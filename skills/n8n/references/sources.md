# Sources and compatibility

Reviewed 2026-10-27. Public API catalog compiled from released n8n **2.45.4**, commit [`e0c02a617f5e6ede3d6c448aff41f632a782aaca`](https://github.com/n8n-io/n8n/tree/e0c02a617f5e6ede3d6c448aff41f632a782aaca/packages/cli/src/public-api/v1). Contains 172 operations and their input contracts, not the response schemas or implementation. It includes licensed and preview/beta endpoints. A catalog entry is not evidence of entitlement or deployment support.

- [n8n public API overview](https://docs.n8n.io/api/), [endpoint reference](https://docs.n8n.io/api/api-reference/), [authentication and scopes](https://docs.n8n.io/api/authentication/), [pagination](https://docs.n8n.io/api/pagination/).
- [Workflow documentation](https://docs.n8n.io/workflows/), [built-in nodes](https://docs.n8n.io/integrations/builtin/), [expressions](https://docs.n8n.io/code/expressions/), [data structure](https://docs.n8n.io/data/data-structure/).
- [Server CLI](https://docs.n8n.io/hosting/cli-commands/), [environment variables](https://docs.n8n.io/hosting/configuration/environment-variables/), [queue mode](https://docs.n8n.io/hosting/scaling/queue-mode/).
- [n8n release history](https://github.com/n8n-io/n8n/releases). Match docs to the actual version before host changes or use of newer API families.
- [Copilot plugin creation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-creating) and [plugin/marketplace reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference). Uses portable Agent Plugins 1.0 with `skills/n8n/SKILL.md` and no MCP configuration.

Use the instance's `/api/v1/discover?include=schemas` when supported to see scope-filtered capabilities and request schemas. On self-hosted versions with the built-in API playground, inspect its version-specific OpenAPI definition. Do not assume undocumented endpoints exist on Cloud or older instances.

## Updating the catalog

Maintainers can compile a local, pinned n8n OpenAPI source tree with `tools/build_catalog.py`. Only this maintenance command requires PyYAML; the distributed runtime does not. The compiler resolves local references, removes upstream descriptions/examples and response schemas, preserves input constraints, rejects recursive input references and uses YAML 1.2-style boolean parsing. Review catalog diffs, run the tests and update the recorded version and documentation before publishing. Do not auto-refresh the catalog at runtime.

For a one-off different instance version, a separately compiled catalog can be selected using `python TOOL --catalog FILE ...`. If an older source tree is structurally different, adapt the compiler and verify it rather than assuming compilation proves compatibility.

The compiled catalog is a modified extraction of n8n's OpenAPI material. Its original licensing is preserved in `scripts/N8N-LICENSE.md`. The skill instructions and Python implementation are original MIT-licensed material; see the repository license notice. No upstream n8n server implementation is bundled.
