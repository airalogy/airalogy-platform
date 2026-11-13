# /// script
# requires-python = ">=3.11"
# dependencies = ["edge-tts==7.3.1"]
# ///
"""Explicit, build-time speech generation. Only reviewed public scripts leave this host."""

import asyncio
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/demos/narration.json"
CACHE = ROOT / "tests/e2e/.runtime/learning-demos/narration"


async def main():
    script_bytes = SCRIPT.read_bytes()
    script = json.loads(script_bytes)
    if script["engine"] != "edge-tts" or script["engine_version"] != version("edge-tts"):
        raise ValueError("Use the speech engine version pinned in narration.json")
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = {
        "script_sha256": hashlib.sha256(script_bytes).hexdigest(),
        "lessons": {},
    }
    for lesson, cues in script["lessons"].items():
        manifest["lessons"][lesson] = []
        for index, cue in enumerate(cues):
            text = cue.get("speech", cue["zh"])
            key = hashlib.sha256(json.dumps(
                [script["engine_version"], script["voice"], script["rate"], text],
                ensure_ascii=False,
            ).encode()).hexdigest()
            target = CACHE / f"{key}.mp3"
            checksum = CACHE / f"{key}.sha256"
            cached = (target.exists() and checksum.exists()
                      and hashlib.sha256(target.read_bytes()).hexdigest() == checksum.read_text())
            if not cached:
                temporary = target.with_suffix(".partial")
                for attempt in range(3):
                    try:
                        speech = edge_tts.Communicate(
                            text, script["voice"], rate=script["rate"],
                            connect_timeout=15, receive_timeout=45,
                        )
                        await asyncio.wait_for(speech.save(str(temporary)), timeout=90)
                        if temporary.stat().st_size < 1000:
                            raise ValueError("Incomplete narration")
                        temporary.replace(target)
                        checksum.write_text(hashlib.sha256(target.read_bytes()).hexdigest())
                        break
                    except Exception:
                        temporary.unlink(missing_ok=True)
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)
            manifest["lessons"][lesson].append({
                "file": target.name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            })
            print(f"Narrated {lesson} {index + 1}/{len(cues)}{' (cached)' if cached else ''}", flush=True)
    temporary = CACHE / "manifest.partial.json"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(CACHE / "manifest.json")


if __name__ == "__main__":
    asyncio.run(main())
