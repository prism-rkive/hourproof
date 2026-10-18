"""The local dashboard server serves the React build like the host does: deep links get the app, files are files,
unknown API paths are JSON 404s, and the live API is unchanged. Without a build, every page says to run `make web`."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hourproof import server


class _Resp:
    def __init__(self, status: int, body: bytes):
        self.status_code, self.text = status, body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.text)


class AsgiClient:
    """A minimal GET client that drives the ASGI app in-process (no extra test dependency)."""

    def __init__(self, app):
        self.app = app

    def get(self, path: str) -> _Resp:
        raw = path.encode()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": path, "raw_path": raw, "query_string": b"", "root_path": "", "headers": [],
                 "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
        out = {"status": 0, "body": b""}
        sent = []

        async def receive():  # the request once; then, like an open connection, nothing until cancelled
            if not sent:
                sent.append(1)
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.start":
                out["status"] = msg["status"]
            elif msg["type"] == "http.response.body":
                out["body"] += msg.get("body", b"")

        asyncio.run(self.app(scope, receive, send))
        return _Resp(out["status"], out["body"])


class SpaServingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        dist = Path(self.tmp.name)
        (dist / "assets").mkdir()
        (dist / "index.html").write_text("<!doctype html><title>app</title>")
        (dist / "assets" / "index-abc.js").write_text("console.log(1)")
        self.patch = mock.patch.object(server, "FRONTEND_DIST", dist)
        self.patch.start()
        self.client = AsgiClient(server.app)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_every_page_route_gets_the_app(self):
        for path in ("/", "/proof", "/security", "/agent", "/carbon", "/note", "/method", "/no-such-page"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("<title>app</title>", r.text, path)

    def test_build_files_are_served_as_files(self):
        r = self.client.get("/assets/index-abc.js")
        self.assertEqual((r.status_code, r.text), (200, "console.log(1)"))

    def test_unknown_api_paths_are_json_404_and_never_the_app(self):
        r = self.client.get("/api/missing")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {"error": "not found"})

    def test_paths_outside_the_build_are_not_served(self):
        r = self.client.get("/../../hourproof/server.py")
        self.assertNotIn("FRONTEND_DIST", r.text)

    def test_the_live_api_is_unchanged(self):
        r = self.client.get("/api/overview")
        self.assertEqual(r.status_code, 200)
        self.assertIn("running", r.json())
        self.assertEqual(self.client.get("/api/demo/log").json().keys(), {"running", "log"})

    def test_without_a_build_every_page_says_to_run_make_web_and_the_api_still_works(self):
        with mock.patch.object(server, "FRONTEND_DIST", Path(self.tmp.name) / "missing"):
            for path in ("/", "/proof", "/no-such-page"):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 503, path)
                self.assertIn("make web", r.text, path)
            self.assertEqual(self.client.get("/api/overview").status_code, 200)

if __name__ == "__main__":
    unittest.main()
