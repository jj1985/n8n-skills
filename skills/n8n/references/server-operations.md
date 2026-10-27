# Server, hosting and UI operations

Use this route when the requested capability isn't exposed by the installed public API. The bundled Python tool is a remote API client, not a privileged shell on the n8n host. Do not confuse n8n's remote CLI with the **Server CLI**, which runs beside the database and can bypass application access controls. Do not automatically install a second CLI to use this skill.

## Inspect before changing

Determine Cloud versus self-hosted, deployed n8n version, container/service names, single-process versus queue topology, database, binary storage, task runners and reverse proxy from available deployment files and operator context. Read only the relevant config and avoid printing secret values. Use `python TOOL health` and `--readiness` for HTTP checks; inspect authorized server/worker logs for the specific failure.

For Docker, invoke the Server CLI with the existing container and user, for example `docker exec -u node <container> n8n --help`. For npm installations use the installed `n8n --help`. Verify the particular command's `--help` on the installed version before running it. Do not assume a container name, database path or Kubernetes namespace.

## Configuration and scaling

Most host-wide settings use n8n environment variables or supported configuration files. Edit the actual deployment source (Compose, Kubernetes manifests, service environment or the platform's settings) rather than exporting variables only in the agent's temporary shell. Keep secrets in the existing secret-management system. Prepare the exact diff and the appropriate restart/redeploy operation; apply when it falls within the user's authorization.

Consult the [official configuration reference](https://docs.n8n.io/hosting/configuration/environment-variables/) for the installed version. Relevant areas include URL/reverse-proxy configuration, timezone, database, encryption, execution timeouts/pruning, binary storage, queue/Redis settings, task runners, security, external secrets, diagnostics, metrics and licensing. Avoid copying environment variable names or defaults from unrelated versions.

Queue deployments require coordination between the main instance, workers, webhook processors, Redis, database, storage and encryption configuration. A healthy main process doesn't establish worker readiness. Confirm that binary storage and Code-node task-runner choices are supported for the topology. Scale through the hosting platform; a public n8n workflow API request cannot resize workers.

Community packages execute code in the n8n environment. Inspect package source/version and compatibility before installing. Use the published API operations where available; otherwise follow official installation procedures for the specific hosting model. Do not work around disabled installation policy. Node availability must match every process that executes it.

## Backups, restore and upgrades

A workflow export or source-control repository is not a full backup. Plan for a consistent database backup, encryption key, configured binary-data storage, deployment configuration and relevant external dependencies. Preserve the encryption key; replacing it can make existing credentials unreadable. Store backups privately and test restoration in an isolated environment before claiming recoverability.

The Server CLI offers workflow/credential export/import and entity export/import on supported versions. Consult its installed help and [official Server CLI documentation](https://docs.n8n.io/hosting/cli-commands/). Avoid decrypted credential export unless specifically needed and authorized. Existing IDs, ownership, publication state and credential relationships matter on import; do not import over a live instance to test a backup.

For upgrades, read release notes and migration guidance between the installed and target versions. Record the current version and recovery point, validate database/storage compatibility, and test the intended workflows. Some migrations cannot be undone by merely selecting an older container image. Make rollback concrete before applying the upgrade.

## Execution, publishing and recovery

For authorized local execution, the Server CLI supports `n8n execute --id <ID>`. This can run external actions and isn't an offline validation command. Use the editor's test execution or a staging instance when appropriate.

Current Server CLI publishing uses `publish:workflow` and `unpublish:workflow`; older versions used `update:workflow --active=...`. Server CLI publishing changes the database and can require a restart of the running instance to take effect. Prefer the public publish endpoint for a running remote instance when available. Never assume a database write has updated in-memory triggers.

User-management resets, MFA recovery, license commands and direct database repairs are high-impact operator tasks. Only run the exact recovery needed for an explicitly authorized incident after verifying installed commands and recovery state. Do not reset authentication to solve a normal API 403.

## UI and provider actions

Use authorized UI interaction for settings with no supported public API, OAuth consent, license activation or provider-side configuration. If the agent has no UI/host access, prepare the concrete files/instructions and explain the remaining access needed. Do not claim a setting changed merely because a config file or request preview was prepared. MCP isn't a fallback requirement.
