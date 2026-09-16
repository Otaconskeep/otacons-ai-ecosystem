"""Canonical filesystem layout: product data vs user data.

PRODUCT DATA (signed / versioned / mostly immutable in production releases):
  lives under the Expansion package / install tree — never receives
  user-generated memories, journals, diaries, or living dossiers.

USER DATA (mutable, survives updates):
  lives under XDG-style config/data roots owned by the installing user.

Do not store user-generated state inside the product bundle.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


@dataclass(frozen=True)
class StateLayout:
    """Resolved roots for one Expansion install."""

    # Product (immutable in production; may be a staged package dir)
    product_root: Path
    product_agents: Path
    product_presets: Path
    product_assets: Path
    product_dossiers: Path
    product_manifest: Path

    # User (mutable)
    user_config_root: Path
    user_data_root: Path
    user_agents: Path
    user_relationships: Path
    user_emotions: Path
    user_memory: Path
    user_journals: Path
    user_diaries: Path
    user_living_dossiers: Path
    user_jobs: Path
    user_events: Path
    user_preferences: Path
    user_migrations: Path
    user_pages: Path
    secrets_root: Path
    package_versions_root: Path

    def ensure_user_dirs(self) -> None:
        for p in (
            self.user_config_root,
            self.user_data_root,
            self.user_agents,
            self.user_relationships,
            self.user_emotions,
            self.user_memory,
            self.user_journals,
            self.user_diaries,
            self.user_living_dossiers,
            self.user_jobs,
            self.user_events,
            self.user_preferences,
            self.user_migrations,
            self.user_pages,
            self.secrets_root,
            self.package_versions_root,
        ):
            p.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.chmod(self.secrets_root, 0o700)
        except OSError:
            pass

    def assert_not_product_write(self, path: Path) -> None:
        """Raise if a caller tries to treat a product path as user-writable state."""
        resolved = path.resolve()
        product = self.product_root.resolve()
        try:
            resolved.relative_to(product)
        except ValueError:
            return
        # Allow writing only under explicitly designated user roots even if
        # someone nested oddly; product/ subtree is always forbidden for user state.
        if 'product' in resolved.parts:
            raise PermissionError(
                f'refusing to write user state into product tree: {resolved}'
            )


def default_product_root() -> Path:
    """Expansion product tree: the installed repo's expansion/ package dir,
    or an explicit override for staged/protected releases.
    """
    override = os.environ.get('OTACON_EXPANSION_PRODUCT_ROOT')
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent


def default_user_config_root() -> Path:
    return _env_path(
        'OTACON_EXPANSION_CONFIG_ROOT',
        Path.home() / '.config' / 'otacon' / 'expansion',
    )


def default_user_data_root() -> Path:
    return _env_path(
        'OTACON_EXPANSION_DATA_ROOT',
        Path.home() / '.local' / 'share' / 'otacon' / 'expansion',
    )


def resolve_layout(product_root: Path | None = None) -> StateLayout:
    product = Path(product_root) if product_root else default_product_root()
    cfg = default_user_config_root()
    data = default_user_data_root()
    # Backward-compatible agent seed location used by install_otacon_expansion.sh
    agents_override = os.environ.get('OTACON_EXPANSION_DATA_DIR')
    user_agents = (
        Path(agents_override).expanduser()
        if agents_override
        else cfg / 'agents'
    )
    return StateLayout(
        product_root=product,
        product_agents=product / 'product' / 'agents',
        product_presets=product / 'product' / 'presets',
        product_assets=product / 'product' / 'assets',
        product_dossiers=product / 'product' / 'dossiers',
        product_manifest=product / 'product' / 'PACKAGE_MANIFEST.json',
        user_config_root=cfg,
        user_data_root=data,
        user_agents=user_agents,
        user_relationships=data / 'relationships',
        user_emotions=data / 'emotions',
        user_memory=data / 'memory',
        user_journals=data / 'journals',
        user_diaries=data / 'diaries',
        user_living_dossiers=data / 'living_dossiers',
        user_jobs=data / 'jobs',
        user_events=data / 'events',
        user_preferences=cfg / 'preferences',
        user_migrations=cfg / 'migrations',
        user_pages=cfg / 'pages',
        secrets_root=_env_path(
            'OTACON_EXPANSION_SECRETS_ROOT',
            cfg / 'secrets',
        ),
        package_versions_root=data / 'packages',
    )
