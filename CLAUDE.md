# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **French-language training curriculum** teaching professional use of Claude Code. It is **content only** — no code, no build system, no tests. All material lives in `formation-claude-code/` as Markdown files.

- `README.md` — course overview, audience, prerequisites, module index (~20 h total)
- `01-…` through `09-…` — nine sequential modules (fondamentaux → adoption équipe)
- `10-evaluation-projet-final.md` — final exam (quiz + hands-on project) with graded rubric

## Authoring conventions

Every module follows the same fixed structure — preserve it when editing or adding a module:

1. `# Module N — Titre (durée)`
2. `## Objectifs` — 3 bullets, learner-outcome phrasing
3. Numbered `## N. Section` bodies mixing theory, tables (surfaces/commands/etc.), and short code fences
4. `## TP guidé (durée)` — a numbered practical exercise on the participant's sample repo
5. `## Checklist de validation` — `- [ ]` self-check items in first person ("Je sais…")

Cross-module references use relative links to sibling files (e.g. `(module 3)` in prose, `[…](02-contexte-et-memoire.md)` in the README table). Keep the README table's durations in sync with the `(N h)` in each module heading.

## Style rules for content

- **Language: French throughout.** Do not switch to English mid-sentence. Technical terms in English are fine when idiomatic (`plan mode`, `headless`, `allowlist`).
- Tone is professional-pedagogical, targets working developers — concise, opinionated, prescriptive ("Réflexe professionnel n° 1 : …"). Avoid marketing tone.
- Prefer tables for enumerations (commands, surfaces, permission rules) — this is the established pattern.
- ❌ / ✅ pairs are used to contrast bad vs. good examples; keep that convention.
- Code fences use ` ```bash ` for shell and are kept short — this is training material, not a reference manual.

## Factual accuracy

Content describes Claude Code features (permission modes, `/clear` vs `/compact`, hooks, skills, sub-agents, MCP, headless `claude -p`, Agent SDK). When editing, verify claims against current Claude Code behavior — outdated flag names or command syntax in a *training* doc is worse than in normal code because learners copy it verbatim. The final-module quiz answers must stay consistent with the module bodies.

## No build / no tests (formation-claude-code only)

For the training curriculum in `formation-claude-code/` there is nothing to compile or run. "Verifying a change" means: read the edited Markdown end-to-end, check internal links resolve, and confirm the module still fits its stated duration.

## GitSky code development (Template-book/ + src/)

The repo also hosts the **GitSky** startup-factory project: the book lives in `Template-book/` and its implementation code is being built out. These rules apply to all GitSky code work:

- **All code goes in a `src/` directory.** Every source file you write for GitSky lives under `src/` — never scatter code elsewhere in the repo.
- **Always design a test for the code you create, and run it to validate your work.** Before considering a task done, think about how to exercise the code end-to-end. Tests failing at the start of development is expected and normal.
- **Never cheat by weakening or rewriting tests to make failing code pass.** If your code fails a test, fix the code — not the test. A test only changes when its intent is genuinely wrong, and then you say so explicitly.
- **The book is the source of truth.** If development diverges from the plan as described in the book (`Template-book/`), stop and ask for the user's opinion *before* changing the book to match. Do not silently update the book to paper over a divergence.
