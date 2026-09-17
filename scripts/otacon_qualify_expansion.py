#!/usr/bin/env python3
"""P4 Expansion acceptance matrix.

Usage:
  python3 scripts/otacon_qualify_expansion.py
  python3 scripts/otacon_qualify_expansion.py --channel protected --package /path/to/rc
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
    ap = argparse.ArgumentParser(description='Otacon Keep Expansion P4 acceptance')
    ap.add_argument('--channel', default='dev', choices=('dev', 'protected', 'public'))
    ap.add_argument('--package', default='', help='Protected package dir for RC checks')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    from expansion.qualify.acceptance import run_acceptance

    pub = None
    pkg = Path(args.package) if args.package else None
    if pkg and (pkg / 'signing-public.pem').is_file():
        pub = (pkg / 'signing-public.pem').read_bytes()
    report = run_acceptance(channel=args.channel, package_dir=pkg, public_key_pem=pub)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f'OVERALL: {report.overall}  channel={report.channel}')
        for c in report.cells:
            print(f'  {c.status:8}  {c.name:22}  {c.detail}')
    return 0 if report.overall in ('PASS', 'DEGRADED', 'SKIP') else 1


if __name__ == '__main__':
    raise SystemExit(main())
