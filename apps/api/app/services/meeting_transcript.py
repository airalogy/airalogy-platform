"""UTF-8 timed text interchange. Times are integer milliseconds from recording start."""

import html
import re
from io import BytesIO, StringIO
from pathlib import Path
from typing import Literal
from uuid import UUID

import webvtt
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Cue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    speaker: str = Field(default="", max_length=255)
    account_id: UUID | None = None
    text: str = Field(min_length=1, max_length=200000)

    @model_validator(mode="after")
    def valid_range(self):
        if (
            (self.start is None) != (self.end is None)
            or self.start is not None
            and self.end <= self.start
        ):
            raise ValueError("Invalid cue time range")
        if "\n" in self.speaker or "\r" in self.speaker:
            raise ValueError("Speaker labels must fit on one line")
        return self


VOICE = re.compile(r"<v(?:\.[^\s>]+)*[ \t]+([^>]+)>(.*?)(?:</v>|(?=<v[ .])|$)", re.S)
PREFIX = re.compile(r"^(?:>>\s*)?([^:\n：<>]{1,64})[：:]\s*(?!/)(.+)$", re.S)
MARKUP = re.compile(r"</?(?:[biu]|ruby|rt|lang|c)(?:[. ][^>]*)?>|<\d[\d:.]*>")


def timestamp(value):
    seconds, ms = divmod(value, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{ms:03}"


def spoken_parts(body):
    pos = 0
    for voice in VOICE.finditer(body):
        if body[pos : voice.start()].strip():
            yield "", body[pos : voice.start()]
        yield html.unescape(voice[1]), voice[2]
        pos = voice.end()
    if body[pos:].strip():
        yield "", body[pos:]


def srt_speakers(body):
    """Many exporters place separate named utterances on lines of one SRT cue."""
    speaker, lines = "", []
    for line in body.splitlines():
        label = PREFIX.match(line.removeprefix("- ").strip())
        if label:
            if lines:
                yield speaker, "\n".join(lines)
            speaker, words = label.groups()
            lines = [words]
        else:
            lines.append(line)
    if lines:
        yield speaker, "\n".join(lines)


def parse_transcript(filename: str, original: bytes) -> list[Cue]:
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        blocks = (
            (None, None, block)
            for block in original.decode("utf-8-sig").splitlines()
            if block.strip()
        )
    elif ext in {".srt", ".vtt"}:
        document = webvtt.from_buffer(
            BytesIO(original), format=ext[1:], strict=ext == ".vtt"
        )
        if document.parse_issues:
            raise ValueError(
                "Invalid subtitle near line " + str(document.parse_issues[0].line)
            )
        blocks = (
            (c.start_in_milliseconds, c.end_in_milliseconds, c.raw_text)
            for c in document
        )
    else:
        raise ValueError("Choose SRT, WebVTT or TXT")
    cues = []
    for start, end, body in blocks:
        parts = (
            spoken_parts(body)
            if ext == ".vtt"
            else srt_speakers(body)
            if ext == ".srt"
            else [("", body)]
        )
        for speaker, words in parts:
            if ext != ".txt":
                words = html.unescape(MARKUP.sub("", words)).strip()
            prefix = PREFIX.match(words) if not speaker else None
            if prefix:
                speaker, words = prefix.groups()
            cues.append(Cue(start=start, end=end, speaker=speaker, text=words))
            if len(cues) > 20000:
                raise ValueError("Too many transcript segments")
    if not cues:
        raise ValueError("Empty transcript")
    return cues


def export_transcript(cues: list[Cue], fmt: Literal["vtt", "srt", "txt"]) -> str:
    def labeled(c):
        return f"{c.speaker}：{c.text}" if c.speaker else c.text

    if fmt == "txt":
        return "\n\n".join(labeled(c) for c in cues) + "\n"
    captions = []
    for c in cues:
        if c.start is None or c.end is None:
            raise ValueError("Timed subtitles need a time range for every segment")
        words = html.escape(c.text, quote=False)
        if c.speaker and fmt == "vtt":
            words = f"<v {html.escape(c.speaker, quote=False)}>{words}</v>"
        elif fmt == "srt":
            words = html.escape(labeled(c), quote=False)
        captions.append(webvtt.Caption(timestamp(c.start), timestamp(c.end), words))
    out = StringIO()
    webvtt.WebVTT(captions=captions).write(out, format=fmt)
    return out.getvalue()
