# Instance and licensed administration

All public API families from release 2.45.4 are included, regardless of edition. The catalog does not hide Business/Enterprise operations. License, release, user role, project permission and API-key scope can independently restrict them. Discover the actual instance capabilities before acting. Some families are preview/beta and may change outside a major release.

Use `operations --search TERM`, then `describe OPERATION` for exact payloads. Never infer a supported verb from a resource name. This table routes tasks without reproducing the schemas:

| Task | Catalog search terms |
| --- | --- |
| Workflow CRUD, history, versions, publish/unpublish, archive, transfer, tags | `Workflow` |
| Execution history, retry, stop, bulk stop, delete, annotations | `Executions` |
| Credential CRUD, schema, test, transfer | `Credential` |
| Users, invitations, instance roles | `User` |
| Projects, memberships, project roles, transfers | `Projects`, `Role` |
| Identity-provider role mapping and rule order | `RoleMappingRule` |
| Tags, variables, folders | `Tags`, `Variables`, `Folders` |
| Tables, columns, rows, upsert, update, clear, delete | `DataTable` |
| Community node install/update/uninstall | `CommunityPackage` |
| Evaluation runs, cases, cancellation | `Evaluation` |
| Insights and security audits | `Insights`, `Audit` |
| LDAP configuration and synchronization | `SettingsLdap` |
| OIDC and SAML settings | `SettingsSsoOidc`, `SettingsSsoSaml` |
| Security policy and redaction enforcement | `SecurityPolicy` |
| OpenTelemetry settings and test trace | `SettingsOtel` |
| Log streaming destinations, types and tests | `LogStreaming` |
| Node-type and credential-type policies, documents, attachments | `NodeTypePolicy`, `CredentialTypePolicy` |
| Source-control status, pull and push | `SourceControl` |
| Promotion providers, connections, checkout, project selection, apply/continue | `Promotions` |
| Dependency-aware package export/import and selection | `N8nPackage` |
| API capabilities visible to this identity | `Discover` |

## Resource changes

Resolve exact IDs and project ownership before transfers, role changes or deletion. A name is not a unique identifier across projects. Preserve existing memberships unless their removal is requested. Deleting a project, table, folder, user or credential can affect dependent workflows. Inspect dependencies through the installed version's supported facilities and establish deletion behavior; do not assume automatic migration or cascading deletion is safe.

Variables are configuration values and can contain sensitive information; they are not a substitute for credential encryption. Data-table row update/delete operations require particular filter shapes; inspect the schema and sample matching rows first. Bulk clear is distinct from deleting selected rows. API query flags named `dryRun` are server semantics, distinct from the client's `--dry-run` (which sends nothing).

Credential `data` is type-specific. Get the credential type schema before creating or patching. Do not treat redacted/absent secrets in a read response as authoritative blank values. Credential tests can make outbound requests. Keep secret files outside the repository. Rotating encryption keys is a server-level migration, not an ordinary credential update.

## Authentication and security settings

Tag names in 2.45.4 must be 1–24 characters after trimming. The public schema omits this bound and the server can report a misleading 409 for an overlong name. The Python tool checks it locally. Source: [TagEntity at the pinned release](https://github.com/n8n-io/n8n/blob/e0c02a617f5e6ede3d6c448aff41f632a782aaca/packages/%40n8n/db/src/entities/tag-entity.ts).

Fetch current writable settings, prepare a minimal intended change while supplying the required full-body fields, and inspect masks/defaults before PUT. Test SSO discovery, issuer/callback URLs, claims and provider requirements using the installed version's documentation. Retain an authorized recovery route before enabling mandatory SSO or changing administrative role mappings. Do not reset users or disable authentication as a shortcut for permission errors.

LDAP sync, role mapping, security policy, redaction enforcement and node restrictions may affect many users or workflows. Match the requested scope. Credential/node policies and attachments have their own precedence; retrieve the current documents and attachments rather than replacing them with a single guessed rule.

OpenTelemetry and log streaming can send execution data outside the instance. Verify the intended destination and event selection; tests send actual traffic. Do not enable broad logging just because the task asks to fix one workflow.

## Source control, packages and promotions

Read source-control status and relevant version-specific docs. Pull, push, package apply and promotion operations can change many resources and live versions. Establish source, destination, branch, project selection, dependencies, credential matching, variable inclusion, conflict policy and publish policy. Export with the narrowest selection that matches the task. Review before applying to the destination.

Handle package multipart uploads using `--form` and `--file`; download exports using `--download`. Inspect package dependencies and manifest before import. Files can include expressions and variable values even when credential passwords are excluded. An exported package is not a complete instance backup.

For apply/continue flows, inspect the response and unresolved bindings/conflicts. Do not loop through continuation calls with guessed answers. Continue only after resolving the specific state returned by the server, with a bounded stopping condition. Never choose hard deletion, overwrite or publish-all solely to make an import succeed.

## Settings outside public API coverage

No public API catalog can promise every editor or host action. Billing/license procurement, interactive OAuth consent, some UI settings, provider setup, external secret-vault setup, storage configuration, scaling, upgrades and disaster recovery may need the UI, server CLI, infrastructure files or another service's documented API. Consult [server-operations.md](server-operations.md) and official version-matched documentation. MCP is optional background knowledge only; this package never relies on it.
