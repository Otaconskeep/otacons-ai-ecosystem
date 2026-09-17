"""Low-disk preflight — fail before mutation when possible."""
from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DiskEstimate:
    download_bytes: int
    staging_bytes: int
    rollback_bytes: int
    snapshot_bytes: int
    migration_overhead_bytes: int
    safety_margin_bytes: int
    required_bytes: int
    available_bytes: int
    ok: bool
    detail: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    if path.is_file():
        return path.stat().st_size
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def estimate_update_space(
    package_dir: Path,
    *,
    user_data_root: Path,
    package_versions_root: Path,
    safety_ratio: float = 0.15,
    min_safety_bytes: int = 64 * 1024 * 1024,
) -> DiskEstimate:
    pkg = _dir_size(package_dir)
    user = _dir_size(user_data_root)
    # download ≈ package; staging copy ≈ package; rollback keep ≈ package;
    # snapshot ≈ user data; migration overhead ≈ 10% of user
    download_b = pkg
    staging_b = pkg
    rollback_b = pkg
    snapshot_b = user
    migration_b = max(int(user * 0.10), 8 * 1024 * 1024)
    raw = download_b + staging_b + rollback_b + snapshot_b + migration_b
    safety = max(int(raw * safety_ratio), min_safety_bytes)
    required = raw + safety
    usage = shutil.disk_usage(str(package_versions_root if package_versions_root.exists()
                                  else user_data_root if user_data_root.exists()
                                  else Path.cwd()))
    available = usage.free
    ok = available >= required
    detail = (
        f'required={required} available={available}'
        if ok else
        f'insufficient disk: need {required} bytes, have {available} (fail before mutation)'
    )
    return DiskEstimate(
        download_bytes=download_b,
        staging_bytes=staging_b,
        rollback_bytes=rollback_b,
        snapshot_bytes=snapshot_b,
        migration_overhead_bytes=migration_b,
        safety_margin_bytes=safety,
        required_bytes=required,
        available_bytes=available,
        ok=ok,
        detail=detail,
    )


def assert_disk_ok(estimate: DiskEstimate) -> None:
    if not estimate.ok:
        raise OSError(f'LOW_DISK: {estimate.detail}')
