import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("n8n_api", ROOT / "skills/n8n/scripts/n8n_api.py")
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = []
        cls.respond = None

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                cls.calls.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                status, headers, content = cls.respond(self) if cls.respond else (200, {}, {"id": "created", "apiKey": "hidden"})
                self.send_response(status)
                if isinstance(content, (dict, list)):
                    headers.setdefault("Content-Type", "application/json")
                    content = json.dumps(content).encode()
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(content)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_request

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.calls.clear()
        type(self).respond = None
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"N8N_BASE_URL": self.url, "N8N_API_KEY": "test-instance-key", "SERVICE_SECRET": "test-secret-value"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.workflow = json.loads((ROOT / "skills/n8n/assets/manual-pass-through.json").read_text())

    def file(self, name, value):
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def run_tool(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = api.main(list(args))
        return code, json.loads(output.getvalue())

    def call(self, *args):
        return self.run_tool("call", *args, "--allow-http")

    def test_catalog_full_surface(self):
        catalog = api.read_json(str(api.CATALOG))
        self.assertEqual(len(catalog["operations"]), 172)
        self.assertEqual(catalog["source"]["version"], "2.45.4")
        for op in catalog["operations"].values():
            self.assertNotIn("$ref", json.dumps(op))
        floor = catalog["operations"]["updateSecurityPolicy"]["body_schema"]["properties"]["redactionEnforcement"]["properties"]["floor"]
        self.assertIn("off", floor["enum"])
        self.assertNotIn(False, floor["enum"])

    def test_discovery_offline(self):
        code, result = self.run_tool("operations", "--search", "SettingsSso")
        self.assertEqual(code, 0)
        self.assertEqual(len(result["operations"]), 4)
        self.assertEqual(self.calls, [])

    def test_describe_exposes_schema(self):
        code, result = self.run_tool("describe", "createWorkflow")
        self.assertEqual(code, 0)
        self.assertIn("nodes", result["body_schema"]["required"])

    def test_mutation_preview_sends_nothing(self):
        code, result = self.call("createWorkflow", "--body", self.file("wf.json", self.workflow))
        self.assertEqual(code, 0)
        self.assertTrue(result["preview"])
        self.assertEqual(self.calls, [])

    def test_apply_sends_exact_body_and_key(self):
        code, result = self.call("createWorkflow", "--body", self.file("wf.json", self.workflow), "--apply")
        self.assertEqual(code, 0)
        method, path, headers, body = self.calls[0]
        self.assertEqual((method, path), ("POST", "/api/v1/workflows"))
        self.assertEqual(headers["x-n8n-api-key"], "test-instance-key")
        self.assertEqual(json.loads(body), self.workflow)
        self.assertEqual(result["data"]["apiKey"], "[REDACTED]")

    def test_update_defaults_to_draft(self):
        self.call("updateWorkflow", "-p", "workflowId=abc", "--body", self.file("wf.json", self.workflow), "--apply")
        self.assertEqual(self.calls[0][1], "/api/v1/workflows/abc?publishIfActive=false")

    def test_publish_override_is_explicit(self):
        self.call("updateWorkflow", "-p", "workflowId=abc", "-q", "publishIfActive=true", "--body", self.file("wf.json", self.workflow), "--apply")
        self.assertTrue(self.calls[0][1].endswith("publishIfActive=true"))

    def test_path_parameter_encoding(self):
        self.call("getWorkflow", "-p", "workflowId=hello world")
        self.assertEqual(self.calls[0][1], "/api/v1/workflows/hello%20world")

    def test_query_encoding(self):
        self.call("getWorkflows", "-q", "name=Sales & Support")
        self.assertIn("name=Sales+%26+Support", self.calls[0][1])

    def test_reverse_proxy_base_path(self):
        self.call("getWorkflows", "--base-url", self.url + "/n8n/api/v1/")
        self.assertEqual(self.calls[0][1], "/n8n/api/v1/workflows")

    def test_missing_param_stops_locally(self):
        code, _ = self.call("getWorkflow")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_unknown_query_stops_locally(self):
        code, _ = self.call("getWorkflows", "-q", "typo=true")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_invalid_boolean_stops_locally(self):
        code, _ = self.call("getWorkflows", "-q", "active=yes")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_duplicate_pairs_fail(self):
        with self.assertRaises(api.ToolError):
            api.pairs(["x=1", "x=2"])

    def test_unknown_body_property_fails(self):
        self.workflow["bogus"] = True
        code, _ = self.call("createWorkflow", "--body", self.file("wf.json", self.workflow), "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_readonly_body_property_fails(self):
        self.workflow["active"] = True
        code, _ = self.call("createWorkflow", "--body", self.file("wf.json", self.workflow), "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_prepare_export_and_validate_graph(self):
        self.workflow.update(id="existing", active=True, createdAt="2026-01-01", versionId="old")
        out = str(Path(self.temp.name) / "prepared.json")
        code, result = self.run_tool("workflow", "prepare", self.file("export.json", self.workflow), "--output", out)
        self.assertEqual(code, 0)
        self.assertIn("active", result["removed_fields"])
        self.assertNotIn("active", json.loads(Path(out).read_text()))

    def test_invalid_graph_target(self):
        self.workflow["connections"]["Manual Trigger"]["main"][0][0]["node"] = "missing"
        with self.assertRaises(api.ToolError):
            api.validate_workflow(self.workflow)

    def test_duplicate_nodes(self):
        self.workflow["nodes"].append(copy.deepcopy(self.workflow["nodes"][0]))
        with self.assertRaises(api.ToolError):
            api.validate_workflow(self.workflow)

    def test_env_binding_is_sent_and_redacted(self):
        body = self.file("secret.json", {"name": "Demo", "type": "httpHeaderAuth", "data": {"name": "Authorization", "value": {"$env": "SERVICE_SECRET"}}})
        type(self).respond = lambda _: (200, {}, {"echo": "test-secret-value"})
        code, result = self.call("createCredential", "--body", body, "--apply")
        self.assertEqual(code, 0)
        self.assertIn(b"test-secret-value", self.calls[0][3])
        self.assertNotIn("test-secret-value", json.dumps(result))

    def test_missing_env_binding_fails(self):
        with self.assertRaises(api.ToolError):
            api.bind_env({"$env": "N8N_TEST_DEFINITELY_MISSING"}, [])

    def test_output_preserves_raw_secret_and_does_not_echo(self):
        out = str(Path(self.temp.name) / "response.json")
        code, result = self.call("getWorkflow", "-p", "workflowId=abc", "--output", out)
        self.assertEqual(code, 0)
        self.assertNotIn("hidden", json.dumps(result))
        self.assertEqual(json.loads(Path(out).read_text())["data"]["apiKey"], "hidden")

    def test_existing_output_fails_before_mutation(self):
        out = self.file("existing.json", {})
        code, _ = self.call("deleteWorkflow", "-p", "workflowId=abc", "--apply", "--output", out)
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_redirect_does_not_forward_key(self):
        type(self).respond = lambda _: (302, {"Location": self.url + "/leak"}, b"")
        code, result = self.call("getWorkflows")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["status"], 302)
        self.assertEqual(len(self.calls), 1)

    def test_http_error_no_body_or_retry(self):
        type(self).respond = lambda _: (429, {}, {"secret": "do-not-display"})
        code, result = self.call("getWorkflows")
        self.assertEqual(code, 1)
        self.assertNotIn("do-not-display", json.dumps(result))
        self.assertEqual(len(self.calls), 1)

    def test_204_delete(self):
        type(self).respond = lambda _: (204, {}, b"")
        code, result = self.call("deleteWorkflow", "-p", "workflowId=abc", "--apply")
        self.assertEqual(code, 0)
        self.assertIsNone(result["data"])

    def test_pagination(self):
        type(self).respond = lambda h: (200, {}, {"data": [2], "nextCursor": None} if "cursor=" in h.path else {"data": [1], "nextCursor": "a+/="})
        code, result = self.call("getWorkflows", "--all-pages")
        self.assertEqual(code, 0)
        self.assertEqual(result["data"]["data"], [1, 2])
        self.assertIn("cursor=a%2B%2F%3D", self.calls[1][1])

    def test_repeated_cursor_fails(self):
        type(self).respond = lambda _: (200, {}, {"data": [], "nextCursor": "repeat"})
        code, result = self.call("getWorkflows", "--all-pages")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "incomplete_pagination")
        self.assertEqual(len(self.calls), 2)

    def test_page_limit_is_not_silent_truncation(self):
        type(self).respond = lambda _: (200, {}, {"data": [1], "nextCursor": "next"})
        code, result = self.call("getWorkflows", "--all-pages", "--max-pages", "1")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "incomplete_pagination")

    def test_webhook_get_preview(self):
        code, result = self.run_tool("webhook", self.url + "/webhook/example", "--method", "GET", "--allow-http")
        self.assertEqual(code, 0)
        self.assertTrue(result["preview"])
        self.assertEqual(self.calls, [])

    def test_webhook_never_sends_api_key(self):
        header_file = self.file("headers.json", {"Authorization": {"$env": "SERVICE_SECRET"}})
        code, _ = self.run_tool("webhook", self.url + "/webhook/example", "--headers", header_file, "--apply", "--allow-http")
        self.assertEqual(code, 0)
        self.assertNotIn("x-n8n-api-key", self.calls[0][2])
        self.assertEqual(self.calls[0][2]["authorization"], "test-secret-value")

    def test_health_does_not_send_api_key(self):
        self.run_tool("health", "--readiness", "--allow-http")
        self.assertEqual(self.calls[0][1], "/healthz/readiness")
        self.assertNotIn("x-n8n-api-key", self.calls[0][2])

    def test_url_guards(self):
        for url in ("https://user:pass@example.com", "https://example.com/?x=1", "https://example.com/#frag", "https://example.com/../escape", "https://example.com/%252e%252e/escape", "https://example.com/\\evil"):
            with self.subTest(url=url), self.assertRaises(api.ToolError):
                api.safe_url(url)

    def test_http_requires_explicit_flag(self):
        code, _ = self.run_tool("call", "getWorkflows")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_raw_path_cannot_escape(self):
        for path in ("https://evil.test", "//evil.test", "/../rest/settings", "/%252e%252e/rest", "/rest/settings"):
            with self.subTest(path=path):
                code, _ = self.run_tool("request", "GET", path, "--allow-http")
                self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_raw_verified_request(self):
        code, _ = self.run_tool("request", "PATCH", "/future-resource/abc", "--body", self.file("body.json", {"enabled": True}), "--apply", "--allow-http")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[0][0:2], ("PATCH", "/api/v1/future-resource/abc"))

    def test_multipart_upload(self):
        package = Path(self.temp.name) / "package.zip"
        package.write_bytes(b"fake-archive-content")
        options = self.file("form.json", {"workflowConflictPolicy": "fail"})
        code, _ = self.call("importPackage", "--form", options, "--file", "package=" + str(package), "--apply")
        self.assertEqual(code, 0)
        self.assertIn(b'filename="package.zip"', self.calls[0][3])
        self.assertIn(b"fake-archive-content", self.calls[0][3])
        self.assertIn(b"workflowConflictPolicy", self.calls[0][3])

    def test_multipart_required_field(self):
        options = self.file("form.json", {"workflowConflictPolicy": "fail"})
        code, _ = self.call("importPackage", "--form", options, "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])

    def test_binary_download(self):
        type(self).respond = lambda _: (200, {"Content-Type": "application/zip"}, b"PK\x03\x04example")
        out = str(Path(self.temp.name) / "package.zip")
        code, _ = self.call("exportPackage", "--body", self.file("export.json", {"workflowIds": ["abc"]}), "--apply", "--download", out)
        self.assertEqual(code, 0)
        self.assertEqual(Path(out).read_bytes(), b"PK\x03\x04example")

    def test_idempotency_supported_only(self):
        code, _ = self.call("createWorkflow", "--body", self.file("wf.json", self.workflow), "--idempotency-key", "test-request", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[0][2]["idempotency-key"], "test-request")
        code, _ = self.call("getWorkflows", "--idempotency-key", "test-request")
        self.assertEqual(code, 1)

    def test_utf8_bom_input(self):
        file = Path(self.temp.name) / "bom.json"
        file.write_text(json.dumps(self.workflow), encoding="utf-8-sig")
        code, _ = self.run_tool("workflow", "validate", str(file))
        self.assertEqual(code, 0)

    def test_schema_bool_is_not_integer(self):
        with self.assertRaises(api.ToolError):
            api.validate(True, {"type": "integer"})

    def test_schema_required_nested_field(self):
        with self.assertRaises(api.ToolError):
            api.validate({"nested": {}}, {"properties": {"nested": {"required": ["name"]}}})

    def test_schema_oneof(self):
        schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
        api.validate("x", schema)
        with self.assertRaises(api.ToolError):
            api.validate([], schema)


if __name__ == "__main__":
    unittest.main()
