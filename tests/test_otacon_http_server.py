#!/usr/bin/env python3
"""OtaconHTTPServer must apply listen backlog before socket.listen()."""
from __future__ import annotations

import socket
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from installer.server import OtaconHTTPServer  # noqa: E402


class _QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


class OtaconHTTPServerBacklogTests(unittest.TestCase):
    def test_class_attr_is_128_not_default_five(self):
        self.assertEqual(OtaconHTTPServer.request_queue_size, 128)
        self.assertEqual(ThreadingHTTPServer.request_queue_size, 5)

    def test_listen_receives_128_during_construction(self):
        """Prove backlog is passed to listen() — post-construct assign is too late."""
        seen: list[int] = []
        real_listen = socket.socket.listen

        def spy_listen(self, backlog=-1):  # noqa: ANN001
            seen.append(backlog)
            return real_listen(self, backlog)

        with mock.patch.object(socket.socket, "listen", spy_listen):
            httpd = OtaconHTTPServer(("127.0.0.1", 0), _QuietHandler)
            self.addCleanup(httpd.server_close)
        self.assertIn(128, seen)
        self.assertEqual(httpd.request_queue_size, 128)

    def test_post_construct_assign_does_not_relisten(self):
        """Document the bug Crist hit: instance assign after __init__ is a no-op."""
        seen: list[int] = []
        real_listen = socket.socket.listen

        def spy_listen(self, backlog=-1):  # noqa: ANN001
            seen.append(backlog)
            return real_listen(self, backlog)

        with mock.patch.object(socket.socket, "listen", spy_listen):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
            self.addCleanup(httpd.server_close)
        self.assertEqual(seen, [5])
        httpd.request_queue_size = 128
        self.assertEqual(httpd.request_queue_size, 128)
        # No second listen — kernel backlog stays at 5.
        self.assertEqual(seen, [5])


if __name__ == "__main__":
    unittest.main()
