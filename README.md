# metaopt-preflight

One-shot, idempotent preflight skill that validates backend connectivity, repository
readiness, and environment prerequisites before launching an
[ml-metaoptimization](../ml-metaoptimization) campaign.

`ml-metaoptimization` is the downstream integration target.
This project is a **separate** skill—it runs once, produces a persisted readiness
artifact, and exits. The orchestrator consumes that artifact to gate campaign start.

## Relationship to ml-metaoptimization

| Aspect | metaopt-preflight | ml-metaoptimization |
|--------|-------------------|---------------------|
| Lifecycle | One-shot | Resumable control loop |
| Output | Readiness artifact | Campaign state |
| Invocation | Before campaign | During campaign |
| State mutation | Bounded bootstrap only | Yes |

## Project layout

```
metaopt-preflight/
├── agents/         # Agent catalog metadata
├── references/     # Authoritative reference docs and contracts
├── scripts/        # Preflight check implementations
├── tests/          # Validation and unit tests
├── SKILL.md        # Skill contract (input/output, rules)
└── README.md       # This file
```

## Status

Scaffold only — skill implementation is tracked in subsequent tasks.

See [SKILL.md](SKILL.md) for the skill contract.
