"""Internal Wyoming protocol transport for Piper TTS.

Protocol details stay inside this module; callers use connect / synthesize / health only.
"""
from __future__ import annotations

import json
import socket
from typing import Any


class WyomingTransportError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_endpoint(endpoint: str) -> tuple[str, int]:
    """Accept wyoming://host:port, tcp://host:port, host:port, or http(s)://host:port."""
    raw = (endpoint or '').strip()
    if not raw:
        raise WyomingTransportError('TTS_SERVICE_UNREACHABLE', 'TTS endpoint is empty')
    for prefix in ('wyoming://', 'tcp://', 'http://', 'https://'):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    raw = raw.split('/', 1)[0]
    if ':' not in raw:
        raise WyomingTransportError('TTS_SERVICE_UNREACHABLE', f'invalid TTS endpoint: {endpoint}')
    host, port_s = raw.rsplit(':', 1)
    try:
        port = int(port_s)
    except ValueError as e:
        raise WyomingTransportError('TTS_SERVICE_UNREACHABLE', f'invalid TTS endpoint port: {endpoint}') from e
    if not host:
        raise WyomingTransportError('TTS_SERVICE_UNREACHABLE', f'invalid TTS endpoint host: {endpoint}')
    return host, port


class WyomingClient:
    """Minimal Wyoming 1.x client (header line + optional data_length + payload_length)."""

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        try:
            self.sock = socket.create_connection((host, port), timeout)
        except OSError as e:
            raise WyomingTransportError('TTS_SERVICE_UNREACHABLE', f'cannot connect to {host}:{port}: {e}') from e
        self.sock.settimeout(timeout)
        self.buf = b''

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout as e:
                raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', 'Wyoming read timed out') from e
            if not chunk:
                raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', 'Wyoming connection closed')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def read_event(self) -> tuple[str, dict[str, Any], bytes]:
        while b'\n' not in self.buf:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout as e:
                raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', 'Wyoming read timed out') from e
            if not chunk:
                raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', 'Wyoming connection closed')
            self.buf += chunk
        line, self.buf = self.buf.split(b'\n', 1)
        try:
            header = json.loads(line.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', 'malformed Wyoming event header') from e
        dlen = int(header.get('data_length') or 0)
        plen = int(header.get('payload_length') or 0)
        data: dict[str, Any] = {}
        if dlen:
            raw = self._recv_exact(dlen)
            try:
                data = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', 'malformed Wyoming event data') from e
        # Legacy: some servers put fields under header["data"]
        if not data and isinstance(header.get('data'), dict):
            data = header['data']
        payload = self._recv_exact(plen) if plen else b''
        return str(header.get('type') or ''), data, payload

    def write_event(self, type_: str, data: dict[str, Any] | None = None, payload: bytes = b'') -> None:
        data = data or {}
        data_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8') if data else b''
        header: dict[str, Any] = {'type': type_, 'version': '1.8.0'}
        if data_bytes:
            header['data_length'] = len(data_bytes)
        if payload:
            header['payload_length'] = len(payload)
        try:
            self.sock.sendall(json.dumps(header, separators=(',', ':')).encode('utf-8') + b'\n' + data_bytes + payload)
        except OSError as e:
            raise WyomingTransportError('PROVIDER_TRANSPORT_ERROR', f'Wyoming write failed: {e}') from e


def wyoming_health(endpoint: str, timeout: float = 5.0) -> str:
    host, port = parse_endpoint(endpoint)
    client = WyomingClient(host, port, timeout=timeout)
    try:
        client.write_event('describe', {})
        try:
            type_, _data, _payload = client.read_event()
        except WyomingTransportError:
            return 'TTS_SERVICE_UNHEALTHY'
        if type_ in ('info', 'description', 'error'):
            return 'TTS_READY' if type_ != 'error' else 'TTS_SERVICE_UNHEALTHY'
        return 'TTS_READY'
    except WyomingTransportError as e:
        if e.code == 'TTS_SERVICE_UNREACHABLE':
            return 'TTS_SERVICE_UNREACHABLE'
        return 'TTS_SERVICE_UNHEALTHY'
    finally:
        client.close()


def wyoming_synthesize(
    endpoint: str,
    text: str,
    voice_name: str,
    speaker: str | None = None,
    settings: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Synthesize PCM via Wyoming and return raw PCM plus format metadata."""
    host, port = parse_endpoint(endpoint)
    settings = settings or {}
    data: dict[str, Any] = {
        'text': text,
        'voice': {'name': voice_name},
    }
    if speaker:
        data['speaker'] = speaker
    for key in ('length_scale', 'noise_scale', 'noise_w'):
        if key in settings and settings[key] is not None:
            data[key] = settings[key]

    client = WyomingClient(host, port, timeout=timeout)
    try:
        client.write_event('synthesize', data)
        audio = b''
        rate, width, channels = 22050, 2, 1
        while True:
            type_, edata, payload = client.read_event()
            if type_ == 'audio-start':
                rate = int(edata.get('rate') or rate)
                width = int(edata.get('width') or width)
                channels = int(edata.get('channels') or channels)
            elif type_ == 'audio-chunk':
                audio += payload
            elif type_ == 'audio-stop':
                break
            elif type_ == 'error':
                raise WyomingTransportError('SYNTHESIS_FAILED', str(edata.get('text') or edata or 'Wyoming error'))
            else:
                # Ignore unrelated events (info, etc.)
                continue
        if not audio:
            raise WyomingTransportError('SYNTHESIS_FAILED', 'empty audio from Wyoming')
        return {
            'pcm': audio,
            'sample_rate': rate,
            'sample_width': width,
            'channels': channels,
        }
    finally:
        client.close()
