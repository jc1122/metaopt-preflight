# Context Window Guide for Preflight

This guide tells a Codex operator exactly which files to read before invoking
`metaopt-preflight`, when to reach for additional references, and which paths
to skip entirely. Preflight is a one-shot skill — it reads a small contract
surface, runs checks once, applies only bounded bootstrap mutations, and
overwrites the readiness artifact. There is no multi-turn loop, no resume, and
no need for a broad repository dump.

---

## TL;DR — first read, then stop

| Moment | Read first | Do not read by default |
|---|---|---|
| Every invocation | `README.md`, `SKILL.md`, campaign YAML | `tests/`, `scripts/bootstrap/`, downstream orchestrator source, broad repo listings |

---

## READ FIRST (on every invocation)

Read these in order at the start of every run:

| File | Why |
|---|---|
| `README.md` | Exact command shape (`--campaign`, optional `--cwd`) and high-level contract |
| `SKILL.md` | Lifecycle phases, one-shot/no-resume rules, output contract, behavioral rules |
| Campaign YAML (path from `--campaign` arg) | The file you are validating — needed for hash computation and check scoping |

These three sources are enough for a normal run. Do not start by dumping
additional docs or implementation files into context.

---

## READ IF NEEDED (conditional)

Only read these if you hit a specific problem during the run:

| File | When to read |
|---|---|
| `references/readiness-artifact.md` | You need exact field semantics, freshness rules, or overwrite/latest-wins details for `.ml-metaopt/preflight-readiness.json` |
| `references/repo-setup.md` | Debugging which R-check failed or what a repo bootstrap mutation should do |
| `references/backend-setup.md` | Debugging which backend check failed or what remediation to suggest |
| `references/boundary.md` | Clarifying scope — does this action belong in preflight or in the orchestrator? |
| `scripts/checks/repo_checks.py` | A repo check result is unexpected and you need to inspect the implementation |
| `scripts/checks/backend_checks.py` | A backend check result is unexpected and you need to inspect the implementation |

Most runs will not need any of these. Reach for them only when a check
behaves in a way that the SKILL.md description does not explain.

## Mutation guardrails at a glance

Allowed local filesystem side effects:

- Create `.ml-metaopt/` scaffolding, including `.ml-metaopt/artifacts/{code,data,manifests,patches}` and `.ml-metaopt/{handoffs,worker-results,tasks,executor-events}`.
- Create or update the project-root `.gitignore` so `.ml-metaopt/` is ignored.
- Overwrite `.ml-metaopt/preflight-readiness.json`. The latest artifact on disk is always authoritative.

Disallowed side effects:

- Writing `.ml-metaopt/state.json` or `AGENTS.md`.
- Modifying experiment code or other campaign-phase outputs.
- Creating commits or other git history changes.
- Creating remote backend resources.

---

## NEVER READ (skip these entirely)

| File / path | Reason to skip |
|---|---|
| `tests/` | Test files are not needed during a preflight run |
| `scripts/bootstrap/` | Bootstrap runs automatically via the check pipeline; you don't invoke or read it directly |
| `/home/jakub/projects/ml-metaoptimization/` | Preflight does not need orchestrator source — the interface is the readiness artifact only |
| Large repo-wide file listings | Broad dumps waste context and are unnecessary for a normal preflight invocation |

---

## Context budget note

Preflight is small. The READ FIRST set fits comfortably in a single
context window:

| Source | Approx size |
|---|---|
| `README.md` | ~160 lines |
| `SKILL.md` | ~200 lines |
| Campaign YAML | Typically < 50 lines |
| **Total before check results** | **~2000–4000 tokens** |

There is no multi-turn accumulation — the agent reads once, executes, writes
the latest readiness artifact, and exits. Context pressure stays low as long
as you avoid unnecessary repo-wide reads.
