"""Build a versioned, prose-only revision from the server's immutable source."""

import re
import tomllib
from pathlib import Path

from airalogy.assigner.graph import extract_assigner_graph_nodes_from_aimd
from airalogy.markdown import generate_model, parse_aimd
from airalogy.markdown.errors import AimdParseError

from app.services.protocol_exports import extract_protocol_source, zip_protocol_source


def field_definitions(content):
    positions = {"start_line", "end_line", "start_col", "end_col"}
    return {
        kind: [
            {k: v for k, v in item.items() if k not in positions}
            if isinstance(item, dict)
            else item
            for item in items
        ]
        for kind, items in parse_aimd(content)["templates"].items()
    }


def revised_package(source: Path, workspace: Path, content: str, version: str):
    root = workspace / "protocol"
    extract_protocol_source(source, root)
    document = root / "protocol.aimd"
    original = document.read_text(encoding="utf-8")
    if original.strip() == content.strip():
        raise ValueError("Protocol text has not changed")
    try:
        same_definition = (
            field_definitions(content) == field_definitions(original)
            and generate_model(content) == generate_model(original)
            and extract_assigner_graph_nodes_from_aimd(content)
            == extract_assigner_graph_nodes_from_aimd(original)
        )
    except AimdParseError as exc:
        raise ValueError("Invalid AIMD document") from exc
    if not same_definition:
        raise ValueError(
            "A text revision must preserve field definitions and executable blocks"
        )
    manifest = root / "protocol.toml"
    text = manifest.read_text(encoding="utf-8")
    expected = tomllib.loads(text)
    expected["airalogy_protocol"]["version"] = version
    section = re.search(
        r"(?ms)^\s*\[airalogy_protocol\][ \t]*(?:#[^\n]*)?\n(.*?)(?=^\s*\[|\Z)", text
    )
    if not section:
        raise ValueError("Protocol manifest has no metadata section")
    fields = re.sub(
        r"""(?m)^([ \t]*version[ \t]*=[ \t]*)["'][^"'\n]+["']""",
        lambda m: m[1] + '"' + version + '"',
        section[1],
        count=1,
    )
    updated = text[: section.start(1)] + fields + text[section.end(1) :]
    if tomllib.loads(updated) != expected:
        raise ValueError("Protocol manifest version could not be updated")
    manifest.write_text(updated, encoding="utf-8")
    document.write_text(content, encoding="utf-8")
    return zip_protocol_source(root, workspace / "revision.zip")
