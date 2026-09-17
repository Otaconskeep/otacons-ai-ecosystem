#!/usr/bin/env python3
"""Build Keep Expansion release-candidate artifact from clean inputs.

Produces: keep-expansion-<version>-rc1/ under --out
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--version', default='')
    args = ap.parse_args()

    from expansion.versions import EXPANSION_VERSION
    from expansion.release.build import build_protected_release
    from expansion.qualify.leak_scan import scan_tree
    from expansion.protected.keys import PermissionedFileKeyProvider
    from expansion.state_layout import resolve_layout

    version = args.version or EXPANSION_VERSION
    if 'rc' not in version:
        # normalize to rc1 label in folder name
        folder = f'keep-expansion-{version}-rc1'
    else:
        folder = f'keep-expansion-{version}'
    out_root = Path(args.out) / folder
    if out_root.exists():
        shutil.rmtree(out_root)

    layout = resolve_layout()
    kp = PermissionedFileKeyProvider(layout=layout)
    ui = ROOT / 'ui'
    result = build_protected_release(
        out_root,
        layout=layout,
        key_provider=kp,
        minify_frontend_from=ui if ui.is_dir() else None,
        key_id='rc1',
    )
    notes = {
        'artifact': folder,
        'version': version,
        'build_id': result.build_id,
        'channel': result.channel,
        'smoke_ok': result.smoke_ok,
        'notes': result.notes,
        'compatibility': {
            'core_version_min': '0.1.0',
            'expansion_version': version,
        },
    }
    (out_root / 'RELEASE_NOTES.json').write_text(json.dumps(notes, indent=2) + '\n', encoding='utf-8')
    scan = scan_tree(out_root, is_release_candidate=True, allow_user_primary=True)
    (out_root / 'LEAK_SCAN.json').write_text(json.dumps(scan.to_dict(), indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'artifact': str(out_root), 'smoke_ok': result.smoke_ok, 'leak_ok': scan.ok, **notes}, indent=2))
    return 0 if result.smoke_ok and scan.ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
