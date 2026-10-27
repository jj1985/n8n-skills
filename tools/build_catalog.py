"""Compile a pinned local n8n OpenAPI tree. Maintainer dependency: PyYAML."""
import argparse
import json
import re
import copy
from pathlib import Path

import yaml


class OpenApiLoader(yaml.SafeLoader):
    """OpenAPI uses YAML 1.2; PyYAML's default treats 'off'/'on' as booleans."""


OpenApiLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for char, resolvers in OpenApiLoader.yaml_implicit_resolvers.items():
    OpenApiLoader.yaml_implicit_resolvers[char] = [r for r in resolvers if r[0] != "tag:yaml.org,2002:bool"]
OpenApiLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))


def compile_catalog(root, revision, version):
    cache = {}

    def document(path):
        path = path.resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Reference escapes OpenAPI tree")
        if path not in cache:
            cache[path] = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=OpenApiLoader)
        return cache[path]

    def resolve(value, path, trail=()):
        if isinstance(value, list):
            return [resolve(item, path, trail) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            file, _, pointer = value["$ref"].partition("#")
            target = (path.parent / file).resolve() if file else path
            identity = (str(target), pointer)
            if identity in trail:
                raise ValueError("Recursive input schema requires explicit handling")
            node = document(target)
            for key in pointer.lstrip("/").split("/") if pointer else []:
                node = node[key.replace("~1", "/").replace("~0", "~")]
            return resolve(node, target, trail + (identity,))
        return {key: resolve(item, path, trail) for key, item in value.items()
                if not ("operationId" in value and key == "responses")}

    def trim(schema):
        # Preserve validation facts, not upstream prose or example payloads.
        if not isinstance(schema, dict):
            return schema
        keys = {"type", "enum", "required", "nullable", "readOnly", "minimum", "maximum",
                "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                "minItems", "maxItems", "uniqueItems", "pattern", "format", "default"}
        out = {k: v for k, v in schema.items() if k in keys}
        for key in ("properties",):
            if key in schema:
                out[key] = {k: trim(v) for k, v in schema[key].items()}
        for key in ("items", "additionalProperties", "not"):
            if key in schema:
                out[key] = trim(schema[key])
        for key in ("allOf", "anyOf", "oneOf"):
            if key in schema:
                out[key] = [trim(v) for v in schema[key]]
        return out

    routes = root / "openapi.decorator-routes.generated.yml"
    if not routes.exists():
        routes = root / "openapi.yml"
    operations = {}
    for route, raw_path in document(routes)["paths"].items():
        path = resolve(raw_path, routes)
        for method, op in path.items():
            if method not in {"get", "post", "put", "patch", "delete", "head"}:
                continue
            op_id = op["operationId"]
            if op_id in operations:
                raise ValueError("Duplicate operation: " + op_id)
            body = op.get("requestBody", {})
            content = body.get("content", {})
            operations[op_id] = {
                "method": method.upper(), "path": route,
                "tags": op.get("tags", []), "scope": op.get("x-required-scope"),
                "parameters": [{k: trim(v) if k == "schema" else v
                                for k, v in p.items() if k in {"name", "in", "required", "schema", "style", "explode"}}
                               for p in path.get("parameters", []) + op.get("parameters", [])],
                "body_required": body.get("required", False),
                "body_schema": trim(content["application/json"].get("schema", {})) if "application/json" in content else None,
                "content_types": list(content),
                "multipart_schema": trim(content["multipart/form-data"].get("schema", {})) if "multipart/form-data" in content else None,
            }
    return {"source": {"repository": "https://github.com/n8n-io/n8n", "revision": revision,
                       "version": version, "license": "Sustainable Use License 1.0",
                       "notice": "Modified: extracted API interface and input schema facts; prose and responses omitted."},
            "operations": dict(sorted(operations.items()))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    result = compile_catalog(args.source, args.revision, args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Compiled {len(result['operations'])} operations")
