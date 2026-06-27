#!/usr/bin/env python3
"""Validate a skill and (optionally) package it into a distributable zip.

Validation checks:
  - SKILL.md exists
  - frontmatter is present and well-formed (--- ... ---)
  - 'name' and 'description' keys exist
  - 'name' matches the skill directory name
  - 'name' is lowercase-hyphenated
  - 'description' is non-trivial (length and not a leftover TODO)

Usage:
    python package_skill.py <path-to-skill-dir>            # validate + write <name>.zip
    python package_skill.py <path-to-skill-dir> --check    # validate only
    python package_skill.py <path-to-skill-dir> -o out.zip # custom output path
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MIN_DESCRIPTION_LEN = 40


def parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal top-level YAML frontmatter parser (no external deps).

    Handles simple `key: value` pairs and YAML block scalars introduced by
    `>-`, `>`, `|`, or `|-` on the key line. Good enough to validate name/description.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing frontmatter: file must start with '---'")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("frontmatter not closed: no terminating '---'")

    body = lines[1:end]
    data: dict[str, str] = {}
    i = 0
    key_re = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
    while i < len(body):
        line = body[i]
        m = key_re.match(line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest in (">", ">-", "|", "|-"):
            # block scalar: gather following more-indented lines
            collected: list[str] = []
            i += 1
            while i < len(body) and (body[i].startswith((" ", "\t")) or body[i] == ""):
                collected.append(body[i].strip())
                i += 1
            sep = "\n" if rest.startswith("|") else " "
            data[key] = sep.join(c for c in collected if c != "").strip()
            continue
        data[key] = rest.strip().strip('"').strip("'")
        i += 1
    return data


def validate(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"no SKILL.md found in {skill_dir}"]

    try:
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [str(exc)]

    name = fm.get("name", "")
    desc = fm.get("description", "")

    if not name:
        errors.append("frontmatter missing 'name'")
    else:
        if not NAME_RE.match(name):
            errors.append(f"'name' {name!r} must be lowercase-hyphenated")
        if name != skill_dir.name:
            errors.append(
                f"'name' {name!r} does not match directory name {skill_dir.name!r}"
            )

    if not desc:
        errors.append("frontmatter missing 'description'")
    else:
        if len(desc) < MIN_DESCRIPTION_LEN:
            errors.append(
                f"'description' is too short ({len(desc)} chars); say what it does AND "
                "when to use it"
            )
        if "TODO" in desc:
            errors.append("'description' still contains a TODO placeholder")

    return errors


def make_zip(skill_dir: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir():
                continue
            if "__pycache__" in path.parts or path.name == ".DS_Store":
                continue
            arcname = Path(skill_dir.name) / path.relative_to(skill_dir)
            zf.write(path, arcname)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and package a skill.")
    parser.add_argument("skill_dir", help="path to the skill directory")
    parser.add_argument(
        "--check", action="store_true", help="validate only, do not write a zip"
    )
    parser.add_argument("-o", "--output", help="output zip path (default: <name>.zip)")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir).expanduser().resolve()
    if not skill_dir.is_dir():
        print(f"error: {skill_dir} is not a directory", file=sys.stderr)
        return 2

    errors = validate(skill_dir)
    if errors:
        print(f"VALIDATION FAILED for {skill_dir.name}:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {skill_dir.name} passed validation.")
    if args.check:
        return 0

    out = Path(args.output) if args.output else skill_dir.parent / f"{skill_dir.name}.zip"
    make_zip(skill_dir, out)
    print(f"Packaged -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
