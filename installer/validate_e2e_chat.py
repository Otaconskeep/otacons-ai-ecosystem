"""End-to-end installer proof: HTTP API -> agent -> Ollama -> real inference."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Otacon real LLM end-to-end check')
    p.add_argument('--base-url', default=os.getenv('OTACON_E2E_BASE', 'http://127.0.0.1:5757'))
    p.add_argument('--token', default=os.getenv('OTACON_LAN_TOKEN', ''))
    p.add_argument('--timeout', type=float, default=120.0)
    args = p.parse_args(argv)

    token = secrets.token_hex(4)
    expected = f'OTACON_READY_{token}'
    payload = {
        'message': (
            f'Reply with exactly this string and nothing else: {expected}'
        ),
        'agent_id': 'agent_001',
        'auto_speak': False,
    }
    body = json.dumps(payload).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if args.token:
        headers['Authorization'] = f'Bearer {args.token}'

    req = urllib.request.Request(
        args.base_url.rstrip('/') + '/api/chat_with_agent',
        data=body,
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        print(f'Result: FAIL\nReason: HTTP_{exc.code}\nDetail: {detail[:500]}')
        return 1
    except Exception as exc:
        print(f'Result: FAIL\nReason: REQUEST_ERROR\nDetail: {exc}')
        return 1

    if data.get('error'):
        print(f"Result: FAIL\nReason: API_ERROR\nDetail: {data.get('error')}")
        return 1

    text = (data.get('text') or data.get('response') or data.get('message') or '').strip()
    if not text:
        print(f'Result: FAIL\nReason: EMPTY_RESPONSE\nPayload keys: {list(data.keys())}')
        return 1

    # Accept exact match or containment (some models add punctuation/whitespace).
    ok = expected in text.replace(' ', '') or expected in text
    print(f'Prompt token: {expected}\nResponse: {text[:500]}\nResult: {"PASS" if ok else "FAIL"}')
    if not ok:
        print('Reason: MODEL_RESPONSE_MISSING_TOKEN')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
