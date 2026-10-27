#!/usr/bin/env python3
"""Deterministic n8n public API tools. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, unquote
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

CATALOG = Path(__file__).with_name("operations.json")
SENSITIVE = re.compile(r"password|secret|token|authorization|api.?key|private.?key|cookie", re.I)
MAX_BYTES = 64 * 1024 * 1024


class ToolError(Exception):
    def __init__(self, message, code="invalid_input", status=None):
        super().__init__(message)
        self.code, self.status = code, status


def read_json(path):
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
        return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, ValueError):
        raise ToolError("Cannot read valid JSON input (UTF-8 required)") from None


def pairs(items):
    result = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key or key in result:
            raise ToolError("Arguments must be unique NAME=VALUE pairs")
        result[key] = value
    return result


def bind_env(value, secrets):
    if isinstance(value, dict):
        if set(value) == {"$env"}:
            name = value["$env"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ToolError("Invalid environment variable reference")
            secret = os.environ.get(name)
            if not secret:
                raise ToolError(f"Required environment variable is unset: {name}")
            secrets.append(secret)
            return secret
        return {k: bind_env(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [bind_env(v, secrets) for v in value]
    return value


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if SENSITIVE.search(k) else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted(set(secrets), key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def validate(value, schema, location="body"):
    """Validate input structural constraints; the server remains authoritative."""
    def fail(reason):
        raise ToolError(f"{location}: {reason}")
    if schema is False:
        fail("value is not allowed")
    if not isinstance(schema, dict):
        return
    if schema.get("readOnly"):
        fail("read-only field must be omitted")
    if value is None and schema.get("nullable"):
        return
    for sub in schema.get("allOf", []):
        validate(value, sub, location)
    for combinator in ("oneOf", "anyOf"):
        if combinator in schema:
            matches = 0
            for sub in schema[combinator]:
                try:
                    validate(value, sub, location)
                    matches += 1
                except ToolError:
                    pass
            if not matches or (combinator == "oneOf" and matches != 1):
                fail(f"does not satisfy {combinator}")
    if "not" in schema:
        try:
            validate(value, schema["not"], location)
        except ToolError:
            pass
        else:
            fail("matches a prohibited schema")
    kind = schema.get("type")
    checks = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
              "string": lambda: isinstance(value, str), "boolean": lambda: type(value) is bool,
              "integer": lambda: type(value) is int,
              "number": lambda: type(value) in (int, float) and math.isfinite(value),
              "null": lambda: value is None}
    if kind in checks and not checks[kind]():
        fail(f"expected {kind}")
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        fail("not in allowed enum; see describe")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value and not props.get(key, {}).get("readOnly"):
                fail(f"missing required field {key}")
        for key, item in value.items():
            if key in props:
                validate(item, props[key], f"{location}.{key}")
            elif schema.get("additionalProperties") is False:
                fail(f"unknown field {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(item, schema["additionalProperties"], f"{location}.{key}")
    if isinstance(value, (str, list)):
        suffix = "Length" if isinstance(value, str) else "Items"
        if len(value) < schema.get("min" + suffix, 0) or len(value) > schema.get("max" + suffix, math.inf):
            fail("length outside allowed range")
    if isinstance(value, str) and "pattern" in schema:
        try:
            if not re.search(schema["pattern"], value):
                fail("does not match required pattern")
        except re.error:
            fail("schema regex is not supported by Python; use verified raw request")
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{location}[{index}]")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            fail("items must be unique")
    if type(value) in (int, float):
        for key, compare in (("minimum", lambda x: value < x), ("maximum", lambda x: value > x)):
            if key in schema and (compare(schema[key]) or (schema.get("exclusive" + key.title()) is True and value == schema[key])):
                fail("number outside allowed range")


def coerce(value, schema):
    kind = schema.get("type")
    if kind in {"boolean", "integer", "number", "array", "object"}:
        try:
            value = json.loads(value)
        except ValueError:
            raise ToolError("Typed parameter must use JSON syntax") from None
    validate(value, schema, "parameter")
    return value


def wire_value(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def safe_url(url, allow_http=False):
    try:
        parts = urlsplit(url)
        _ = parts.port
    except ValueError:
        raise ToolError("Invalid URL") from None
    if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment or "\\" in url
            or any(ord(c) < 33 for c in url)):
        raise ToolError("URL must be HTTP(S), without credentials, query, fragment or whitespace")
    if parts.scheme != "https" and not allow_http:
        raise ToolError("HTTP requires --allow-http for an explicitly trusted connection")
    safe_path(parts.path or "/")
    return url.rstrip("/")


def safe_path(path):
    if not path.startswith("/") or path.startswith("//"):
        raise ToolError("Path must start with one slash")
    decoded = path
    for _ in range(4):
        if any(c in decoded for c in "\\?#") or any(ord(c) < 32 for c in decoded):
            raise ToolError("Path contains unsafe delimiters")
        if any(segment in {".", ".."} for segment in decoded.split("/")):
            raise ToolError("Path traversal is not allowed")
        new = unquote(decoded)
        if new == decoded:
            break
        decoded = new
    if "%" in decoded:
        raise ToolError("Ambiguous encoded path")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base, key=None, allow_http=False, timeout=30, ca_file=None):
        self.base = safe_url(base, allow_http)
        self.key = key
        self.timeout = timeout
        if not 0 < timeout <= 600:
            raise ToolError("Timeout must be between 0 and 600 seconds")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))

    def send(self, method, url, body=None, headers=None):
        headers = {"Accept": "application/json", "User-Agent": "n8n-copilot-skills/1.0.0", **(headers or {})}
        if self.key:
            if any(c in self.key for c in "\r\n"):
                raise ToolError("Invalid API key")
            headers["X-N8N-API-KEY"] = self.key
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ToolError("Response exceeds 64 MiB; narrow the request", "response_too_large")
                content_type = response.headers.get("Content-Type", "")
                if not raw:
                    return response.status, None, raw
                if "json" in content_type:
                    try:
                        return response.status, json.loads(raw), raw
                    except ValueError:
                        raise ToolError("Server returned invalid JSON", "invalid_response") from None
                return response.status, {"content_type": content_type, "bytes": len(raw),
                                         "sha256": hashlib.sha256(raw).hexdigest()}, raw
        except HTTPError as error:
            # Do not echo server bodies or Location: they may contain secrets.
            status = error.code
            error.close()
            hints = {401: "Check API key and expiration", 403: "Check scopes, project role and license; verify state before retrying",
                     404: "Check resource ID, base URL and instance version", 409: "Re-read state and resolve the conflict",
                     429: "Rate limited; wait and reassess before retrying"}
            raise ToolError(hints.get(status, "HTTP request failed; inspect instance logs"), "http_error", status) from None
        except (URLError, TimeoutError, OSError):
            raise ToolError("Network or TLS failure; outcome may be unknown. Verify state before retrying writes.", "network_error") from None


def write_new(path, content):
    target = Path(path)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
    except OSError:
        raise ToolError("Cannot create output; choose a new file in an existing directory") from None


def multipart(fields, files):
    chunks = []
    # Content-derived boundary keeps serialization repeatable.
    parts = []
    for name, value in fields.items():
        parts.append((name, None, wire_value(value).encode("utf-8")))
    for name, path in files.items():
        p = Path(path)
        if p.stat().st_size > MAX_BYTES:
            raise ToolError("Upload exceeds 64 MiB")
        parts.append((name, p.name, p.read_bytes()))
    boundary = "n8n-" + hashlib.sha256(b"".join(p[2] for p in parts)).hexdigest()
    for name, filename, content in parts:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ToolError("Invalid multipart field name")
        if filename and any(c in filename for c in '\r\n"\\'):
            raise ToolError("Unsupported upload filename")
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"\r\nContent-Type: application/octet-stream'
        chunks.append(f"--{boundary}\r\n{disposition}\r\n\r\n".encode() + content + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def validate_workflow(workflow):
    if not isinstance(workflow, dict):
        raise ToolError("Workflow must be an object, not an export array")
    nodes, connections = workflow.get("nodes"), workflow.get("connections")
    if not isinstance(nodes, list) or not isinstance(connections, dict):
        raise ToolError("Workflow needs nodes array and connections object")
    names, ids = set(), set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ToolError("Each node must be an object")
        for field in ("name", "type", "id"):
            if not isinstance(node.get(field), str) or not node[field]:
                raise ToolError(f"Node needs nonempty {field}")
        if node["name"] in names or node["id"] in ids:
            raise ToolError("Node names and IDs must be unique")
        names.add(node["name"])
        ids.add(node["id"])
        if not isinstance(node.get("parameters"), dict) or type(node.get("typeVersion")) not in (int, float):
            raise ToolError("Node needs parameters object and numeric typeVersion")
        if not isinstance(node.get("position"), list) or len(node["position"]) != 2 or any(type(v) not in (int, float) for v in node["position"]):
            raise ToolError("Node position must contain two numbers")
    for source, outputs in connections.items():
        if source not in names or not isinstance(outputs, dict):
            raise ToolError("Connection source must identify an existing node")
        for port, branches in outputs.items():
            if not isinstance(branches, list):
                raise ToolError("Connection outputs must be arrays")
            for edges in branches:
                if not isinstance(edges, list):
                    raise ToolError("Each connection output must contain an array of edges")
                for edge in edges:
                    if (not isinstance(edge, dict) or edge.get("node") not in names or edge.get("type") != port
                            or type(edge.get("index")) is not int or edge["index"] < 0):
                        raise ToolError("Invalid connection target, type or input index")


def request_options(parser):
    parser.add_argument("--base-url", default=os.environ.get("N8N_BASE_URL"), help="Instance URL or API root; default N8N_BASE_URL")
    parser.add_argument("--api-key-env", default="N8N_API_KEY")
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--ca-file", default=os.environ.get("N8N_CA_FILE"))
    parser.add_argument("--body", help="JSON file, or - for stdin; supports {$env: NAME} values")
    parser.add_argument("--query", "-q", action="append", default=[])
    parser.add_argument("--apply", action="store_true", help="Send a mutation after authorization; otherwise preview only")
    parser.add_argument("--dry-run", action="store_true", help="Preview reads as well as writes")
    parser.add_argument("--output", help="Write full, unredacted JSON envelope to a NEW file")
    parser.add_argument("--download", help="Write exact response bytes to a NEW file")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--catalog", default=str(CATALOG), help="Alternate compiled catalog for an instance version")
    sub = root.add_subparsers(dest="command", required=True)
    ops = sub.add_parser("operations", help="List supported operations offline")
    ops.add_argument("--search", default="")
    describe = sub.add_parser("describe", help="Show exact method, parameters, scope and body schema")
    describe.add_argument("operation")
    call = sub.add_parser("call", help="Invoke a named catalog operation")
    call.add_argument("operation")
    call.add_argument("--param", "-p", action="append", default=[])
    call.add_argument("--idempotency-key")
    call.add_argument("--form", help="JSON file of multipart text fields")
    call.add_argument("--file", action="append", default=[], help="Multipart NAME=FILE")
    call.add_argument("--all-pages", action="store_true")
    call.add_argument("--max-pages", type=int, default=100)
    request_options(call)
    raw = sub.add_parser("request", help="Version-specific public API escape hatch; verify endpoint documentation first")
    raw.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    raw.add_argument("path", help="Path below /api/v1, for example /workflows")
    request_options(raw)
    webhook = sub.add_parser("webhook", help="Invoke a user-specified webhook; never sends the n8n API key")
    webhook.add_argument("url")
    webhook.add_argument("--method", default="POST", choices=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    webhook.add_argument("--headers", help="JSON header file with optional $env bindings")
    request_options(webhook)
    health = sub.add_parser("health", help="Check /healthz or /healthz/readiness without API credentials")
    health.add_argument("--readiness", action="store_true")
    request_options(health)
    wf = sub.add_parser("workflow", help="Offline workflow payload preparation and graph checks")
    wf.add_argument("action", choices=["validate", "prepare"])
    wf.add_argument("file")
    wf.add_argument("--operation", choices=["createWorkflow", "updateWorkflow"], default="createWorkflow")
    wf.add_argument("--output", help="Write prepared payload to a new file")
    return root


def run(args):
    catalog = read_json(args.catalog)
    operations = catalog["operations"]
    if args.command == "operations":
        needle = args.search.casefold()
        return {"ok": True, "source": catalog["source"], "operations": [
            {"operation": name, **{k: op[k] for k in ("method", "path", "tags", "scope")}}
            for name, op in operations.items() if needle in (name + json.dumps(op.get("tags")) + op["path"]).casefold()]}
    if args.command == "describe":
        if args.operation not in operations:
            raise ToolError("Unknown operation; use operations --search")
        return {"ok": True, "operation": args.operation, **operations[args.operation]}
    if args.command == "workflow":
        workflow = read_json(args.file)
        schema = operations[args.operation]["body_schema"]
        removed = []
        if args.action == "prepare":
            if not isinstance(workflow, dict):
                raise ToolError("Select one workflow object from an export array first")
            props = schema["properties"]
            removed = [k for k in workflow if k not in props or props[k].get("readOnly")]
            workflow = {k: v for k, v in workflow.items() if k not in removed}
        validate(workflow, schema)
        validate_workflow(workflow)
        if args.output:
            write_new(args.output, (json.dumps(workflow, indent=2, ensure_ascii=False) + "\n").encode())
        return {"ok": True, "valid": True, "removed_fields": removed, "output": args.output,
                "note": "Structural checks only; node parameters, expressions and runtime behavior need instance testing"}

    if args.apply and args.dry_run:
        raise ToolError("Choose --apply or --dry-run")
    if args.output and args.download:
        raise ToolError("Choose --output or --download")
    for file in (args.output, args.download):
        if file and (Path(file).exists() or not Path(file).parent.is_dir()):
            raise ToolError("Output must be a new file in an existing directory")
    secrets = []
    body = bind_env(read_json(args.body), secrets) if args.body else None
    query = pairs(args.query)
    headers = {}
    files = {}
    method, path = getattr(args, "method", "GET"), getattr(args, "path", "")
    if args.command == "call":
        op = operations.get(args.operation)
        if not op:
            raise ToolError("Unknown operation; use operations --search")
        method, path = op["method"], op["path"]
        params = pairs(args.param)
        allowed = {where: {p["name"]: p for p in op["parameters"] if p["in"] == where} for where in ("path", "query", "header")}
        for where, provided in (("path", params), ("query", query)):
            if provided.keys() - allowed[where].keys():
                raise ToolError(f"Unknown {where} parameter; use describe")
            for name, spec in allowed[where].items():
                if spec.get("required") and name not in provided:
                    raise ToolError(f"Missing {where} parameter: {name}")
                if name in provided:
                    provided[name] = coerce(provided[name], spec.get("schema", {}))
        for name, value in params.items():
            path = path.replace("{" + name + "}", quote(wire_value(value), safe=""))
        if args.idempotency_key:
            spec = allowed["header"].get("Idempotency-Key")
            if not spec:
                raise ToolError("This operation does not declare idempotency support")
            validate(args.idempotency_key, spec["schema"], "Idempotency-Key")
            headers["Idempotency-Key"] = args.idempotency_key
        if args.form or args.file:
            if args.body or op["multipart_schema"] is None:
                raise ToolError("Multipart requires a multipart operation and no --body")
            body = bind_env(read_json(args.form), secrets) if args.form else {}
            if not isinstance(body, dict):
                raise ToolError("Multipart fields must be a JSON object")
            files = pairs(args.file)
            if body.keys() & files.keys():
                raise ToolError("Duplicate multipart field")
            validate({**body, **files}, op["multipart_schema"])
            for key, spec in op["multipart_schema"].get("properties", {}).items():
                if spec.get("format") == "binary" and key in body:
                    raise ToolError("Binary fields must use --file")
            for key in files:
                if op["multipart_schema"].get("properties", {}).get(key, {}).get("format") != "binary":
                    raise ToolError("--file only accepts binary schema fields")
        elif body is not None:
            if op["body_schema"] is None:
                raise ToolError("Operation does not accept JSON; inspect content_types")
            validate(body, op["body_schema"])
        elif op["body_required"]:
            raise ToolError("Operation requires a request body")
        if args.operation in {"createWorkflow", "updateWorkflow"}:
            validate_workflow(body)
        if args.operation == "updateWorkflow" and "publishIfActive" in allowed["query"]:
            # Saving a published workflow otherwise automatically republishes on current n8n.
            query.setdefault("publishIfActive", "false")
        if args.all_pages and (method != "GET" or "cursor" not in allowed["query"] or args.download):
            raise ToolError("--all-pages requires a cursor-based GET and JSON output")
        if not 1 <= args.max_pages <= 10000:
            raise ToolError("--max-pages must be 1..10000")
    is_webhook = args.command == "webhook"
    is_health = args.command == "health"
    key = None
    if is_webhook:
        base = safe_url(args.url, args.allow_http)
        if args.headers:
            headers = bind_env(read_json(args.headers), secrets)
            if not isinstance(headers, dict):
                raise ToolError("Webhook headers must be a JSON object")
            for name, value in headers.items():
                if (not re.fullmatch(r"[A-Za-z0-9-]+", name) or not isinstance(value, str)
                        or any(c in value for c in "\r\n") or name.lower() in {"host", "content-length", "transfer-encoding", "x-n8n-api-key"}):
                    raise ToolError("Unsupported webhook header")
    else:
        if not args.base_url:
            raise ToolError("Set N8N_BASE_URL or --base-url")
        base = safe_url(args.base_url, args.allow_http)
        if is_health:
            if base.endswith("/api/v1"):
                base = base[:-7]
            path = "/healthz/readiness" if args.readiness else "/healthz"
            if body is not None or query:
                raise ToolError("Health checks do not accept body or query parameters")
        else:
            if not base.endswith("/api/v1"):
                base += "/api/v1"
            safe_path(path)
            if path.startswith("/api/") or path.startswith("/rest/"):
                raise ToolError("Supply a public API path below /api/v1; editor REST endpoints are unsupported")
            key = os.environ.get(args.api_key_env)
            if key:
                secrets.append(key)
    encoded = None
    if args.command == "call" and (args.form or args.file):
        encoded, headers["Content-Type"] = multipart(body, files)
    elif body is not None:
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    if encoded is not None and len(encoded) > MAX_BYTES:
        raise ToolError("Request exceeds 64 MiB")
    if method in {"GET", "HEAD"} and encoded is not None:
        raise ToolError("GET/HEAD must not carry a body")
    url = base if is_webhook else base + path
    url += ("?" + urlencode({k: wire_value(v) for k, v in query.items()})) if query else ""
    mutating = method not in {"GET", "HEAD"} or is_webhook
    if args.dry_run or (mutating and not args.apply):
        # Omit payload values entirely; hashes identify the exact reviewed serialized body.
        return {"ok": True, "preview": True, "method": method, "endpoint": base if is_webhook else base + path,
                "query": redact(query, secrets), "body_bytes": len(encoded or b""),
                "body_sha256": hashlib.sha256(encoded or b"").hexdigest(),
                "body_fields": list(body) if isinstance(body, dict) else None,
                "files": list(files), "header_names": list(headers),
                "authorization_required": mutating,
                "note": "No request sent. Use --apply only within the user's authorized scope."}
    if not is_webhook and not is_health and not key:
        raise ToolError(f"Set API key environment variable {args.api_key_env}")
    client = Client(base, key, args.allow_http, args.timeout, args.ca_file)
    status, data, raw = client.send(method, url, encoded, headers)
    if getattr(args, "all_pages", False):
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ToolError("Expected cursor envelope with data array", "invalid_response")
        combined, seen, page = list(data["data"]), set(), 1
        cursor = data.get("nextCursor")
        while cursor:
            if not isinstance(cursor, str) or cursor in seen or page >= args.max_pages:
                raise ToolError("Pagination incomplete: repeated/invalid cursor or page limit; narrow query or raise --max-pages", "incomplete_pagination")
            seen.add(cursor)
            query["cursor"] = cursor
            _, data, _ = client.send("GET", base + path + "?" + urlencode({k: wire_value(v) for k, v in query.items()}))
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise ToolError("Invalid pagination response", "invalid_response")
            combined.extend(data["data"])
            cursor = data.get("nextCursor")
            page += 1
        data = {"data": combined, "nextCursor": None, "pages": page}
    result = {"ok": True, "status": status, "data": data}
    if args.output:
        write_new(args.output, (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode())
        return {"ok": True, "status": status, "output": args.output}
    if args.download:
        write_new(args.download, raw)
        return {"ok": True, "status": status, "download": args.download, "bytes": len(raw)}
    return redact(result, secrets)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except ToolError as error:
        result = {"ok": False, "error": {"code": error.code, "message": str(error)}}
        if error.status is not None:
            result["error"]["status"] = error.status
        print(json.dumps(result, ensure_ascii=True))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "Invalid input, file or catalog; inspect local configuration"}}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
