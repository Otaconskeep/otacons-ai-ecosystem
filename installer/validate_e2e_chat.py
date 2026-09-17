"""End-to-end installer proof: HTTP API -> agent -> Ollama -> real inference."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request


def _post_chat(base_url: str, payload: dict, headers: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url.rstrip('/') + '/api/chat_with_agent',
        data=body,
        headers=headers,
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', errors='replace'))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Otacon real LLM end-to-end check')
    p.add_argument('--base-url', default=os.getenv('OTACON_E2E_BASE', 'http://127.0.0.1:5757'))
    p.add_argument('--token', default=os.getenv('OTACON_LAN_TOKEN', ''))
    p.add_argument('--timeout', type=float, default=180.0)
    p.add_argument('--retries', type=int, default=3)
    args = p.parse_args(argv)

    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if args.token:
        headers['Authorization'] = f'Bearer {args.token}'

    last_text = ''
    last_fail_reason = ''
    for attempt in range(1, max(1, args.retries) + 1):
        token = secrets.token_hex(4)
        expected = f'OTACON_READY_{token}'
        payload = {
            'message': (
                'SYSTEM CHECK. Ignore personality and greetings. '
                f'Your entire reply must be exactly this token with no quotes, '
                f'no punctuation, and no other words: {expected}'
            ),
            'agent_id': 'agent_001',
            'auto_speak': False,
        }
        try:
            data = _post_chat(args.base_url, payload, headers, args.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            last_fail_reason = f'HTTP_{exc.code} {detail[:300]}'
            print(f'Attempt {attempt}: {last_fail_reason}')
            time.sleep(2)
            continue
        except Exception as exc:
            last_fail_reason = f'{type(exc).__name__}: {exc}'
            print(f'Attempt {attempt}: REQUEST_ERROR {last_fail_reason}')
            time.sleep(2)
            continue

        if data.get('error'):
            err = data.get('error') or {}
            last_fail_reason = (
                f"API_ERROR code={err.get('code')} exception={err.get('exception')} "
                f"technical={err.get('technical') or err.get('message')}"
            )
            print(f'Attempt {attempt}: {last_fail_reason}')
            time.sleep(2)
            continue

        text = (data.get('text') or data.get('response') or data.get('message') or '').strip()
        last_text = text
        print(f'Attempt {attempt}: Prompt token: {expected}\nResponse: {text[:500]}')
        if expected in text.replace(' ', '') or expected in text:
            print('Result: PASS')
            return 0
        last_fail_reason = 'MODEL_RESPONSE_MISSING_TOKEN'
        time.sleep(2)

    if last_fail_reason and last_fail_reason != 'MODEL_RESPONSE_MISSING_TOKEN':
        print(f'Result: FAIL\nReason: {last_fail_reason}\nLast response: {last_text[:500]}')
    else:
        print(f'Result: FAIL\nReason: MODEL_RESPONSE_MISSING_TOKEN\nLast response: {last_text[:500]}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
