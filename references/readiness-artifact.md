# Readiness Artifact Contract

This document defines the schema, semantics, freshness rules, and persistence
conventions for the machine-readable readiness artifact emitted by
`metaopt-preflight` and consumed by `ml-metaoptimization`.

For preflight ownership and lifecycle, see `references/boundary.md`.
For campaign identity and runtime hash definitions, see
`ml-metaoptimization/references/contracts.md`.

---

## Persistence

**Path:** `.ml-metaopt/preflight-readiness.json`

The artifact lives inside the `.ml-metaopt/` directory because it is part of
the campaign workspace managed jointly by the preflight and orchestrator
skills. Preflight is the sole writer; `ml-metaoptimization` is the sole
consumer.

Preflight may create the `.ml-metaopt/` directory as a bootstrap mutation if it
does not already exist.

---

## Overwrite / Latest-Wins Semantics

Every preflight invocation overwrites any previously emitted artifact at the
persistence path. The latest artifact on disk is always authoritative. There
is no history, no append log, and no merge with prior artifacts.

Consumers must treat the on-disk artifact as a point-in-time snapshot.

---

## Top-Level Schema

```json
{
  "schema_version": 1,
  "status": "READY",
  "campaign_id": "<string>",
  "campaign_identity_hash": "sha256:<64 hex chars>",
  "runtime_config_hash": "sha256:<64 hex chars>",
  "emitted_at": "<ISO 8601 timestamp>",
  "preflight_duration_seconds": 12.3,
  "checks_summary": {
    "total": 5,
    "passed": 4,
    "failed": 0,
    "bootstrapped": 1
  },
  "failures": [],
  "next_action": "proceed",
  "diagnostics": null
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | positive integer | Schema version of this artifact. Currently `1`. |
| `status` | string | Readiness outcome — see Status Semantics below. |
| `campaign_id` | string | Campaign identifier from the campaign spec. |
| `campaign_identity_hash` | string | Hash of the campaign identity payload, as defined by `ml-metaoptimization/references/contracts.md`. Format: `sha256:<64 lowercase hex chars>`. |
| `runtime_config_hash` | string | Hash of the runtime configuration payload, as defined by `ml-metaoptimization/references/contracts.md`. Format: `sha256:<64 lowercase hex chars>`. |
| `emitted_at` | string (ISO 8601) | Timestamp when the artifact was written. |
| `preflight_duration_seconds` | number | Wall-clock duration of the preflight invocation in seconds. |
| `checks_summary` | object | Aggregate check counts — see Checks Summary below. |
| `failures` | array | Failure records — see Failure Records below. Empty when `status` is `READY`. |
| `next_action` | string | Recommended next step — see Next Action below. |
| `diagnostics` | string or null | Free-form diagnostic text. `null` when there is nothing notable to report. |

### Checks Summary

| Field | Type | Description |
|-------|------|-------------|
| `total` | non-negative integer | Total number of readiness checks evaluated. |
| `passed` | non-negative integer | Checks that passed on initial evaluation. |
| `failed` | non-negative integer | Checks that remain failed after any bootstrap attempts. |
| `bootstrapped` | non-negative integer | Checks that initially failed but passed after a bootstrap mutation. |

Invariant: `passed + failed + bootstrapped == total`.

### Failure Records

Each entry in `failures` must be an object with:

| Field | Type | Description |
|-------|------|-------------|
| `check_id` | string | Stable identifier for the check (e.g., `backend_reachability`, `campaign_file_exists`). Specific check IDs will be enumerated in the check catalog (later task). |
| `category` | string | One of `"backend"`, `"repository"`, `"environment"`. |
| `message` | string | Human-readable description of what failed. |
| `remediation` | string | Actionable guidance for resolving the failure. |

The `failures` array must be empty when `status` is `READY` and non-empty
when `status` is `FAILED`.

---

## Status Semantics

| Value | Meaning |
|-------|---------|
| `READY` | All readiness checks passed (possibly after bootstrap). The environment is safe for `ml-metaoptimization` to begin a campaign. |
| `FAILED` | One or more readiness checks remain failed. The environment is NOT ready. The `failures` array contains actionable details. |

No other status values are valid.

---

## Next Action

| Status | `next_action` value | Meaning |
|--------|---------------------|---------|
| `READY` | `"proceed"` | The orchestrator may begin the campaign. |
| `FAILED` | Human-readable remediation summary | Describes what the user should fix before re-running preflight. |

When `status` is `FAILED`, `next_action` should summarize the most critical
remediation steps from the `failures` array. It is a convenience field — the
`failures` array remains the authoritative detail.

---

## Diagnostics

The `diagnostics` field is free-form text intended for human consumption or
logging. It may include:

- Notes about bootstrap mutations performed (e.g., "created `.ml-metaopt/`
  directory", "provisioned delegation infrastructure").
- Warnings that do not block readiness but may be relevant (e.g., "backend
  responded slowly — 4.2 s latency").
- `null` when there is nothing notable.

The orchestrator must not parse `diagnostics` programmatically. It exists for
human operators and log inspection only.

---

## Freshness and Invalidation Rules

The readiness artifact is a **point-in-time snapshot**. It records that
preflight's checks passed under specific conditions at a specific moment.
Freshness has two tiers with different verification costs:

### Tier 1 — Binding Freshness (cheap, orchestrator can verify)

Binding freshness answers: "was this artifact produced for the current
campaign and runtime configuration?" It is purely about artifact
presence, parseability, and hash alignment — **not** about readiness
outcome. A `FAILED` artifact with matching hashes is fresh (it accurately
reflects the preflight result for this configuration); a `READY` artifact
with mismatched hashes is stale.

The orchestrator can verify binding freshness by comparing hash values
already available during `LOAD_CAMPAIGN`:

1. The artifact exists at `.ml-metaopt/preflight-readiness.json` and is
   parseable JSON with a recognized `schema_version`.
2. `campaign_identity_hash` in the artifact matches the orchestrator's
   computed `campaign_identity_hash`.
3. `runtime_config_hash` in the artifact matches the orchestrator's
   computed `runtime_config_hash`.

If any of these conditions fail, the artifact is **stale** (or absent) and
the orchestrator must not proceed. It should block with a message directing
the user to re-run `metaopt-preflight`.

Note: The `status` field is **not** part of binding freshness. A fresh
artifact may have `status` of either `READY` or `FAILED`. The orchestrator
evaluates `status` as a separate readiness-outcome check after confirming
binding freshness — see the Orchestrator Consumption Protocol below.

**Rationale:** The campaign identity hash covers the campaign's structural
identity (objective, datasets). The runtime config hash covers operational
configuration (execution, queue backend, sanity, artifacts). Together they
ensure the artifact was produced for the exact campaign configuration the
orchestrator is about to execute. No additional hash computation by the
orchestrator is required — it already computes both hashes during
`LOAD_CAMPAIGN`.

### Tier 2 — Operational Freshness (requires preflight rerun)

Certain conditions verified by preflight cannot be re-checked by hash
comparison alone:

- Backend reachability (network state may have changed)
- Runtime dependency availability (tools may have been uninstalled)
- Git working tree cleanliness (files may have been modified)
- Credential validity (tokens may have expired)

The readiness artifact does not guarantee these conditions remain true after
`emitted_at`. The orchestrator is **not required** to re-validate them —
doing so would duplicate preflight's logic.

Instead, if the orchestrator encounters an operational failure that
preflight would have caught (e.g., backend unreachable at
`ENQUEUE_REMOTE_BATCH`), it may recommend re-running `metaopt-preflight`
as a remediation step in its error handling.

### When to Re-run Preflight

Re-running preflight is recommended when:

- The campaign spec has been edited (hashes will no longer match).
- The environment has changed (new machine, updated dependencies,
  credential rotation).
- The orchestrator encountered an operational failure that suggests
  environmental drift.
- The user wants to re-validate readiness after external remediation.

Re-running preflight is **not** required on every orchestrator invocation if
the binding freshness checks pass and the environment has not visibly
changed.

---

## Relationship to Campaign/Runtime Identity

This artifact reuses the identity concepts defined in
`ml-metaoptimization/references/contracts.md`:

- **`campaign_identity_hash`** — canonical hash over `version`,
  `campaign_id`, `objective.metric`, `objective.direction`,
  `objective.aggregation`, and sorted dataset entries. Defined and owned by
  `ml-metaoptimization`.

- **`runtime_config_hash`** — canonical hash over `sanity`, `artifacts`,
  `remote_queue`, and `execution`. Defined and owned by
  `ml-metaoptimization`.

Preflight computes these hashes using the same canonicalization rules
specified in the Campaign Identity Hash Contract. It does not define its own
competing identity scheme.

### No Additional Top-Level Fingerprints Required

The two existing hashes provide sufficient coverage for binding freshness:

- **Backend identity** (which backend, endpoint, retry policy) is captured
  in `remote_queue`, which is part of `runtime_config_hash`.
- **Execution configuration** (entrypoint, sanity commands) is captured in
  `execution` and `sanity`, which are part of `runtime_config_hash`.

If future tasks (backend setup contract, repo setup contract) reveal
preflight inputs not covered by these two hashes — for example,
environment-specific configuration outside the campaign spec — a
`preflight_inputs_hash` may be introduced as an optional additional binding.
Such an extension would be additive: the orchestrator's existing hash checks
would remain valid, and the new hash would provide an additional staleness
signal.

Until that need is concretely demonstrated, no additional fingerprints are
defined.

---

## Orchestrator Consumption Protocol

The orchestrator should consume the readiness artifact during
`LOAD_CAMPAIGN` or `HYDRATE_STATE`, before entering the campaign loop.
The protocol distinguishes binding freshness (is this artifact for the
current configuration?) from readiness outcome (did preflight succeed?):

1. Attempt to read `.ml-metaopt/preflight-readiness.json`.
2. If the file is **missing or unreadable** (does not exist, is not valid
   JSON, or has an unrecognized `schema_version`) → block with
   `next_action = "run metaopt-preflight"`.
3. If the file is present and parseable, verify **binding freshness**
   (Tier 1): compare `campaign_identity_hash` and `runtime_config_hash`
   against the orchestrator's computed values.
4. If binding freshness **fails** (hash mismatch) → block with
   `next_action = "re-run metaopt-preflight (campaign configuration has changed)"`.
5. If binding freshness **passes** and `status` is `FAILED` → block using
   the artifact's `failures` array and `next_action` field to present
   actionable remediation guidance. The message should indicate that
   preflight ran for the current configuration but the environment is not
   ready — not that configuration has changed.
6. If binding freshness **passes** and `status` is `READY` → proceed into
   the campaign loop.

The orchestrator must not attempt to re-run individual preflight checks. The
readiness artifact is the sole interface; if it is absent or stale, the
remedy is to invoke `metaopt-preflight`.

---

## Schema Versioning

The `schema_version` field enables future evolution:

- Consumers that encounter an unrecognized `schema_version` should treat the
  artifact as absent (block and request preflight rerun) rather than
  attempting to parse unknown fields.
- Schema changes that add optional fields without removing or redefining
  existing ones may keep the same `schema_version`.
- Schema changes that alter required field semantics or remove fields must
  increment `schema_version`.

---

## Deferred Specifications

The following are explicitly out of scope for this contract and will be
defined in later tasks:

| Topic | Deferred to |
|-------|-------------|
| Enumerated check IDs and their pass/fail criteria | Check catalog task |
| Backend setup contract (probe commands, bootstrap mutations) | Backend setup contract task |
| Repo setup contract (structural requirements, bootstrap mutations) | Repo setup contract task |
| Preflight input contract (what configuration preflight reads) | Input contract task |
