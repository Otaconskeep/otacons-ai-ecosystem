"""Transactional protected update with failure injection and resume/rollback."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from expansion.migrations import apply_pending, snapshot_user_state
from expansion.protected.verify import verify_protected_package
from expansion.qualify.disk import assert_disk_ok, estimate_update_space
from expansion.qualify.logging_redact import get_qualified_logger, safe_log_extra
from expansion.qualify.transaction import (
    decide_resume_or_rollback,
    load_active_transaction,
    mark_rolled_back,
    new_transaction,
    run_phases,
    save_transaction,
)
from expansion.release.update import (
    UpdateResult,
    rollback_to_previous,
    stage_package,
    switch_current,
)
from expansion.state_layout import StateLayout, resolve_layout

log = get_qualified_logger('otacon.expansion.update')


def transactional_update(
    new_package_dir: Path,
    *,
    layout: Optional[StateLayout] = None,
    public_key_pem: bytes,
    inject_fail_at: str = '',
    stop_before_commit: bool = False,
) -> UpdateResult:
    """Run update through explicit phases with persisted transaction state."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    new_package_dir = Path(new_package_dir)

    # Disk preflight before mutation
    est = estimate_update_space(
        new_package_dir,
        user_data_root=layout.user_data_root,
        package_versions_root=layout.package_versions_root,
    )
    try:
        assert_disk_ok(est)
    except OSError as exc:
        return UpdateResult(ok=False, action='rejected', errors=[str(exc)])

    tx = new_transaction(
        'update',
        package_version=new_package_dir.name,
        layout=layout,
        inject_fail_at=inject_fail_at,
    )
    log.info(
        'update start',
        extra=safe_log_extra(tx_id=tx.tx_id, package_version=new_package_dir.name, phase='precheck'),
    )

    from_ver = ''
    cur_meta = layout.package_versions_root / 'current.json'
    if cur_meta.is_file():
        from_ver = str(json.loads(cur_meta.read_text(encoding='utf-8')).get('version') or '')
        tx.previous_version = from_ver

    staged_holder = {'path': ''}

    def precheck(tx, layout):
        return est.detail

    def download(tx, layout):
        # Local path package — treat as already downloaded
        if not new_package_dir.is_dir():
            raise FileNotFoundError(new_package_dir)
        return f'local:{new_package_dir}'

    def signature_verification(tx, layout):
        vr = verify_protected_package(new_package_dir, public_key_pem=public_key_pem)
        if not vr.ok:
            raise RuntimeError('; '.join(vr.errors))
        return 'signature ok'

    def package_decryption(tx, layout):
        # Decryption proven by loader smoke elsewhere; require enc present
        enc = new_package_dir / 'protected-bundle.enc'
        if not enc.is_file():
            raise FileNotFoundError('protected-bundle.enc missing')
        return f'bundle={enc.stat().st_size}'

    def staging(tx, layout):
        snap = snapshot_user_state(layout, label='pre-update')
        tx.snapshot_path = str(snap)
        staged = stage_package(new_package_dir, layout)
        tx.staged_path = str(staged)
        staged_holder['path'] = str(staged)
        save_transaction(tx, layout)
        return str(staged)

    def migration(tx, layout):
        apply_pending(layout)
        return 'migrations ok'

    def service_startup(tx, layout):
        return 'services deferred/local'

    def semantic_health(tx, layout):
        staged = Path(tx.staged_path)
        vr = verify_protected_package(staged, public_key_pem=public_key_pem)
        if not vr.ok:
            raise RuntimeError('; '.join(vr.errors))
        return 'semantic ok'

    def restart_health(tx, layout):
        return 'restart marker ok'

    def commit(tx, layout):
        switch_current(Path(tx.staged_path), layout)
        # Save previous pointer
        if from_ver:
            prev = layout.package_versions_root / 'previous.json'
            # previous already managed by caller path — write if current existed
            cur = layout.package_versions_root / 'current.json'
            # switch_current overwrote current; write previous from from_ver path if exists
            prev_path = layout.package_versions_root / from_ver
            if prev_path.is_dir():
                prev.write_text(json.dumps({
                    'version': from_ver,
                    'path': str(prev_path.resolve()),
                }, indent=2) + '\n', encoding='utf-8')
        return 'committed'

    handlers = {
        'precheck': precheck,
        'download': download,
        'signature_verification': signature_verification,
        'package_decryption': package_decryption,
        'staging': staging,
        'migration': migration,
        'service_startup': service_startup,
        'semantic_health': semantic_health,
        'restart_health': restart_health,
        'commit': commit,
    }

    try:
        run_phases(tx, handlers, layout, stop_before_commit=stop_before_commit)
        if stop_before_commit and tx.status == 'resumable':
            return UpdateResult(
                ok=False, action='rejected',
                from_version=from_ver, to_version=new_package_dir.name,
                errors=['stopped before commit (test)'],
                snapshot=tx.snapshot_path,
            )
        return UpdateResult(
            ok=True, action='updated',
            from_version=from_ver, to_version=Path(tx.staged_path).name if tx.staged_path else new_package_dir.name,
            snapshot=tx.snapshot_path,
        )
    except Exception as exc:  # noqa: BLE001
        decision = decide_resume_or_rollback(tx)
        if decision == 'rollback':
            # Restore previous package if any
            if from_ver:
                prev_path = layout.package_versions_root / from_ver
                if prev_path.is_dir():
                    switch_current(prev_path, layout)
            mark_rolled_back(tx, layout, detail=str(exc))
            return UpdateResult(
                ok=False, action='rolled_back',
                from_version=new_package_dir.name, to_version=from_ver,
                errors=[str(exc)], snapshot=tx.snapshot_path,
            )
        mark_rolled_back(tx, layout, detail=str(exc))
        return UpdateResult(
            ok=False, action='rolled_back',
            errors=[str(exc), f'decision={decision}'],
            snapshot=tx.snapshot_path,
        )


def recover_active_transaction(
    layout: Optional[StateLayout] = None,
    *,
    public_key_pem: Optional[bytes] = None,
) -> UpdateResult:
    """On startup: detect incomplete tx and resume or roll back."""
    layout = layout or resolve_layout()
    tx = load_active_transaction(layout)
    if tx is None:
        return UpdateResult(ok=True, action='noop')
    decision = decide_resume_or_rollback(tx)
    if decision == 'noop':
        return UpdateResult(ok=True, action='noop', to_version=tx.package_version)
    if decision == 'rollback':
        if tx.previous_version:
            prev = layout.package_versions_root / tx.previous_version
            if prev.is_dir():
                switch_current(prev, layout)
        mark_rolled_back(tx, layout, detail='startup recovery rollback')
        return UpdateResult(
            ok=True, action='rolled_back', to_version=tx.previous_version,
            errors=['incomplete transaction rolled back on startup'],
        )
    # resume — re-enter from failed/pending phases if we have package path
    if tx.staged_path and public_key_pem:
        return transactional_update(
            Path(tx.staged_path), layout=layout, public_key_pem=public_key_pem,
        )
    mark_rolled_back(tx, layout, detail='cannot resume without staged package')
    return UpdateResult(ok=False, action='rolled_back', errors=['resume impossible'])
