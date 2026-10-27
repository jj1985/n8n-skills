# Workflow authoring and operations

## Build or edit

Read the existing workflow and identify its draft/published state, project, node versions, credentials and expected trigger. Preserve node names when possible: connections and expressions reference them. A workflow JSON payload is not arbitrary application code; do not invent node types or parameter names. Use a known-good export from the installed version, official node documentation, or the installed node's definition. This applies equally to HTTP, database, SaaS, AI agent, model, memory, vector-store and community nodes.

Use `describe createWorkflow` / `describe updateWorkflow` for the current writable shape. `name`, `nodes`, `connections` and `settings` are required by the bundled schema. `workflow prepare INPUT --operation updateWorkflow --output NEW_FILE` removes top-level read-only/unknown export metadata, reports the removed keys and checks the graph. Review removed fields; don't discard required behavior silently. `workflow validate FILE` runs the same structural checks without removal.

Nodes need stable unique IDs, unique names, type, typeVersion, parameters and a two-number position. Connections are keyed by source **name** and output type, then output-index arrays of target edges. `edge.index` is the target input index. Retain non-main connections (for example AI model/tool connections); cycles can be intentional, so the validator doesn't prohibit them. Structural validation can't establish node-specific input counts, parameter validity or installed node availability.

Expressions normally use n8n's `={{ ... }}` form. `$json` is the current item's JSON; cross-node access depends on item linking and node names. Code-node output must follow the selected execution mode and n8n item conventions. Inspect actual data and pairing rather than substituting guessed expression syntax. Treat binary data references separately from JSON and don't embed secrets into expressions or Code nodes.

Reference credentials by the proper credential type and existing ID/name, not raw passwords in node parameters. For new credentials, retrieve their schema and create them separately with environment-bound secrets. Some OAuth credentials require an interactive provider authorization flow; an API record alone doesn't complete that flow.

The included [manual-pass-through.json](../assets/manual-pass-through.json) is a small, inactive local example. It demonstrates a Manual Trigger connected to a No Operation node. It is not a production integration template.

## Draft, publish, test

On release 2.45.4, saving a published workflow normally republishes it. The helper supplies `publishIfActive=false` by default for `updateWorkflow`. Passing `-q publishIfActive=true` explicitly changes that behavior. For the live version, inspect `activeVersionId` and the returned version state; the old `active` boolean is deprecated. Use `publishWorkflow` with an explicitly selected `versionId` when the task requires a particular version, or `unpublishWorkflow` to stop production triggers. Older instances may only expose `activateWorkflow`/`deactivateWorkflow`; verify semantics instead of assuming equivalence across versions.

Before updating, retain a protected full response and extract the workflow object to prepare a new payload. Re-read the resource just before a consequential update if other editors may have changed it. This helper does not implement an atomic compare-and-swap or promise concurrent-edit protection. The bundled update schema marks `versionId` read-only; do not invent an If-Match header or send that field as a lock. Use documented version facilities where supported, otherwise stop on conflicting edits.

Test with non-production input and verify expected output and downstream effects. There is no universal public "execute any workflow" operation in the bundled catalog. Invoke its authorized webhook, use the editor's manual execution, or use the self-hosted server CLI `n8n execute --id <ID>` where appropriate. A Manual Trigger workflow requires editor/server CLI execution. Do not guess `/workflows/{id}/execute` or `/run`.

Production `/webhook/...` calls require the relevant workflow to be published. `/webhook-test/...` needs the editor's test listener. Preserve webhook authentication and response mode. GET webhooks can perform writes. Retries can duplicate payments, messages or records even if the HTTP verb looks harmless.

For evaluations, inspect `createTestRun`, `getTestRun`, `getTestCases`, `getTestRuns` and `cancelTestRun`. Evaluation runs execute workflow logic and may call paid services. Use the user's authorized dataset/scope; do not trigger evaluations just to validate JSON.

## Diagnose executions

Use `getExecutions` filtered by workflow/status, then `getExecution` with only the data needed. Inspect the failing node, error, input shape, item linking, credential access, run mode and installed node version. Execution history may contain personal data, secrets and large payloads. Save sensitive output locally instead of dumping it into chat.

`retryExecution` may use original or changed workflow behavior depending on its input and version; inspect its schema and assess already-completed side effects. `stopExecution` / `stopManyExecutions` do not undo previous external actions. Deleting history removes diagnostic evidence. Stop after an unexplained failure rather than retrying until an action appears successful.

Verify a change using the resulting draft/published version and one appropriately scoped execution. Keep separate claims for JSON validation, server acceptance, publication and end-to-end correctness. Restoring a workflow snapshot is not rollback of external side effects, execution history or credential changes.
