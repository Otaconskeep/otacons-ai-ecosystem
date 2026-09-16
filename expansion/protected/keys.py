"""Platform key-provider interface for Expansion secrets.

Never store plaintext keys in BAT, PowerShell, Python source, JavaScript,
JSON configs, env files, or logs. Keys live behind this abstraction.

Windows: DPAPI (stub + interface ready).
Linux: permissioned key file under secrets/ (0600) or future secret-service.
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout


class KeyProvider(ABC):
    """Swappable platform-specific secret storage."""

    @abstractmethod
    def store(self, name: str, material: bytes) -> None:
        ...

    @abstractmethod
    def load(self, name: str) -> bytes:
        ...

    @abstractmethod
    def delete(self, name: str) -> None:
        ...

    def exists(self, name: str) -> bool:
        try:
            self.load(name)
            return True
        except KeyError:
            return False


class PermissionedFileKeyProvider(KeyProvider):
    """Linux/dev default: secrets dir with 0700 / files 0600."""

    def __init__(self, root: Optional[Path] = None, layout: Optional[StateLayout] = None):
        layout = layout or resolve_layout()
        self.root = Path(root) if root else layout.secrets_root
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def _path(self, name: str) -> Path:
        if '/' in name or '\\' in name or '..' in name:
            raise ValueError('invalid secret name')
        return self.root / f'{name}.key'

    def store(self, name: str, material: bytes) -> None:
        path = self._path(name)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, material)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def load(self, name: str) -> bytes:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return path.read_bytes()

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.is_file():
            path.unlink()


class WindowsDpapiKeyProvider(KeyProvider):
    """Windows DPAPI-backed provider (active on win32; otherwise raises)."""

    def __init__(self, root: Optional[Path] = None, layout: Optional[StateLayout] = None):
        layout = layout or resolve_layout()
        self._inner = PermissionedFileKeyProvider(
            root=root or (layout.secrets_root / 'dpapi'),
            layout=layout,
        )
        self._win32 = sys.platform == 'win32'

    def store(self, name: str, material: bytes) -> None:
        if not self._win32:
            # Interface available; material still permission-protected for cross-dev tests
            self._inner.store(name, material)
            return
        try:
            import win32crypt  # type: ignore
            protected = win32crypt.CryptProtectData(material, None, None, None, None, 0)
            self._inner.store(name, protected)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f'DPAPI protect failed: {exc}') from exc

    def load(self, name: str) -> bytes:
        raw = self._inner.load(name)
        if not self._win32:
            return raw
        try:
            import win32crypt  # type: ignore
            return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f'DPAPI unprotect failed: {exc}') from exc

    def delete(self, name: str) -> None:
        self._inner.delete(name)


def default_key_provider(layout: Optional[StateLayout] = None) -> KeyProvider:
    if sys.platform == 'win32':
        return WindowsDpapiKeyProvider(layout=layout)
    return PermissionedFileKeyProvider(layout=layout)
