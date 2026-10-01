from __future__ import annotations

import json
import socket
import threading
import unittest
from http.client import HTTPConnection

from acc.server import create_server, snapshot


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.server = create_server(port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.host = f"127.0.0.1:{self.port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path: str, headers: dict[str, str] | None = None, method: str = "GET"):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=2)
        connection.request("GET" if method == "GET" else method, path,
                           headers={"Host": self.host, **(headers or {})})
        response = connection.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        connection.close()
        return result

    def test_binds_only_to_ipv4_loopback(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_snapshot_is_an_explicit_empty_state(self) -> None:
        data = snapshot()
        self.assertEqual(data["status"], "not_connected")
        self.assertEqual(data["sessions"], [])
        self.assertIsNone(data["observed_at"])
        status, headers, body = self.request("/api/snapshot")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body), data)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_static_files_are_allowlisted_and_have_security_headers(self) -> None:
        paths = (("/", b"Not connected"), ("/app.js", b"textContent"), ("/style.css", b"color-scheme"))
        for path, expected in paths:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(expected, body)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(headers["X-Frame-Options"], "DENY")
                self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def test_unknown_paths_and_methods_are_rejected(self) -> None:
        self.assertEqual(self.request("/secret")[0], 404)
        self.assertEqual(self.request("/api/snapshot", method="POST")[0], 405)

    def test_foreign_host_and_origin_are_rejected(self) -> None:
        self.assertEqual(self.request("/", {"Host": "example.com"})[0], 421)
        self.assertEqual(self.request("/api/snapshot", {"Origin": "https://example.test"})[0], 403)

    def test_same_origin_and_fetch_metadata_are_checked(self) -> None:
        self.assertEqual(self.request("/api/snapshot", {"Origin": f"http://{self.host}"})[0], 200)
        self.assertEqual(self.request("/api/snapshot", {"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_port_must_be_an_integer_in_local_port_range(self) -> None:
        for value in (True, 0, -1, 65536, "8765", 3.14):
            with self.subTest(value=value), self.assertRaises(ValueError):
                create_server(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
