import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "airalogy_agent", Path(__file__).resolve().parents[2] / "tools/airalogy_agent.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TOKEN = "apl_" + "synthetic_" * 5


class ClientTests(unittest.TestCase):
    def test_plaintext_remote_credentials_and_unsafe_paths_are_rejected(self):
        for url in [
            "http://example.test",
            "https://user:password@example.test",
            "https://example.test/path",
            "https://example.test/?token=secret",
        ]:
            with self.subTest(url=url), self.assertRaises(module.ClientError):
                module.Client(url, TOKEN)
        client = module.Client("https://example.test", TOKEN)
        with self.assertRaises(module.ClientError):
            client.call("../grants", {})

    def test_transport_and_redirect_never_forward_credentials(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(
                    (
                        self.path,
                        self.headers.get("Authorization"),
                        json.loads(
                            self.rfile.read(int(self.headers["Content-Length"]))
                        ),
                    )
                )
                if self.path.endswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "https://example.test/steal")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                client = module.Client(f"http://127.0.0.1:{server.server_port}", TOKEN)
                self.assertEqual(client.call("access_context", {}), {"ok": True})
                with self.assertRaises(module.ClientError):
                    client.call("redirect", {})
            finally:
                server.shutdown()
                worker.join()
        self.assertEqual(len(seen), 2)
        self.assertEqual(
            seen[0],
            ("/api/external-access/tools/access_context", "Bearer " + TOKEN, {}),
        )

    def test_snapshot_pages_keep_the_same_digest(self):
        client = module.Client("https://example.test", TOKEN)
        pages = iter(
            [
                {"snapshot_id": "id", "digest": "a", "items": [1], "next_offset": 1},
                {"digest": "a", "items": [2], "next_offset": None},
            ]
        )
        client.call = lambda *args: next(pages)
        self.assertEqual(client.snapshot({"sources": []})["items"], [1, 2])
        pages = iter(
            [
                {"snapshot_id": "id", "digest": "a", "items": [1], "next_offset": 1},
                {"digest": "changed", "items": [2], "next_offset": None},
            ]
        )
        with self.assertRaises(module.ClientError):
            client.snapshot({"sources": []})

    def test_local_files_are_never_overwritten_or_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "protocol.aimd").write_text("{{var|value: float}}")
            (root / "protocol.toml").write_text(
                '[airalogy_protocol]\nid="synthetic"\nversion="1.0.0"'
            )
            (root / ".env").write_text("not-a-real-credential")
            self.assertNotIn(".env", module.sources(root))
            with self.assertRaises(FileExistsError):
                module.write_new(root / "protocol.aimd", b"changed")
            (root / "linked.py").symlink_to(root / ".env")
            with self.assertRaises(module.ClientError):
                module.sources(root)


if __name__ == "__main__":
    unittest.main()
