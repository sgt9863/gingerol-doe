#!/usr/bin/env python3
"""Scaffold a new skill directory from a template.

Creates <path>/<skill-name>/ containing a template SKILL.md plus empty
scripts/, reference/, and assets/ subdirectories. Delete the subdirectories
you don't need.

Usage:
    python init_skill.py <skill-name> [--path SKILLS_DIR] [--force]

Examples:
    python init_skill.py pdf-tools
    python init_skill.py pdf-tools --path .claude/skills
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

TEMPLATE = """\
---
name: {name}
description: >-
  TODO: one or two sentences on WHAT this skill does, AND the concrete situations
  that should trigger it (real user phrasings, tasks, file types). Write in the third
  person, e.g. "Use when the user wants to ...".
---

# {title}

## What this does
TODO: one paragraph summary of the job this skill lets an agent do reliably.

## When to use
- TODO: concrete trigger situation
- TODO: another trigger situation

## Steps
1. TODO: first concrete step.
2. TODO: next step. Prefer short imperative sentences.

## Notes
- Put deterministic/repeatable operations in scripts/ instead of describing them here.
- Put long reference material in reference/ and link to it; keep this file focused.
"""


def title_from_name(name: str) -> str:
    return " ".join(word.capitalize() for word in name.split("-"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new skill directory.")
    parser.add_argument("name", help="skill name: lowercase, hyphen-separated")
    parser.add_argument(
        "--path",
        default=".",
        help="parent directory to create the skill in (default: current dir)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow writing into an existing skill directory",
    )
    args = parser.parse_args(argv)

    name = args.name.strip()
    if not NAME_RE.match(name):
        print(
            f"error: invalid skill name {name!r}. "
            "Use lowercase letters, digits, and hyphens (e.g. 'pdf-tools').",
            file=sys.stderr,
        )
        return 2

    skill_dir = Path(args.path).expanduser() / name
    skill_md = skill_dir / "SKILL.md"

    if skill_md.exists() and not args.force:
        print(
            f"error: {skill_md} already exists. Use --force to overwrite the template.",
            file=sys.stderr,
        )
        return 1

    for sub in ("scripts", "reference", "assets"):
        (skill_dir / sub).mkdir(parents=True, exist_ok=True)

    skill_md.write_text(
        TEMPLATE.format(name=name, title=title_from_name(name)), encoding="utf-8"
    )

    print(f"Created skill scaffold at {skill_dir}/")
    print(f"  - {skill_md}")
    print("  - scripts/  reference/  assets/  (delete the ones you don't need)")
    print("\nNext: edit SKILL.md, then validate with:")
    print(f"  python {Path(__file__).with_name('package_skill.py')} {skill_dir} --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
