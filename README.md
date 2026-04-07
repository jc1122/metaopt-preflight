# metaopt-preflight

One-shot, idempotent preflight skill that validates backend connectivity, repository
readiness, and environment prerequisites before launching an
[ml-metaoptimization](../ml-metaoptimization) campaign.

## Relationship to ml-metaoptimization

`ml-metaoptimization` is a **resumable deterministic state machine** that drives
the campaign loop (`LOAD_CAMPAIGN` → … → `COMPLETE`). It assumes the environment
is already ready when it starts.

`metaopt-preflight` is the **one-shot preparation phase** that runs before the
orchestrator. It evaluates readiness, performs bounded bootstrap mutations if
needed, and emits a persisted readiness artifact. The orchestrator consumes that
artifact to gate campaign entry. Once preflight exits, it plays no further role
in the campaign.

The two skills share no runtime state. Preflight never reads or writes
`.ml-metaopt/state.json`, and the orchestrator never re-invokes preflight.

| Aspect | metaopt-preflight | ml-metaoptimization |
|--------|-------------------|---------------------|
| Lifecycle | One-shot, no resume | Resumable control loop |
| Purpose | Environment/backend readiness | Campaign execution |
| Output | Readiness artifact | Campaign state, experiment results |
| Invocation | Before campaign | During campaign (possibly across reinvocations) |
| State mutation | Bounded bootstrap only | Full campaign state management |
| State files | None (artifact only) | `.ml-metaopt/state.json`, `AGENTS.md` hook |

## Ownership summary

**Preflight owns:** environment readiness evaluation, backend reachability
checks, bounded idempotent bootstrap mutations, persisted readiness signal.

**Preflight does NOT own:** campaign loop, proposal lifecycle, experiment
materialization/analysis, resumable state machine, worker dispatch.

See [SKILL.md](SKILL.md) for the full contract and
[references/boundary.md](references/boundary.md) for the authoritative boundary
and lifecycle specification.

## Project layout

```
metaopt-preflight/
├── agents/         # Agent catalog metadata
├── references/     # Authoritative reference docs and contracts
│   ├── boundary.md            # Ownership boundary and lifecycle
│   ├── readiness-artifact.md  # Readiness artifact schema and freshness rules
│   ├── backend-setup.md       # Backend setup contract and readiness conditions
│   └── repo-setup.md          # Repo setup contract and scaffolding mutations
├── scripts/        # Preflight check implementations
├── tests/          # Validation and unit tests
├── SKILL.md        # Skill contract (input/output, rules)
└── README.md       # This file
```

## Validation

Run the contract-doc validation tests (stdlib-only, no extra dependencies):

```
python -m unittest tests.test_contract_docs -v
```

These tests verify that reference docs, SKILL.md, and example fixtures stay
aligned on the public contract (artifact path, required fields, one-shot
lifecycle semantics, reference set completeness).

## Status

Ownership boundary, readiness artifact contract, backend setup contract, and
repo setup contract defined. Input contract and check catalog are deferred to
later tasks.
