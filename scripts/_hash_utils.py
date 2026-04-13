"""Campaign identity and runtime-config hash utilities.

Produces hashes that are byte-identical to the v4 orchestrator
(ml-metaoptimization/scripts/load_campaign_handoff.py::_identity_hash)
so the LOAD_CAMPAIGN freshness check passes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _get_nested(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Safely traverse *payload* along *path*, returning ``None`` on miss."""
    node: Any = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _canonical_json(payload: Any) -> bytes:
    """Deterministic JSON encoding (matches orchestrator exactly)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(payload)).hexdigest()}"


# ── public API ───────────────────────────────────────────────────────


def compute_campaign_identity_hash(campaign: dict[str, Any]) -> str:
    """Return the campaign identity hash.

    Fields (must match orchestrator ``_identity_hash``):
      - campaign.name
      - objective.metric
      - objective.direction
      - wandb.entity
      - wandb.project
    """
    if not isinstance(campaign, dict):
        campaign = {}
    payload = {
        "campaign_name": _get_nested(campaign, ("campaign", "name")),
        "objective": {
            "metric": _get_nested(campaign, ("objective", "metric")),
            "direction": _get_nested(campaign, ("objective", "direction")),
        },
        "wandb": {
            "entity": _get_nested(campaign, ("wandb", "entity")),
            "project": _get_nested(campaign, ("wandb", "project")),
        },
    }
    return _sha256(payload)


def compute_runtime_config_hash(campaign: dict[str, Any]) -> str:
    """Return the runtime config hash.

    Fields:
      - compute (entire block)
      - wandb.entity, wandb.project
      - project.repo
      - project.smoke_test_command
    """
    if not isinstance(campaign, dict):
        campaign = {}
    payload = {
        "compute": campaign.get("compute") if isinstance(campaign.get("compute"), dict) else None,
        "wandb": {
            "entity": _get_nested(campaign, ("wandb", "entity")),
            "project": _get_nested(campaign, ("wandb", "project")),
        },
        "project": {
            "repo": _get_nested(campaign, ("project", "repo")),
            "smoke_test_command": _get_nested(campaign, ("project", "smoke_test_command")),
        },
    }
    return _sha256(payload)


def verify_hashes_match(preflight_hash: str, orchestrator_hash: str) -> bool:
    """Return ``True`` when two hash strings are identical."""
    if not isinstance(preflight_hash, str) or not isinstance(orchestrator_hash, str):
        return False
    return preflight_hash == orchestrator_hash
