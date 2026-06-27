---
name: skill-creator
description: >-
  Guide for creating, editing, and packaging Agent Skills. Use when the user wants to
  build a new skill, improve or refactor an existing skill, fix a SKILL.md frontmatter or
  description, decide what belongs in scripts vs reference files, validate a skill's
  structure, or package a skill for distribution. Covers the SKILL.md format, the
  name/description frontmatter rules, progressive disclosure, and the init/package helper
  scripts in this skill's scripts/ directory.
---

# Skill Creator

A meta-skill: it helps you author other skills. Use it whenever you are creating a new
skill, improving an existing one, or packaging a skill to share.

> Note: This copy was reconstructed to match Anthropic's official `skill-creator`
> behavior and conventions. If you have network access to the upstream
> `anthropics/skills` repository, you can replace this directory with the official
> version verbatim — the workflow and file layout are intentionally the same.

## What a skill is

A skill is a directory that packages instructions and (optionally) code/resources so an
agent can reliably do a specialized task. The only required file is `SKILL.md`:

```
my-skill/
├── SKILL.md            # required: frontmatter + instructions
├── scripts/            # optional: runnable helper code the agent executes
├── reference/          # optional: docs the agent reads only when needed
└── assets/             # optional: templates, examples, data files
```

`SKILL.md` has two parts:

1. **YAML frontmatter** — `name` and `description`. This is the ONLY part loaded into
   context up front, so it must be enough for the agent to decide *whether* to open the
   skill.
2. **Markdown body** — the actual instructions, loaded only after the skill is triggered.

## The golden rule: progressive disclosure

Context is scarce. Load the minimum, defer the rest.

- **Frontmatter (`description`)** is always in context → keep it tight but trigger-rich.
- **SKILL.md body** loads when the skill fires → put the core workflow here.
- **`reference/*.md`** loads only when the body tells the agent to read it → put long
  specs, edge-case tables, API details, and rarely-needed depth here.
- **`scripts/*`** are executed, not read into context → put deterministic, repeatable
  operations here instead of describing them in prose.

Rule of thumb: if SKILL.md is getting long (> ~500 lines) or full of reference tables,
move depth into `reference/` and point to it.

## Frontmatter rules (this is where most skills fail)

```yaml
---
name: my-skill
description: >-
  What the skill does, AND the concrete situations that should trigger it.
---
```

- **`name`**: lowercase, hyphen-separated, matches the directory name. No spaces.
- **`description`**: the single most important field. It is the agent's only basis for
  deciding to use the skill. It must answer two things:
  1. *What does this skill do?*
  2. *When should it be used?* — list concrete trigger phrases, tasks, and situations.
- Write the description in the **third person** ("Use when the user…", not "I help you…").
- Front-load trigger keywords a user would actually say.
- Keep it to a few sentences; long enough to disambiguate, short enough to stay cheap.

Weak: `description: Helps with PDFs.`
Strong: `description: Extract text and tables from PDF files, fill PDF forms, merge/split
PDFs, and convert PDFs to images. Use when the user uploads a PDF, asks to read or parse a
PDF, fill a form, or combine/split PDF documents.`

## Workflow for creating a skill

1. **Understand the task.** What real job should this skill let an agent do reliably?
   Collect concrete example requests that should trigger it. If unclear, ask.
2. **Scaffold it.** Run the init script:
   ```
   python scripts/init_skill.py <skill-name> --path <skills-dir>
   ```
   This creates the directory, a template `SKILL.md`, and empty `scripts/`, `reference/`,
   `assets/` folders (drop ones you don't need).
3. **Write the body.** Start with a one-paragraph "what this does", then the step-by-step
   procedure. Prefer numbered steps and short imperative sentences over essays.
4. **Decide what becomes a script vs prose.** Anything deterministic, repeatable, or
   error-prone by hand (validation, parsing, file generation, packaging) → a script. Keep
   prose for judgment and orchestration.
5. **Push depth into `reference/`.** Long specs, option tables, and edge cases go in
   reference files the body links to ("for the full option list, read
   `reference/options.md`").
6. **Tighten the frontmatter.** Rewrite the `description` last, once you know exactly what
   the skill does and when it fires. This is the highest-leverage edit.
7. **Validate.** Run the package script in check mode (see below) and fix what it flags.
8. **Test.** Try the trigger phrases. Does an agent reach for the skill? Does the body get
   it to a correct result without re-deriving everything?

## Editing or improving an existing skill

- Read the current `SKILL.md` first. Diagnose before rewriting.
- Most common problems: a vague `description` (won't trigger), everything crammed into the
  body (should be split into `reference/`), and prose describing steps that should be a
  script.
- Preserve the `name`/directory match. If you rename, rename both.

## Packaging a skill for distribution

```
python scripts/package_skill.py <path-to-skill-dir>
```

This validates the skill (frontmatter present, `name` matches the directory, description
non-trivial, no obvious structural issues) and produces a `<name>.zip` you can share or
upload. Run it with `--check` to validate without zipping.

## Quality checklist

- [ ] `name` is lowercase-hyphenated and equals the directory name.
- [ ] `description` says **what** it does **and when** to use it, with real trigger words.
- [ ] Body opens with a one-paragraph summary, then concrete numbered steps.
- [ ] Deterministic/repeatable operations live in `scripts/`, not prose.
- [ ] Long reference material lives in `reference/`, loaded on demand.
- [ ] SKILL.md is focused (not a dumping ground); depth is deferred.
- [ ] `python scripts/package_skill.py <dir> --check` passes.

## See also

- `reference/skill-authoring-guide.md` — deeper guidance, anti-patterns, and worked
  examples (read when you need more than the checklist above).
