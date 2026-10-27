# Python tool contract

Use the absolute `scripts/n8n_api.py` path from the loaded skill. Python 3.10+; runtime uses only the standard library. Examples below abbreviate that path as `TOOL`. The `--catalog FILE` global option precedes the subcommand; other flags follow it.

## Connection

Set `N8N_BASE_URL` and inject `N8N_API_KEY` from the user's secret store into the process environment. `--api-key-env NAME` selects another environment variable for multiple instances. Authentication uses `X-N8N-API-KEY`. API-key scopes and project permissions both apply. TLS is verified; `N8N_CA_FILE` or `--ca-file` adds a private CA bundle. There is no TLS-verification bypass. Plain HTTP requires explicit `--allow-http` for a trusted local/network connection.

An instance URL such as `https://automation.example/n8n` becomes `https://automation.example/n8n/api/v1`. A URL already ending in `/api/v1` is unchanged. Reverse-proxy subpaths are retained. URL credentials, queries, fragments, path traversal and all redirects are rejected. Set the final canonical URL instead of relying on redirects. Standard Python proxy environment variables apply.

## Operation discovery and requests

```text
python TOOL operations --search Settings
python TOOL operations --search Credential
python TOOL describe getWorkflow
python TOOL call getWorkflow -p workflowId=abc123
python TOOL call getWorkflows -q limit=100 -q active=true --all-pages
python TOOL call updateWorkflow -p workflowId=abc123 --body draft.json
python TOOL call updateWorkflow -p workflowId=abc123 --body draft.json --apply
python TOOL call publishWorkflow -p workflowId=abc123 --body version.json --apply
```

`describe` returns the method, path, required scopes, parameters, input schema, multipart schema and content types. Treat comma-separated scope strings as upstream metadata, not a guarantee of the exact AND/OR permission behavior. The catalog lists all published operations, including preview/beta API families; server availability still varies.

`--param/-p` fills path parameters, percent-encoding their values. `--query/-q` accepts unique `NAME=VALUE` pairs. Typed booleans/numbers/arrays/objects use JSON syntax; string enums stay strings. Complex query values are JSON serialized; confirm the server contract before using endpoints with a different serialization convention. Unknown or missing catalog parameters fail locally. Query filters that themselves contain JSON should be passed as one shell argument.

`--body FILE` reads UTF-8 JSON; `--body -` reads stdin. PowerShell UTF-8 BOM files are supported. Put secrets in environment bindings, for example:

```json
{"name":"Service credential","type":"httpHeaderAuth","data":{"name":"Authorization","value":{"$env":"SERVICE_AUTH_HEADER"}}}
```

An object containing only `$env` resolves its named environment variable. Empty/unset values fail. No shell expansion or evaluation is used. This binding works in JSON bodies, multipart field JSON and webhook headers. Use the credential's actual schema from `getCredentialType`, not this illustrative type for every service.

Requests are serialized deterministically. Mutation previews show endpoint, query, field names, byte count and SHA-256 of serialized body; body values and header values are omitted. Review the local file alongside the preview. Changes to the file or environment between preview and apply change the request; the hash is a comparison aid, not a signed approval mechanism. `--dry-run` also previews reads. `--apply` and `--dry-run` are mutually exclusive.

Structural checks cover required fields, readonly fields, types, enum values, basic bounds, patterns, additional properties and schema combinations. They are **not a complete OpenAPI/JSON Schema implementation**: formats, semantic dependencies and node parameters remain server-validated. To address a documented version mismatch, use a version-matched catalog or a verified raw public request rather than editing away inconvenient constraints.

## Outputs and errors

Successful network responses are JSON envelopes: `{"ok":true,"status":200,"data":...}`. A list endpoint therefore commonly appears at `result.data.data`. JSON response files preserve this envelope. To edit a fetched workflow, extract its `data` object into a separate file before `workflow prepare`; do not send the envelope back to n8n.

`--output NEW_FILE` writes the unredacted envelope and prints only status/path. `--download NEW_FILE` writes exact response bytes (JSON or binary). These options are exclusive and never overwrite an existing file. Parent directories must already exist. POSIX files are created with mode 0600; Windows permissions inherit from the directory, so use a directory with appropriate ACLs. Downloads and exports can contain sensitive data.

Without a file option, terminal JSON redacts common secret field names and values injected by `$env` or the API-key environment variable. This is best-effort secret suppression, not comprehensive data loss prevention. Variables, node expressions, execution payloads and unusual credential fields may still contain sensitive content.

HTTP errors return `ok:false`, an error code and numeric status, without the server response body. Exit code 0 means success or a successful preview; 1 means validation/network/API failure; argparse syntax errors use 2. Check `preview` before claiming a mutation occurred. Use instance logs for detailed server errors; don't expose secrets while troubleshooting.

No automatic retry is performed, including for 429/5xx. Stop and inspect state after uncertain writes. `--idempotency-key VALUE` is accepted only for operations that declare that header. Keep a key for the same logical request; do not reuse it for changed content. A 403 workflow update can mean the draft saved but publication failed.

`--all-pages` follows `nextCursor` for cataloged cursor GETs. A repeated/invalid cursor or `--max-pages` limit fails explicitly rather than returning a misleading complete result. Default cap 100 pages; maximum 10,000. All pages are aggregated in memory. Individual requests/responses and uploads have a 64 MiB limit. Use filters and bounded batches for large datasets. Default timeout 30 seconds, configurable up to 600.

## Package upload and download

```text
python TOOL describe exportPackage
python TOOL call exportPackage --body export-selection.json --download package.zip --apply
python TOOL describe importPackage
python TOOL call importPackage --form import-options.json --file package=package.zip
python TOOL call importPackage --form import-options.json --file package=package.zip --apply
```

`--form` is a JSON object of multipart text fields. `--file NAME=PATH` supplies declared binary fields. `importPackage` requires `workflowConflictPolicy` in its form fields. Inspect actual package format and dependencies before import; a `.zip` filename alone doesn't establish validity. Export can include variables, expressions, workflow structure and dependencies. Choose inclusion/conflict/publishing policies deliberately; defaults may import values or preserve live publication.

## Webhooks, health and newer endpoints

```text
python TOOL webhook https://automation.example/webhook/test-order --body event.json
python TOOL webhook https://automation.example/webhook/test-order --body event.json --headers webhook-headers.json --apply
python TOOL health --readiness
python TOOL request GET /documented-new-resource --dry-run
```

Webhook requests never use `N8N_API_KEY`; explicitly supplied header files can use `$env` for webhook-specific authorization. `X-N8N-API-KEY` is disallowed there. Every webhook invocation, including GET, requires `--apply`. URLs cannot contain queries; pass them using `-q`. No redirect is followed. Do not send instance keys to a third-party webhook.

Health checks use the instance URL plus `/healthz` or `/healthz/readiness`, without credentials. If the hosting configuration changes these endpoints, consult its documented settings. A healthy HTTP process is not proof that a workflow succeeds.

`request` is restricted to paths below the configured public `/api/v1` root. It does not authenticate to editor REST endpoints. It supports JSON bodies, normal query values and raw downloads, but not catalog checks, multipart or automatic pagination. This is the extension point for verified endpoints absent from the pinned catalog.
