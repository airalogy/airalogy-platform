#!/usr/bin/env python3
"""Airalogy Platform HTTP client/CLI. Credentials stay in the caller's environment.

Import Client for Python automation, or run --help. No model or cloud relay is used.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

MAX_RESPONSE = 20 * 1024 * 1024


class ClientError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClientError("Redirect refused: configure the exact Platform instance URL")


class Client:
    """Uses exactly the same scoped tools as MCP, including browser confirmation."""

    def __init__(self, instance: str, token: str):
        parsed = urllib.parse.urlsplit(instance)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") not in ("", "/api")
        ):
            raise ClientError(
                "Use an instance origin, without credentials, query or extra path"
            )
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost", "::1")
        ):
            raise ClientError(
                "HTTPS is required except for a loopback development instance"
            )
        if not parsed.hostname or not re.fullmatch(r"apl_[A-Za-z0-9_-]{20,96}", token):
            raise ClientError("A valid scoped Platform token is required")
        self.endpoint = (
            instance.rstrip("/").removesuffix("/api") + "/api/external-access/tools/"
        )
        self._token = token
        self._opener = urllib.request.build_opener(
            NoRedirect(),
            *(
                [urllib.request.ProxyHandler({})]
                if parsed.hostname in ("127.0.0.1", "localhost", "::1")
                else []
            ),
        )

    def call(self, tool: str, arguments: dict):
        if not re.fullmatch(r"[a-z_]{1,80}", tool):
            raise ClientError("Invalid tool name")
        data = json.dumps(arguments, allow_nan=False).encode()
        if len(data) > 2 * 1024 * 1024:
            raise ClientError("Request exceeds the 2 MiB tool limit")
        request = urllib.request.Request(
            self.endpoint + tool,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=120) as response:
                content = response.read(MAX_RESPONSE + 1)
                if len(content) > MAX_RESPONSE:
                    raise ClientError("Response exceeds the bounded client limit")
                return json.loads(content)
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read(32_768)).get("detail", {})
                code = (
                    detail.get("code", "request_failed")
                    if isinstance(detail, dict)
                    else "request_failed"
                )
            except (ValueError, AttributeError):
                code = "request_failed"
            raise ClientError(
                f"HTTP {error.code}: {code}. Review permissions, current versions and Platform confirmation."
            ) from None
        except urllib.error.URLError as error:
            raise ClientError(
                "Connection failed. Check the instance address, network and trusted TLS certificate."
            ) from error

    def snapshot(self, selection: dict):
        first = self.call(
            "create_snapshot",
            {**selection, "request_key": selection.get("request_key", uuid4().hex)},
        )
        rows = list(first["items"])
        offset = first["next_offset"]
        while offset is not None:
            page = self.call(
                "read_snapshot", {"snapshot_id": first["snapshot_id"], "offset": offset}
            )
            if page["digest"] != first["digest"]:
                raise ClientError("Snapshot changed during pagination")
            rows.extend(page["items"])
            offset = page["next_offset"]
        return {**first, "items": rows, "next_offset": None}

    def download(self, args: dict, output: Path):
        metadata = self.call(
            "read_research_file", {**args, "expected_sha256": None, "offset": 0}
        )
        if metadata["size_bytes"] > 16 * 1024 * 1024:
            raise ClientError("File exceeds the 16 MiB external download limit")
        content, offset = bytearray(), 0
        while offset is not None:
            part = self.call(
                "read_research_file",
                {**args, "expected_sha256": metadata["sha256"], "offset": offset},
            )
            if part["sha256"] != metadata["sha256"] or part["offset"] != offset:
                raise ClientError("File changed during download")
            content.extend(base64.b64decode(part["content_base64"], validate=True))
            if len(content) > 16 * 1024 * 1024:
                raise ClientError("Download limit exceeded")
            offset = part["next_offset"]
        if (
            len(content) != metadata["size_bytes"]
            or hashlib.sha256(content).hexdigest() != metadata["sha256"]
        ):
            raise ClientError("Download checksum mismatch")
        write_new(output, bytes(content))
        return metadata


def write_new(path: Path, content: bytes):
    # Never silently overwrite a local Protocol, dataset or report.
    with path.open("xb") as stream:
        stream.write(content)


def workspace(directory: Path):
    result, binary = {}, {}
    if not directory.is_dir():
        raise ClientError("Expected a Protocol workspace directory")
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if any(p.startswith(".") or p == "__pycache__" for p in relative.parts):
            continue
        if path.is_symlink():
            raise ClientError("Symlinks are not allowed in a candidate workspace")
        if path.is_file():
            if path.suffix.lower() not in {
                ".aimd",
                ".toml",
                ".py",
                ".json",
                ".md",
                ".csv",
                ".tsv",
                ".txt",
                ".svg",
                ".yaml",
                ".yml",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".pdf",
            }:
                raise ClientError(f"Unsupported candidate source file: {relative}")
            if path.stat().st_size > 1_000_000:
                raise ClientError("Candidate source exceeds 1 MB")
            if path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".pdf",
            }:
                binary[relative.as_posix()] = base64.b64encode(
                    path.read_bytes()
                ).decode()
            else:
                result[relative.as_posix()] = path.read_text(encoding="utf-8")
    if (
        not {"protocol.aimd", "protocol.toml"} <= result.keys()
        or len(result) + len(binary) > 50
        or sum(len(v.encode()) for v in result.values())
        + sum(len(base64.b64decode(v)) for v in binary.values())
        > 1_000_000
    ):
        raise ClientError(
            "Expected protocol.aimd + protocol.toml, at most 50 files / 1 MB"
        )
    return result, binary


def sources(directory: Path):
    return workspace(directory)[0]


def check_sources(files):
    try:
        from airalogy.assigner.graph import (
            extract_assigner_graph_nodes_from_aimd,
            extract_server_assigner_graph_nodes_from_python,
            validate_assigner_graph,
        )
        from airalogy.markdown import validate_aimd
    except ImportError as error:
        raise ClientError(
            "Install the same official airalogy package version as your Platform executor before local checks"
        ) from error
    nodes = []
    for name, content in files.items():
        if name.endswith(".aimd"):
            valid, errors = validate_aimd(content)
            if not valid:
                raise ClientError(f"{name}: " + "; ".join(str(e) for e in errors))
            nodes.extend(extract_assigner_graph_nodes_from_aimd(content))
        elif name.endswith(".py"):
            ast.parse(content, filename=name)
            if name == "assigner.py":
                nodes.extend(
                    extract_server_assigner_graph_nodes_from_python(
                        content, source=name
                    )
                )
        elif name.endswith(".toml"):
            tomllib.loads(content)
    validate_assigner_graph(nodes)
    return {"status": "valid", "level": "static", "server_validation_required": True}


def login(instance, client_id, scopes, port, token_file):
    import secrets
    import time
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    if token_file.exists():
        raise ClientError("Credential file already exists; choose a new private path")
    # Reuse origin/TLS checks and redirect refusal without a real bearer credential.
    transport = Client(instance, "apl_" + "placeholder_" * 4)
    origin = transport.endpoint.removesuffix("/api/external-access/tools/")
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(32)
    callback = f"http://127.0.0.1:{port}/callback"
    outcome = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if (
                parsed.path != "/callback"
                or query.get("state") != [state]
                or not (query.get("code") or query.get("error"))
            ):
                self.send_error(400)
                return
            outcome.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authorization received. Return to the terminal.")

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", port), Callback) as server:
        server.timeout = 1
        request = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": callback,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": scopes,
            "resource": origin + "/api/external-access",
        }
        address = (
            origin
            + "/api/external-access/oauth/authorize?"
            + urllib.parse.urlencode(request)
        )
        print(
            "Opening Platform authorization. Choose a Project and review the requested actions.",
            file=sys.stderr,
        )
        if not webbrowser.open(address):
            raise ClientError(
                "Could not open a browser; use a scoped token connection instead"
            )
        deadline = time.monotonic() + 300
        while not outcome and time.monotonic() < deadline:
            server.handle_request()
    if not outcome.get("code"):
        raise ClientError("Authorization cancelled or timed out")
    payload = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": callback,
            "resource": request["resource"],
            "code": outcome["code"],
            "code_verifier": verifier,
        }
    ).encode()
    exchange = urllib.request.Request(
        origin + "/api/external-access/oauth/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with transport._opener.open(exchange, timeout=30) as response:
            result = json.loads(response.read(8192))
    except urllib.error.URLError as error:
        raise ClientError(
            "Token exchange failed; restart browser authorization"
        ) from error
    descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(
            {
                "instance": origin,
                "token": result["access_token"],
                "expires_at": time.time() + result["expires_in"],
            },
            output,
        )
    return {
        "connected": True,
        "credential_file": str(token_file),
        "instruction": "Set AIRALOGY_PLATFORM_TOKEN_FILE to this private file path. Never share or commit it.",
    }


def token_from_environment(instance):
    import stat
    import time

    token = os.environ.get("AIRALOGY_PLATFORM_TOKEN")
    if token:
        return token
    filename = os.environ.get("AIRALOGY_PLATFORM_TOKEN_FILE")
    if not filename:
        return ""
    path = Path(filename)
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_mode & 0o077
        or not hasattr(os, "getuid")
        or details.st_uid != os.getuid()
        or details.st_size > 8192
    ):
        raise ClientError("Credential file must be private to its owner (mode 600)")
    data = json.loads(path.read_text())
    if (
        data["instance"] != instance.rstrip("/").removesuffix("/api")
        or data["expires_at"] <= time.time()
    ):
        raise ClientError("Credential belongs to another instance or has expired")
    return data["token"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instance", default=os.environ.get("AIRALOGY_PLATFORM_URL", "")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("context")
    auth = commands.add_parser("login")
    auth.add_argument("--client-id", required=True)
    auth.add_argument("--scopes", default="protocols:read records:read")
    auth.add_argument("--port", type=int, default=8765)
    auth.add_argument("--token-file", type=Path, required=True)
    preview = commands.add_parser("preview")
    preview.add_argument("--port", type=int, default=3109)
    call = commands.add_parser("call")
    call.add_argument("tool")
    call.add_argument("json_file", type=Path)
    snap = commands.add_parser("snapshot")
    snap.add_argument("selection", type=Path)
    snap.add_argument("output", type=Path)
    check = commands.add_parser("check")
    check.add_argument("directory", type=Path)
    candidate = commands.add_parser("candidate")
    candidate.add_argument("directory", type=Path)
    candidate.add_argument("--protocol-id")
    candidate.add_argument("--base-version-id")
    candidate.add_argument("--request-key", default=None)
    package = commands.add_parser("source")
    package.add_argument("protocol_id")
    package.add_argument("version")
    package.add_argument("output", type=Path)
    package.add_argument("--format", choices=["aira", "zip"], default="aira")
    download = commands.add_parser("download")
    download.add_argument("selection", type=Path)
    download.add_argument("output", type=Path)
    for name in ("status", "execute"):
        command = commands.add_parser(name)
        command.add_argument("operation_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "login":
            print(
                json.dumps(
                    login(
                        args.instance,
                        args.client_id,
                        args.scopes,
                        args.port,
                        args.token_file,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.command == "preview":
            from functools import partial
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

            directory = (
                Path(__file__).resolve().parents[1] / "apps/web/dist-agent-preview"
            )
            if not (directory / "agent-preview.html").is_file():
                raise ClientError(
                    "Build the official local preview first: pnpm agent:preview:build"
                )

            class PreviewHandler(SimpleHTTPRequestHandler):
                def end_headers(self):
                    self.send_header("Cache-Control", "no-store")
                    self.send_header(
                        "Content-Security-Policy",
                        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'",
                    )
                    super().end_headers()

                def list_directory(self, path):
                    self.send_error(403)

            with ThreadingHTTPServer(
                ("127.0.0.1", args.port),
                partial(PreviewHandler, directory=str(directory)),
            ) as server:
                print(
                    f"Local-only preview: http://127.0.0.1:{server.server_port}/agent-preview.html",
                    flush=True,
                )
                server.serve_forever()
            return 0
        if args.command == "check":
            result = check_sources(sources(args.directory))
        else:
            client = Client(args.instance, token_from_environment(args.instance))
            if args.command == "context":
                result = client.call("access_context", {})
            elif args.command == "call":
                result = client.call(args.tool, json.loads(args.json_file.read_text()))
            elif args.command == "candidate":
                files, binary_files = workspace(args.directory)
                check_sources(files)
                result = client.call(
                    "preview_protocol_candidate",
                    {
                        "request_key": args.request_key or uuid4().hex,
                        "protocol_id": args.protocol_id,
                        "base_version_id": args.base_version_id,
                        "files": files,
                        "binary_files": binary_files,
                    },
                )
            elif args.command == "snapshot":
                result = client.snapshot(json.loads(args.selection.read_text()))
                write_new(
                    args.output,
                    json.dumps(result, ensure_ascii=False, indent=2).encode(),
                )
                result = {
                    k: v for k, v in result.items() if k not in ("items", "sources")
                }
            elif args.command == "source":
                result = client.call(
                    "download_protocol_source",
                    {
                        "protocol_id": args.protocol_id,
                        "version": args.version,
                        "format": args.format,
                    },
                )
                content = base64.b64decode(result.pop("content_base64"), validate=True)
                if hashlib.sha256(content).hexdigest() != result["sha256"]:
                    raise ClientError("Source checksum mismatch")
                write_new(args.output, content)
            elif args.command == "download":
                result = client.download(
                    json.loads(args.selection.read_text()), args.output
                )
            else:
                result = client.call(
                    "operation_status"
                    if args.command == "status"
                    else "execute_operation",
                    {"operation_id": args.operation_id},
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ClientError, ValueError, OSError, SyntaxError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
