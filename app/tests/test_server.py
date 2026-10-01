"""Server smoke tests: loopback-only, routes, demo/live modes (ACC-07/12)."""
import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from server import Handler, build_poller


def start_server(demo):
    poller, mode = build_poller(demo=demo)
    poller.poll_once()
    Handler.poller = poller
    Handler.mode = mode
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2},
                         daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.read()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = start_server(demo=True)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_binds_loopback_only(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_health(self):
        status, body = get(self.base, "/api/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["mode"], "demo")
        self.assertEqual(sorted(data["providers"]),
                         ["Claude Code", "Codex", "Hermes"])

    def test_sessions_shape(self):
        status, body = get(self.base, "/api/sessions")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["mode"], "demo")
        by_name = {p["provider"]: p for p in data["providers"]}

        hermes = by_name["Hermes"]
        self.assertTrue(hermes["ok"])
        main = next(s for s in hermes["sessions"]
                    if s["session_id"] == "hermes-main")
        self.assertEqual(main["percent_used"], 21)
        self.assertEqual(main["context_limit"], 200000)
        self.assertEqual(main["freshness"], "fresh")

        claude = by_name["Claude Code"]
        parent = next(s for s in claude["sessions"]
                      if s["session_id"] == "cc-parent")
        self.assertEqual(parent["freshness"], "stale")
        child = next(s for s in claude["sessions"]
                     if s["session_id"] == "cc-child-3")
        self.assertIsNone(child["percent_used"])
        self.assertIsNotNone(child["unavailable_reason"])

        codex = by_name["Codex"]
        self.assertFalse(codex["ok"])
        self.assertIn("locked", codex["error"])

    def test_activity_feed_newest_first_data_present(self):
        _, body = get(self.base, "/api/sessions")
        data = json.loads(body)
        tools = [t for p in data["providers"] for s in p["sessions"]
                 for t in s["tools"]]
        self.assertTrue(len(tools) >= 5)
        for t in tools:
            self.assertIn(t["outcome"], ("ok", "error"))
            self.assertTrue(t["tool"])

    def test_index_served(self):
        status, body = get(self.base, "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>AI Command Center</title>", body)
        self.assertIn(b"/ui/app.js", body)

    def test_static_js_served(self):
        status, body = get(self.base, "/ui/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"api/sessions", body)

    def test_no_traversal(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get(self.base, "/ui/../server.py")
        self.assertEqual(ctx.exception.code, 404)

    def test_read_only_no_post(self):
        req = urllib.request.Request(self.base + "/api/sessions",
                                     data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertNotEqual(ctx.exception.code, 200)


class LiveModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = start_server(demo=False)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_live_mode_with_no_adapters_is_honestly_empty(self):
        """No silent fallback to demo data: empty registry, empty providers."""
        _, body = get(self.base, "/api/sessions")
        data = json.loads(body)
        self.assertEqual(data["mode"], "live")
        self.assertEqual(data["providers"], [])


if __name__ == "__main__":
    unittest.main()
