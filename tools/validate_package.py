"""Offline package integrity checks, no dependencies."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
plugin = json.loads((ROOT / "plugin.json").read_text())
marketplace = json.loads((ROOT / ".github/plugin/marketplace.json").read_text())
assert plugin["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
assert marketplace["plugins"][0]["name"] == plugin["name"]
assert marketplace["plugins"][0]["version"] == plugin["version"]
assert marketplace["plugins"][0]["source"] == "./"
assert not {"mcpServers", "hooks"} & plugin.keys()
assert not (ROOT / "mcp.json").exists()
skill = ROOT / "skills/n8n/SKILL.md"
text = skill.read_text(encoding="utf-8")
assert text.startswith("---\nname: n8n\ndescription: ")
for file in [ROOT / "README.md", *ROOT.glob("skills/**/*.md")]:
    for link in re.findall(r"\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
        if "://" not in link and not link.startswith("#"):
            assert (file.parent / link.split("#")[0]).is_file(), (file, link)
catalog = json.loads((ROOT / "skills/n8n/scripts/operations.json").read_text())
assert len(catalog["operations"]) == 172
assert (ROOT / "skills/n8n/scripts/N8N-LICENSE.md").is_file()
for name, op in catalog["operations"].items():
    expected = set(re.findall(r"{([^}]+)}", op["path"]))
    provided = {p["name"] for p in op["parameters"] if p["in"] == "path"}
    assert expected == provided, name
    assert not op["content_types"] or op["body_schema"] is not None or op["multipart_schema"] is not None, name
print("Package valid: manifest, marketplace, skill references, licenses and 172 operation contracts")
