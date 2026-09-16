#!/usr/bin/env python3
"""Build Expansion packages (dev or protected release).

Usage:
  python3 scripts/build_expansion_release.py --channel dev --out /tmp/exp-dev
  python3 scripts/build_expansion_release.py --channel protected --out /tmp/exp-prot

Protected builds require product/dossiers/*.json (dev SoT) and write
protected-bundle.enc + signed PACKAGE_MANIFEST.json. Bundle keys go to
the KeyProvider secrets root — never into the package tree.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description='Build Otacon Keep Expansion package')
    ap.add_argument('--channel', choices=('dev', 'protected'), default='dev')
    ap.add_argument('--out', required=True, help='Output directory')
    ap.add_argument('--ui', default='', help='Optional UI source tree to harden into release')
    args = ap.parse_args()
    out = Path(args.out)

    if args.channel == 'dev':
        from expansion.release.build import build_dev_tree
        result = build_dev_tree(out)
    else:
        from expansion.release.build import build_protected_release
        ui = Path(args.ui) if args.ui else (ROOT / 'ui')
        result = build_protected_release(
            out,
            minify_frontend_from=ui if ui.is_dir() else None,
        )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.smoke_ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
