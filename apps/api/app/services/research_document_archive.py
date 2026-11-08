"""Portable current-document archives: original bytes, no executable extraction."""

import hashlib
import io
import json
import zipfile
from uuid import UUID

from app.services.research_documents import DOCUMENT_FORMAT, DocumentContent

ARCHIVE_MAX_BYTES = 64 * 1024 * 1024


def read_document_archive(data: bytes):
    if not data or len(data) > ARCHIVE_MAX_BYTES:
        raise ValueError("Document archive exceeds the size limit")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(infos) > 103 or len(set(names)) != len(names):
            raise ValueError("Duplicate or excessive archive entries")
        if sum(item.file_size for item in infos) > ARCHIVE_MAX_BYTES:
            raise ValueError("Expanded archive exceeds the size limit")
        manifest_info = archive.getinfo("document.json")
        if manifest_info.file_size > 2_000_000:
            raise ValueError("Document manifest exceeds the size limit")
        manifest = json.loads(archive.read(manifest_info))
        if manifest.get("format") != DOCUMENT_FORMAT:
            raise ValueError("Unsupported document archive format")
        content = DocumentContent.model_validate(manifest["content"])
        files = manifest.get("files", [])
        if not isinstance(files, list) or len(files) > 100:
            raise ValueError("Invalid attachment manifest")
        expected = {"document.json", "document.aimd"}
        attachments = []
        seen = set()
        for item in files:
            identity = str(UUID(item["id"]))
            if identity in seen:
                raise ValueError("Duplicate attachment identity")
            seen.add(identity)
            path = f"files/{identity}"
            expected.add(path)
            body = archive.read(path)
            if (
                len(body) != item["size_bytes"]
                or hashlib.sha256(body).hexdigest() != item["sha256"]
            ):
                raise ValueError("Attachment checksum mismatch")
            filename = item["filename"]
            if (
                not isinstance(filename, str)
                or not filename
                or len(filename) > 512
                or any(c in filename for c in ("/", "\\", "\x00", "\r", "\n"))
            ):
                raise ValueError("Invalid original filename")
            attachments.append((item, body))
        if set(names) != expected or set(map(str, content.file_ids)) != seen:
            raise ValueError("Archive contains missing or unexpected content")
        if archive.read("document.aimd").decode("utf-8") != content.body:
            raise ValueError("AIMD source differs from the document manifest")
        return content, attachments, manifest
