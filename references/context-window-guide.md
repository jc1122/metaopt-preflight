# Context Window Guide for Preflight

This document tells the preflight agent exactly which files to read, when,
and which files to skip entirely. Preflight is a one-shot agent — it reads
docs once, runs checks, and emits a readiness artifact. There is no
multi-turn loop and no re-entry, so the guide is simple.

---

## TL;DR — read this, skip everything else

| Moment | Must read | Must NOT read |
|---|---|---|
| Every invocation | `SKILL.md`, `references/readiness-artifact.md`, campaign YAML | `tests/`, `scripts/bootstrap/`, orchestrator source, this file |

---

## ALWAYS READ (on every invocation)

Read these at the start of every run:

| File | Why |
|---|---|
| `SKILL.md` | Input contract, lifecycle phases, output schema, behavioral rules |
| `references/readiness-artifact.md` | Exact artifact schema you must emit, freshness rules, field semantics |
| Campaign YAML (path from `--campaign` arg) | The file you are validating — needed for hash computation and check scoping |

These three sources are everything you need to execute the full
Gather → Evaluate → Bootstrap → Emit lifecycle. Do not skip any of them.

---

## READ IF NEEDED (conditional)

Only read these if you hit a specific problem during the run:

| File | When to read |
|---|---|
| `references/repo-setup.md` | Debugging which R-check failed or what a repo bootstrap mutation should do |
| `references/backend-setup.md` | Debugging which backend check failed or what remediation to suggest |
| `references/boundary.md` | Clarifying scope — does this action belong in preflight or in the orchestrator? |
| `scripts/checks/repo_checks.py` | A repo check result is unexpected and you need to inspect the implementation |
| `scripts/checks/backend_checks.py` | A backend check result is unexpected and you need to inspect the implementation |

Most runs will not need any of these. Reach for them only when a check
behaves in a way that the SKILL.md description does not explain.

---

## NEVER READ (skip these entirely)

| File / path | Reason to skip |
|---|---|
| `tests/` | Test files are not needed during a preflight run |
| `scripts/bootstrap/` | Bootstrap runs automatically via the check pipeline; you don't invoke or read it directly |
| `/home/jakub/projects/ml-metaoptimization/` | Preflight does not need orchestrator source — the interface is the readiness artifact only |
| `references/context-window-guide.md` | This file itself — you are already following it |

---

## Context budget note

Preflight is small. All ALWAYS READ docs fit comfortably in a single
context window:

| Source | Approx size |
|---|---|
| `SKILL.md` | ~200 lines |
| `references/readiness-artifact.md` | ~100 lines |
| Campaign YAML | Typically < 50 lines |
| **Total before check results** | **~2000–4000 tokens** |

There is no multi-turn accumulation — the agent reads once, executes, and
exits. Context pressure is not a concern for this skill.
