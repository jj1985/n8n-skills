# n8n skills for GitHub Copilot

Create, edit and troubleshoot workflows, configure n8n and administer licensed instances through deterministic Python REST tools. **No MCP, Node.js server or third-party Python runtime dependencies.**

The package includes all **172 public API operations in n8n 2.45.4**, pinned to a released source commit, plus guidance for host configuration, backups, upgrades, workers and actions that need the UI or Server CLI. Business and Enterprise operations are included; your instance's license, version, API scopes and role permissions determine availability.

## Install in Copilot CLI

Register this public marketplace and install its plugin:

```sh
copilot plugin marketplace add jj1985/n8n-skills
copilot plugin install n8n-api@jj1985-n8n
```

Or install the root plugin directly:

```sh
copilot plugin install jj1985/n8n-skills
```

Restart the session, then ask Copilot to use the n8n skill. Verify discovery with `copilot skill list`. Compatible Copilot clients that support Agent Plugins 1.0 can load the same package. For a client supporting skills but not plugins, copy the **whole** `skills/n8n` folder into its supported skill directory (for repository-scoped Copilot skills: `.github/skills/n8n`). Scripts, catalog, references, asset and license must travel together. This is a community marketplace, not a claim of listing or endorsement in GitHub's built-in marketplace.

## Configure

Requires Python **3.10+** with network access to n8n. Set `N8N_BASE_URL` to your instance URL or its `/api/v1` root. Inject `N8N_API_KEY` into the environment from a secret store or local environment configuration. Create the key in n8n's API settings with the relevant scopes. Do not commit a key or paste it into a prompt. An n8n license is separate from this plugin.

Optional: `N8N_CA_FILE` for a private CA. `--api-key-env` allows choosing another environment variable. HTTPS is verified; trusted plain HTTP connections require `--allow-http` explicitly.

Example prompts:

- “Use n8n to build an inactive workflow that receives a webhook and validates its input.”
- “Update workflow abc123 as a draft and explain what needs testing before publication.”
- “Inspect failed executions for this workflow and identify the failing node.”
- “Configure OIDC for our licensed n8n instance using the settings I provided.”
- “Prepare a package promotion between our staging and production projects.”
- “Review our self-hosted queue configuration and prepare the required changes.”

## Python CLI

From a clone of this repository:

```sh
python skills/n8n/scripts/n8n_api.py operations --search Workflow
python skills/n8n/scripts/n8n_api.py describe createWorkflow
python skills/n8n/scripts/n8n_api.py workflow validate skills/n8n/assets/manual-pass-through.json
python skills/n8n/scripts/n8n_api.py call getWorkflows --query limit=100 --all-pages
python skills/n8n/scripts/n8n_api.py call createWorkflow --body skills/n8n/assets/manual-pass-through.json
# Apply only when creating this workflow on the selected instance is intended:
python skills/n8n/scripts/n8n_api.py call createWorkflow --body skills/n8n/assets/manual-pass-through.json --apply
```

Writes preview by default; reads execute immediately. `--dry-run` also previews reads. `--apply` sends one request, with no automatic retries. Named operations validate parameters and structural input constraints. `describe` exposes machine-readable schemas to agents. JSON results distinguish previews, success and failure. See the [complete CLI contract](skills/n8n/references/python-tools.md).

Built-in helpers include workflow graph validation and payload preparation, cursor pagination, environment-bound secret fields, package multipart uploads, binary downloads, webhook invocation without forwarding the API key, and health checks. A verified raw public-API request command covers endpoints on other n8n versions. Mutations, webhook invocations and evaluation execution remain subject to the user's authorization.

The workflow update helper defaults to `publishIfActive=false` because current n8n otherwise republishes changes to published workflows. This behavior is visible in the preview. An explicit `--query publishIfActive=true` requests the server's live-update behavior.

## Coverage and limits

Workflow lifecycle/history, executions, credentials, users/projects/roles, role mapping, tags, variables, folders, data tables/rows/columns, community packages, evaluations, insights, audits, LDAP, SAML, OIDC, security policies, OpenTelemetry, log streaming, node/credential policies, source control, promotions and package import/export are included. [Administration routing](skills/n8n/references/administration.md) maps these to discoverable API families.

No public API exposes every possible host, editor or external-provider interaction. [Server operations guidance](skills/n8n/references/server-operations.md) covers those boundaries without depending on MCP or undocumented editor endpoints. The package doesn't automatically provision infrastructure, complete OAuth consent, modify billing or install licensed features.

The catalog targets 2.45.4, not an assertion of compatibility with every version. Query `getDiscover` where available. The client checks structure, not the validity of every node's parameters, expressions or downstream behavior. Save acceptance and end-to-end success are distinct. No universal public workflow execution endpoint is invented.

Secret-key redaction is best effort. Full output/download files are deliberately unredacted, never overwritten and should live in a protected directory. No telemetry, background service or install hooks are included.

## Development and verification

```sh
python -m unittest discover -s tests -v
python tools/validate_package.py
```

Tests use a local HTTP fixture and offline requests; no n8n credentials are required. They test request construction, mutation previews, draft defaults, validation, errors, pagination, redirects, secrets, webhooks and file transfer. A live licensed instance is still needed for integration acceptance of its node types and business workflows.

Release 1.0.1 also incorporates live testing on n8n 2.45.4: workflow create/read/update, publish/unpublish, protected webhook execution, execution/history inspection, archive/unarchive, credential create/delete, tag association and data-table row insertion/read/deletion. Temporary resources were cleaned up. This verifies those paths on one deployment, not every licensed operation. Live testing identified the server's 24-character tag-name limit and export-only workflow metadata; the client now handles both, with regression tests. The offline suite contains 46 tests.

To update the catalog, install PyYAML in a maintainer environment, obtain a pinned n8n source tree, and run:

```sh
python tools/build_catalog.py /path/to/n8n/packages/cli/src/public-api/v1 skills/n8n/scripts/operations.json --revision COMMIT_SHA --version VERSION
```

Review changes, update compatibility references and run tests before release. The runtime remains dependency-free.

## License and attribution

Original Python code, skill instructions and packaging: MIT, copyright 2026 jj1985. The compiled API catalog is a modified extraction from n8n's OpenAPI definitions and retains n8n's **Sustainable Use License 1.0**, included [beside the catalog](skills/n8n/scripts/N8N-LICENSE.md). The package therefore contains mixed-license material; the upstream catalog is not relicensed as MIT. n8n and GitHub Copilot are their respective owners' marks. This project is independent and is not an official n8n or GitHub product.
