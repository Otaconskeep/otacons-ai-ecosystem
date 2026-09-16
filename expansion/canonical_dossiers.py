"""Canonical dossier loader — product JSON is the single source of truth.

Rule:
  expansion/product/dossiers/{agent_id}.json  = canonical source
  this module                          = load + validate only

Do not redefine agent lore in Python. Packaging/encryption later wraps the
same product JSON (or a build-generated protected bundle derived from it).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from expansion.dossier import (
    CanonicalDossier,
    canonical_from_dict,
    empty_canonical_dossier,
    validate_canonical_dossier,
)
from expansion.state_layout import StateLayout, resolve_layout

CANONICAL_AGENT_IDS = ('aria', 'vector', 'ledger', 'muse', 'sentry')


def product_dossiers_dir(layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    return layout.product_root / 'product' / 'dossiers'


def dossier_path(agent_id: str, layout: Optional[StateLayout] = None) -> Path:
    return product_dossiers_dir(layout) / f'{agent_id}.json'


def _load_raw(agent_id: str, layout: Optional[StateLayout] = None) -> dict:
    path = dossier_path(agent_id, layout)
    if not path.is_file():
        raise FileNotFoundError(
            f'canonical dossier missing: {path} '
            f'(product/dossiers/*.json is the source of truth)'
        )
    return json.loads(path.read_text(encoding='utf-8'))


@lru_cache(maxsize=16)
def _cached_load(agent_id: str, product_root: str) -> CanonicalDossier:
    """Cache by agent_id + product_root so tests with temp roots stay isolated."""
    layout = resolve_layout(Path(product_root))
    raw = _load_raw(agent_id, layout)
    dossier = canonical_from_dict(raw)
    errors = validate_canonical_dossier(dossier)
    if errors:
        raise ValueError(f'{agent_id} dossier invalid: {errors}')
    if dossier.agent_id != agent_id:
        raise ValueError(
            f'dossier agent_id mismatch: file={agent_id!r} payload={dossier.agent_id!r}'
        )
    return dossier


def clear_dossier_cache() -> None:
    _cached_load.cache_clear()


def get_canonical_dossier(
    agent_id: str,
    layout: Optional[StateLayout] = None,
) -> CanonicalDossier:
    layout = layout or resolve_layout()
    if agent_id not in CANONICAL_AGENT_IDS:
        return empty_canonical_dossier(agent_id)
    try:
        return _cached_load(agent_id, str(layout.product_root.resolve()))
    except FileNotFoundError:
        return empty_canonical_dossier(agent_id)


def all_canonical_dossiers(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    return {aid: get_canonical_dossier(aid, layout) for aid in CANONICAL_AGENT_IDS}


def list_product_dossier_paths(layout: Optional[StateLayout] = None) -> list[Path]:
    """Return paths to shipped product dossier JSON files (must exist)."""
    layout = layout or resolve_layout()
    root = product_dossiers_dir(layout)
    paths = []
    missing = []
    for aid in CANONICAL_AGENT_IDS:
        path = root / f'{aid}.json'
        if path.is_file():
            paths.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise FileNotFoundError(
            'canonical product dossiers missing (JSON is SoT): ' + '; '.join(missing)
        )
    return paths


# Back-compat aliases used by older call sites / tests (loader only).
def dossier_aria() -> CanonicalDossier:
    return get_canonical_dossier('aria')


def dossier_vector() -> CanonicalDossier:
    return get_canonical_dossier('vector')


def dossier_ledger() -> CanonicalDossier:
    return get_canonical_dossier('ledger')


def dossier_muse() -> CanonicalDossier:
    return get_canonical_dossier('muse')


def dossier_sentry() -> CanonicalDossier:
    return get_canonical_dossier('sentry')
