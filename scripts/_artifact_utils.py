"""Readiness artifact builder, writer, and reader.

Schema defined in references/readiness-artifact.md.
Consumed by ml-metaoptimization's _evaluate_preflight() in load_campaign_handoff.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_FILENAME = "preflight-readiness.json"
SCHEMA_VERSION = 1


def summarize_failures(failures: list[dict]) -> str:
    """Return a short human-readable summary for the next_action field."""
    if not failures:
        return "proceed"
    ids = [f.get("check_id", "unknown") for f in failures]
    return f"Fix {len(ids)} failure{'s' if len(ids) != 1 else ''}: [{', '.join(ids)}]"


def build_artifact(
    campaign_identity_hash: str,
    runtime_config_hash: str,
    status: str,
    failures: list[dict],
    checks_summary: dict,
    diagnostics: str | None,
    campaign_id: str,
    duration_seconds: float,
) -> dict:
    """Build the full readiness artifact dict matching the schema."""
    if status not in ("READY", "FAILED"):
        raise ValueError(f"status must be 'READY' or 'FAILED', got {status!r}")

    if status == "READY":
        next_action = "proceed"
    else:
        next_action = summarize_failures(failures)

    summary = {
        "total": checks_summary.get("total", 0),
        "passed": checks_summary.get("passed", 0),
        "failed": checks_summary.get("failed", 0),
        "bootstrapped": checks_summary.get("bootstrapped", 0),
        "warnings": checks_summary.get("warnings", 0),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "campaign_id": campaign_id,
        "campaign_identity_hash": campaign_identity_hash,
        "runtime_config_hash": runtime_config_hash,
        "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preflight_duration_seconds": duration_seconds,
        "checks_summary": summary,
        "failures": list(failures),
        "next_action": next_action,
        "diagnostics": diagnostics,
    }


def write_artifact(artifact: dict, state_dir: Path) -> Path:
    """Write artifact JSON to state_dir / ARTIFACT_FILENAME.

    Creates parent directories if needed. Overwrites any existing file
    (latest-wins semantics).
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / ARTIFACT_FILENAME
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return path


def read_artifact(state_dir: Path) -> dict | None:
    """Read and parse the readiness artifact. Returns None if missing or corrupt."""
    path = state_dir / ARTIFACT_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None
