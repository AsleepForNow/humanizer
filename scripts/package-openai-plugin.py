#!/usr/bin/env python3
"""Export the root Humanizer skill as a portable skills-only plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="ZIP path outside the source repository")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error("Write the archive outside the source repository")
    if output.suffix.lower() != ".zip":
        parser.error("Use a .zip output filename")

    skill = (ROOT / "SKILL.md").read_bytes()
    text = skill.decode("utf-8")
    metadata = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if metadata is None:
        raise SystemExit("SKILL.md needs YAML frontmatter")
    version = re.search(r'(?m)^  version: "([0-9]+\.[0-9]+\.[0-9]+)"$', metadata[1])
    if version is None or not re.search(r"(?m)^name: humanizer$", metadata[1]):
        raise SystemExit("Check the skill name and metadata.version")
    numbers = [int(n) for n in re.findall(r"(?m)^### ([0-9]+)\. ", text)]
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        raise SystemExit("Skill patterns must be numbered without gaps")

    manifest = json.loads((ROOT / "openai/plugin.json").read_text(encoding="utf-8"))
    if manifest.get("$schema") != SCHEMA or manifest.get("name") != "humanizer":
        raise SystemExit("Check the portable plugin schema and name")
    if manifest.get("version") != version[1]:
        raise SystemExit("Match the portable plugin version to the source skill")
    if any(key in manifest for key in ("skills", "mcpServers", "apps", "interface")):
        raise SystemExit("Portable components use fixed paths and extensions.com.openai")
    interface = manifest["extensions"]["com.openai"]["interface"]
    for field in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
        if not isinstance(interface.get(field), str) or not interface[field].strip():
            raise SystemExit(f"Provide a nonblank interface.{field}")
    if len(interface["shortDescription"]) > 30 or interface["category"] != "Productivity":
        raise SystemExit("Check the subtitle length and listing category")
    if interface.get("capabilities") != []:
        raise SystemExit("This plugin has no server or interactive view")
    prompts = interface["defaultPrompt"]
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        raise SystemExit("Provide one to three default prompts")
    if any(not isinstance(p, str) or not p.strip() or len(p) > 128 or "\n" in p for p in prompts):
        raise SystemExit("Default prompts must be nonblank single lines of at most 128 characters")

    entries = {
        "plugin.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "skills/humanizer/SKILL.md": skill,
        "skills/humanizer/agents/openai.yaml": (ROOT / "agents/openai.yaml").read_bytes(),
        "assets/humanizer.svg": (ROOT / "openai/humanizer.svg").read_bytes(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
    }
    for key in ("logo", "composerIcon"):
        if interface[key].removeprefix("./") not in entries:
            raise SystemExit(f"Include the referenced {key}")
    for source in ("SKILL.md", "agents/openai.yaml", "LICENSE", "openai/plugin.json", "openai/humanizer.svg"):
        if (ROOT / source).is_symlink():
            raise SystemExit(f"Package regular files only: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(entries):
            raise SystemExit("Archive verification failed")
        if archive.read("skills/humanizer/SKILL.md") != skill:
            raise SystemExit("The exported skill must match the source exactly")
        json.loads(archive.read("plugin.json"))
    print(json.dumps({
        "archive": str(output), "version": version[1], "patterns": len(numbers),
        "files": sorted(entries), "source_skill_unchanged": True,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
