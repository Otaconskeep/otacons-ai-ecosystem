"""Living dossier initialization (empty, provenance-ready)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from expansion.dossier import LivingDossier, to_dict, validate_living_dossier
from expansion.state_layout import StateLayout
from expansion.versions import DOSSIER_SCHEMA_VERSION


def init_empty_living_dossier(layout: StateLayout, agent_id: str) -> Path:
    layout.user_living_dossiers.mkdir(parents=True, exist_ok=True)
    path = layout.user_living_dossiers / f'{agent_id}.json'
    if path.exists():
        return path
    living = LivingDossier(
        schema_version=DOSSIER_SCHEMA_VERSION,
        agent_id=agent_id,
        observed_traits=(),
        notes='No observed traits yet — living history starts at install.',
        updated_at=time.time(),
    )
    # Empty observed_traits is valid (no provenance required until observations exist)
    errors = validate_living_dossier(living)
    # validate requires evidence on each trait; empty tuple is fine
    if errors:
        raise ValueError(errors)
    path.write_text(json.dumps(to_dict(living), indent=2) + '\n', encoding='utf-8')
    return path
