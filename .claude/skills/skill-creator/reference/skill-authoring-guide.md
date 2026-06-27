# Skill authoring guide (deep reference)

Read this when the SKILL.md checklist isn't enough — when you're designing a non-trivial
skill, debugging why a skill never triggers, or deciding how to split a large skill.

## How skills load (and why structure matters)

An agent does not read every skill's body all the time. It sees only the **frontmatter
`description`** of each available skill. When a task matches, it opens that skill's
`SKILL.md` body. Files under `reference/` are read only when the body explicitly tells the
agent to. Files under `scripts/` are executed, never loaded as prose.

This three-tier loading — description → body → reference/scripts — is **progressive
disclosure**. Design every skill around it:

| Tier | Always in context? | Put here |
|------|--------------------|----------|
| `description` | Yes (cheap, every turn) | What it does + when to trigger |
| `SKILL.md` body | Only after trigger | Core workflow, the 80% path |
| `reference/*` | Only when body links to it | Specs, tables, edge cases, depth |
| `scripts/*` | Never (executed) | Deterministic, repeatable operations |

## Writing descriptions that actually trigger

The `description` is matched against the user's request. If it doesn't contain the words
and situations the user would use, the skill stays dormant.

Do:
- Lead with concrete capabilities and the nouns/verbs users say ("PDF", "merge", "fill a
  form").
- Include an explicit "Use when …" clause listing trigger situations.
- Write in the third person.
- Cover synonyms and adjacent phrasings the user might use.

Avoid:
- Vague verbs ("helps with", "handles", "deals with").
- Describing the *implementation* instead of the *trigger* ("uses pdfplumber" tells the
  agent nothing about when to fire).
- First person ("I can …").

### Before / after

Before:
```yaml
description: A skill for working with spreadsheets.
```
After:
```yaml
description: >-
  Read, write, and analyze Excel and CSV files — extract sheets, compute summaries,
  filter/pivot rows, and generate charts. Use when the user uploads an .xlsx or .csv,
  asks to analyze tabular data, build a pivot, or produce a spreadsheet report.
```

## Scripts vs prose: where to draw the line

Put it in a **script** when the operation is:
- deterministic (same input → same output),
- repeated or looped,
- error-prone to do by hand (parsing, validation, byte-level file ops),
- verifiable (you can check the exit code / output).

Keep it in **prose** when it requires judgment, ordering decisions, or adapting to the
specific request. The body should orchestrate; scripts should execute.

A good script: single clear purpose, argparse CLI, helpful `--help`, non-zero exit on
failure, no surprise side effects, minimal dependencies (prefer the standard library so
the script runs anywhere).

## Splitting a large skill

If SKILL.md drifts past ~500 lines or fills with reference tables:
- Move option catalogs, API field lists, and edge-case matrices into `reference/`.
- Have the body say *when* to read each reference file, not *what's in it*.
- Keep the body to the main path plus pointers. The agent pulls depth on demand.

## Common anti-patterns

- **The kitchen-sink body** — everything inlined, nothing deferred. Burns context and
  buries the workflow. Fix: split into `reference/`.
- **The mystery description** — too vague to trigger, or describes internals. Fix: rewrite
  around what/when with real trigger words.
- **Prose pretending to be code** — step-by-step instructions for a deterministic
  transformation. Fix: write a script.
- **Name/dir mismatch** — `name:` in frontmatter ≠ directory name. Breaks loading. Fix:
  make them identical.
- **Stale TODOs** — template placeholders left in the description. Fix: the package script
  flags these; rewrite before shipping.

## Validate and package

From the skill-creator's `scripts/` directory:

```
python package_skill.py <skill-dir> --check   # validate only
python package_skill.py <skill-dir>           # validate + write <name>.zip
```

The validator checks frontmatter presence, name/dir match, lowercase-hyphenated name, and
a non-trivial description. Fix everything it reports before distributing.

## A minimal good skill, end to end

```
weather-report/
└── SKILL.md
```
```yaml
---
name: weather-report
description: >-
  Fetch and summarize current weather and short-term forecasts for a city or
  coordinates. Use when the user asks for the weather, temperature, rain chance, or a
  forecast for a place.
---

# Weather Report

## What this does
Given a location, fetch current conditions and a short forecast and summarize them plainly.

## Steps
1. Resolve the location to coordinates if needed.
2. Call the weather API (see reference/api.md for the endpoint and fields).
3. Summarize: current temp, conditions, and the next-24h outlook in 2–3 sentences.
```

Small, single-purpose, triggers cleanly, defers API detail to a reference file. Most good
skills look like this — not like frameworks.
