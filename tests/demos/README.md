# Task-based learning demos

These are local, synthetic **product acceptance recordings**, not simulated UI, a human usability study or proof of scientific validity. All writes are to a separate private demo project or the local fixture user's personal documents. The scripts refuse non-loopback service URLs. Never point the fixture database at production.

The first-visit video stays inside the actual Platform: Home → project → Protocol → form → explicit submit → saved Record → reload, then previews document creation, the CSV template download and Protocol creation before resuming from Home. Its test rejects documentation-page navigation. It is not a recording of the written guide. The optional recording cursor follows real pointer events; no application state or successful result is staged. Only the Record is created in this overview; the other entries are previews, with their complete tasks in the four separate videos.

## Reproduce

1. Prepare the repository's isolated [browser E2E environment](../e2e/README.md), including fixtures and an API with AI disabled. Keep existing developer services and data separate.
2. Start the matching web/API services. The example below assumes `3108` / `4108`; set the URLs to your own isolated ports. The standard fixture account is local-only and is not recorded in the clips.
3. Generate examples and embedded documentation, then run the actual tasks:

```sh
pnpm demos:examples
pnpm docs:build:web
DEMO_WEB_URL=http://127.0.0.1:3108 DEMO_API_URL=http://127.0.0.1:4108 NO_PROXY=127.0.0.1,localhost,::1 pnpm demos:check --grep 'first visit|first Record|first document|first Protocol|first CSV'
DEMO_WEB_URL=http://127.0.0.1:3108 DEMO_API_URL=http://127.0.0.1:4108 NO_PROXY=127.0.0.1,localhost,::1 pnpm demos:record
```

4. The three Aira lessons are a separate, explicitly opted-in live-model acceptance. Start an isolated AI-enabled local API and matching web service with a configured provider, then run:

```sh
DEMO_LIVE_AI=1 DEMO_WEB_URL=http://127.0.0.1:3110 DEMO_API_URL=http://127.0.0.1:4110 NO_PROXY=127.0.0.1,localhost,::1 pnpm demos:record
DEMO_AI_OVERVIEW=1 DEMO_WEB_URL=http://127.0.0.1:3110 DEMO_API_URL=http://127.0.0.1:4110 NO_PROXY=127.0.0.1,localhost,::1 pnpm demos:record --grep "first visit"
```

This calls real models and may incur provider charges. Only synthetic Protocols, field values and computed demo statistics are sent. It checks generated source validation, dialogue references, field review, draft/Record persistence, deterministic group means and saved interpretation/method recovery. No intercepted model response is used. Failures are retained privately; only successful captures can become published lesson assets. These live calls are excluded from ordinary checks and pre-push.

The current local Recorder acceptance also uses the **unreleased Masterbrain source fix** for extra JSON quotes in source evidence (including numeric evidence). Build the reviewed checkout as a local wheel, install it into an isolated candidate directory and put that directory on the test API’s `PYTHONPATH`. Keep the production lockfile unchanged for this local-only verification. A clean published-package deployment is **not yet verified** for this fix; publish and pin the tested Masterbrain patch before releasing these product changes. Do not modify an installed wheel or hide this prerequisite in the acceptance report.

5. Review `docs/demos/narration.json` against the successful captures. Generate speech explicitly with `uv` (isolated, pinned `edge-tts` tool); this sends **only the reviewed public narration text** to Microsoft Edge's online speech service. No screenshots, credentials or research data are sent. Generation requires network access; ordinary builds and playback do not. Then encode with an installed FFmpeg supporting `libx264`, AAC and `mov_text` (set `DEMO_FFMPEG` to its executable if it is not on PATH):

```sh
pnpm demos:voice
pnpm demos:media
pnpm demos:verify
pnpm docs:build:web
DEMO_WEB_URL=http://127.0.0.1:3108 DEMO_API_URL=http://127.0.0.1:4108 NO_PROXY=127.0.0.1,localhost,::1 pnpm demos:check
```

Chinese AI narration is generated once and embedded in the MP4. The player does not autoplay; both language editions use the Chinese voice and can mute it or select Chinese/English captions. Playback needs no AI or speech service. The four manual tasks work without AI; the three Aira tasks require an enabled model. Captions are embedded and also supplied as WebVTT.

The renderer aligns each spoken step with its recorded action, removes the initial uncaptioned setup, keeps actions and speech at their original speed, and holds the settled image before the transition tail when needed. This avoids extending a brief page-reload frame into a long blank screen. Both caption tracks follow the resulting timeline. Speech is normalized, separated by pauses and checked for silence; every resulting video/audio stream is decoded before replacing the previous complete set. Script changes invalidate cached narration; changed recorded steps require script review. Generation retries are bounded, successful speech is content-addressed and reusable, and failed generation leaves existing lesson media intact.

Long AI waits can be cut using **visually reviewed** intervals in `docs/demos/edits.json`. Each edit is bound to the exact raw WebM SHA-256, uses zero-based step indices and source-video seconds, and must leave the trigger and result visible within the same step. New recordings invalidate these edits: review the footage and replace the ranges or remove that lesson's edits before rendering. Do not infer waits from silence or delete input, consent, review, errors or result transitions. The renderer keeps retained actions at normal speed, preserves the full narration and retimes both caption tracks. Captions and lesson pages focus on task instructions; editing provenance stays in the manifest and production files. This is not a latency benchmark. Raw recordings remain unchanged.

To update only reviewed clips without rerunning models, regenerating speech or touching the manual lessons:

```sh
DEMO_LESSONS=aira-protocol,aira-analysis pnpm demos:media
pnpm demos:verify
pnpm docs:build:web
```

## Outputs and boundaries

- `docs/demos/scenarios.json`: reviewed task instructions and examples.
- `docs/demos/narration.json`: reviewed bilingual captions, Chinese narration, pronunciation overrides and pinned voice settings. All eight lessons use the selected `zh-CN-YunyangNeural` male voice at its natural `+0%` rate; this is AI-generated speech, not a real narrator recording.
- `docs/demos/edits.json`: source-bound reviewed AI wait cuts; published edit provenance and retained source ranges are also recorded in the media manifest.
- `docs/demos/manifest.json`: capture/source identity, local-development status, media duration/hashes, narration provenance and per-step audio/video alignment.
- `docs/public/demos/`: self-hosted MP4s, posters, captions and synthetic examples. The docs build includes them under the deployment's `/docs/` path; no external video host is required.
- `tests/e2e/.runtime/learning-demos/`: ignored raw captures, speech cache, intermediate audio/video, local target URLs and failure traces. **Never commit these**: traces can include session tokens.
- Each run creates an isolated private project and synthetic personal documents. They remain for local inspection. Reset only the disposable E2E environment to remove them; do not bulk-delete existing user content.

Setup seeds the demo project and two starter Protocols through authenticated APIs. The documented actions (writing, saving, revising and importing) use the real UI and API; no response is mocked. A Record revision retains its prior value, invalid CSV writes zero Records, successful preflight also writes zero, and explicit confirmation creates exactly two. Protocol syntax validation and example preview are exercised without claiming wet-lab verification.

Regenerate all affected clips after a workflow or label changes. Review the videos and captions at desktop and mobile widths, ensure no loading/error frame is mistaken for completion, and compare the success instructions to the actual saved result. Keep the task tests fast by omitting `DEMO_RECORD`; delays exist only to make the recordings readable. The separate UI tests exercise playback, captions, narrow layouts, dismissible orientation and immediate-navigation document persistence.
