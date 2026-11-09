# External Agent access

Connect Codex or another MCP client to one authorized Project. Platform remains responsible for access control, strict data validation and Record revision history. These deterministic operations do not require Aira, Masterbrain or an enabled model service.

This implements [Issue #11](https://github.com/airalogy/platform/issues/11) and the research workflows in [Issue #22](https://github.com/airalogy/platform/issues/22): scoped reads, imports/revisions, immutable analysis snapshots, private external results and reviewed Protocol publication. Administrative and instrument-control access are excluded. File downloads require separate authorization.

## Enable and connect

1. A Lab Owner or Manager opens **Lab settings → External tool access policy**. Access is off by default. Enable it only if the organization's data policy permits the external tool and its model provider to process the returned data.
2. Optionally block top-level Record variable IDs, one per line. These restrictions apply across the Lab, including otherwise public Projects. Changing the policy invalidates outstanding write confirmations.
3. In **Account settings → External AI tools**, select a Project, name the grant, choose actions and an expiration of 1–90 days. The user must currently belong to that Lab and have access to that Project. The grant never expands the user's permissions.
4. Save the token when it is shown once. The server stores only its SHA-256 digest. Do not use a browser session token or legacy API key as a substitute.
5. Configure the client privately. For a same-origin deployment, the MCP endpoint is `https://your-platform.example/api/mcp`. The settings page supplies the exact command for the current instance:

```sh
codex mcp add airalogy --url https://your-platform.example/api/mcp --bearer-token-env-var AIRALOGY_PLATFORM_TOKEN
```

Set `AIRALOGY_PLATFORM_TOKEN` using your client's secure environment configuration. Do not paste the token into chat, source control or shared documents; do not place it literally in the registration command. A desktop application does not necessarily inherit variables from an already-open terminal: restart it with the configured environment. See the [Codex MCP documentation](https://developers.openai.com/codex/mcp/) for client configuration.

Revocation takes effect on subsequent calls and cancels unexecuted requests. Expiry, account credential invalidation, loss of Lab/Project membership and policy changes are checked server-side on each request. An operation already committed before revocation remains a normal Record, with its history.

## Complete an import

Ask the connected tool to:

1. Call `access_context`, then `list_protocols` and `get_protocol` to establish the target and obtain its canonical CSV header.
2. Prepare CSV using those exact `var.<id>` headers. Display titles and approximate names are not mappings. Do not invent values, fill missing scores with zero or relax the Protocol to force an import.
3. Call `preview_import` with the Protocol ID, CSV text and a unique `request_key`. The platform validates every row with the existing importer. Invalid data returns bounded row/field errors and creates **zero Records**.
4. Open the returned confirmation URL yourself. Review the destination, row count, Protocol version and complete CSV in Platform. Approve or reject while logged into the same account that created the token. **The external token cannot approve itself.**
5. Return to the tool and call `execute_operation` with only the approved operation ID. It cannot replace the input at execution time. The result contains saved Record IDs and links.

Confirmations expire 15 minutes after preview; approval does not extend that deadline. They are temporary operation requests, not Record drafts. Changing the input requires a new preview and request key. Retrying the same preview key with identical input returns the same request; different input returns `409`. Retrying a completed operation returns its existing receipt rather than importing again. Always check status after an interrupted response before preparing a new request.

## Correct a Record

`list_records` returns only the latest versions that the user may read. A deleted latest version also hides its retained earlier revisions from this list. Pass `record_id`, `protocol_id`, `expected_version`, changed variable values in `changes`, a meaningful `reason` and a fresh `request_key` to `preview_revision`. Only the original author may revise a Record, matching the existing Platform rule.

The user reviews the before/after values in Platform. After approval, execution creates a correction revision and retains the old version and reason. If another revision was saved meanwhile, execution fails; read the new version and preview again. There is no external delete operation.

## Disclosure and operation limits

- Each token is bound to exactly one Project. `protocols:read` is required. Additional scopes are listed below; existing credentials gain none automatically. Revision also requires Record read scope.
- Lab field restrictions and existing Protocol/Record permissions are checked in the API. Public visibility alone does not allow an external token to skip Lab membership or policy.
- Protocol reads expose field IDs, titles, required status, primitive types and supported validation limits. They do not expose AIMD, executable code, environment variables, model prompts or defaults/examples. CSV templates contain headers only.
- Record reads expose primitive variables by default, including supported date/time strings. Explicit `records:complex` permits bounded arrays/objects with concrete schemas (up to four levels); unsupported references, resource/file types and values are withheld. Attachments use the separate file tools. Permanent signed URLs are never returned. Unsafe string values are omitted and named in `withheld_fields`; they are not rewritten as scientific null values. Omitted fields must not be inferred.
- A Protocol containing blocked or unsupported complex variables must be imported/revised through the normal Platform UI. V1 does not partially write such a Protocol. External import does not inject the user's broad legacy API key or Protocol environment secrets into validation; validators requiring those credentials must use the normal UI.
- Each CSV is at most 1 MiB; total request body is at most 2 MiB, including streamed bodies. Existing row limits still apply. Listings use 50 items per page with `next_offset`. At most 10 pending/approved confirmations per grant and 50 active grants per user; authenticated tool activity is limited to 120 logged calls per user per minute.
- Credentials and CSV/Record payloads are excluded from external API request logs. Audit records contain actor, grant, operation identity and result references rather than input values. Validation errors expose bounded field/line locations and categories, not arbitrary custom-validator output.
- Confirmation payloads are cleared on execution, rejection and revocation, and lazily cleared when expired operations are visited. Revision summaries remain private and require current permission to view. They are not a public activity feed.

## API and MCP contract

The public reverse proxy prefixes these application paths with `/api`:

| Endpoint | Authentication | Purpose |
| --- | --- | --- |
| `GET /external-access/dashboard` | Browser `Auth-Token` | Own grants, confirmation metadata and audit |
| `GET/PUT /external-access/labs/{id}/policy` | Browser; Lab Owner/Manager | Current policy and revision-checked update |
| `POST /external-access/grants` | Browser | One-time scoped token issuance |
| `DELETE /external-access/grants/{id}` | Browser; token owner | Revoke and cancel pending writes |
| `GET /external-access/operations/{id}` | Browser; token owner | Authorized complete preview |
| `POST /external-access/operations/{id}/decision` | Browser; token owner | Confirm exact `digest` with `approve: true/false` |
| `POST /external-access/tools/{name}` | Scoped Bearer token | Deterministic tool call with JSON arguments |
| `POST /mcp` | Scoped Bearer token | Stateless Streamable HTTP MCP |

The MCP tools are `access_context`, `list_protocols`, `get_protocol`, `list_records`, `preview_import`, `preview_revision`, `operation_status`, and `execute_operation`. Client discovery supplies each input schema. Extra arguments are rejected; the execution tool accepts only an operation ID. Tool discovery does not grant any scope.

MCP uses JSON responses, accepts `application/json, text/event-stream`, validates Origin against `SITE_URL`, negotiates supported protocol versions and returns `202` for supported notifications. There are no session IDs, legacy SSE transport or unsolicited server requests; GET/DELETE return `405`. Failed tool calls use `isError: true`. Direct HTTP clients receive appropriate `401`, `403`, `404`, `409`, `413`, `422` or `429` errors. Generic executor failures ask the user to inspect the normal Platform UI rather than returning potentially sensitive exception text.

All mutations and their idempotent receipt/audit commit together. The lock order is user call gate → shared Lab policy → grant → operation → Protocol → Record; ordinary Record corrections also acquire the stable Protocol lock and may supply `expected_version`. Calls from different Lab members do not require an exclusive Lab-wide lock. No external tool can send SQL, choose arbitrary server URLs, change members/permissions or execute an instrument.

## Deployment and follow-up

The complete feature needs migrations through `0082_external_research` and its matching web/API build. Follow the normal release and backup gates; this guide is not authorization to upgrade a live instance. Existing Labs remain disabled until explicitly configured. The independent `mcp` client is a development/test dependency only; the runtime transport uses the existing FastAPI stack.

The integration suite covers real migration round trips, real CSV validation, atomic rollback, concurrent retries, Record history, permission changes, expiry, disclosure boundaries and an independent MCP SDK client. Browser coverage exercises grant creation, user confirmation and revocation in Chinese/English at phone/desktop widths. No production/customer data is needed.

Change notifications are pull-based through `snapshot_changes`; this does not schedule a rerun. Push Webhooks, dynamic OAuth registration, refresh tokens, remote job execution and automatic publication to shared Knowledge are not provided. These are separate extensions, not prerequisites for the analysis and Protocol workflows below.

## External analysis and returned results

Open **Project → More → Connect external AI**, or Account settings → External AI tools. The destination and available actions are shown before creating credentials. Test the connection while the one-time token is visible.

| Additional scope | Capability and required authority |
| --- | --- |
| `records:export` | Freeze/export data; also requires `records:read` and the existing Project export authority (Lab Owner or Project Owner/Manager). Read permission alone is insufficient. |
| `analysis:write` / `analysis:read` | Propose/read own external results; source export and current source-read rights still required. |
| `protocols:source` | Exact source archive, separate from field/schema reads. Source may itself contain confidential research text. |
| `protocols:candidate` / `protocols:publish` | Validate/propose / publish after web confirmation; require source scope and ordinary create/update Protocol authority. |
| `records:complex` | Explicitly scoped bounded structured values; no implicit access to file contents. |
| `knowledge:read`, `documents:read`, `materials:read` | Project context only; personal, other-Project and Restricted content retain normal access checks. |
| `files:read` | Explicit checksum-pinned attachments. Requires parent capability and access; Record files also require export authority. |

1. Inspect context and Protocol dictionaries. Call `create_snapshot` with a fresh `request_key` and `sources: [{protocol_id, fields, records?}]`. Optional records are exact `{id, version}` pairs; omission selects current readable revisions at capture. Each snapshot supports up to 16 Protocols, 100 selected fields each, 2,000 Records total and 16 MiB. Paging returns 50 rows of **the same** snapshot, including Protocol/schema versions, missing/unsupported/withheld status and its digest. Unconfirmed snapshots expire in 24 hours. At most 20 active snapshots per user.
2. Compute in the external tool. Sources remain separate; explicitly choose join keys, units and cardinality when combining Protocols. Fetch any separately authorized context with `list_context_assets` / `read_context_asset`; supply its digest on later text pages. `list_record_files` and `read_research_file` first return metadata, then chunks pinned by `expected_sha256`. Maximum attachment: 16 MiB; chunk: 256 KiB. No arbitrary URL fetch or secret-bearing environment is exposed.
3. Call `preview_analysis` with snapshot ID/digest, title, question, report, method, parameters, environment, executor, limitations, `execution: computed | interpretation_only`, a fresh request key, and optional files `{filename, kind, content_base64, sha256}`. Return at most 20 files totaling 1 MiB, with `.py`, `.json`, `.csv`, `.txt`, `.md`, `.png` or `.jpg/.jpeg` extensions. Code is stored, never executed by this endpoint. Add `rerun_of_id` to connect a new run to an existing result.
4. The user reviews the full report, provenance, limitations and downloadable files in Platform and confirms the exact proposal. `execute_operation` creates a normal private `AnalysisRun`, a versioned `AnalysisPipeline` method and file references atomically. It preserves the original run on rerun; an unchanged method reuses its revision, a changed method creates the next revision. Lost responses can be retried without duplicates.
5. Open the result through the returned URL. Its source digest, file checksums, environment and rerun lineage are retained. External computation is labeled **not reproduced by Platform**; absence of code/environment is explicitly marked incomplete. It is private to the submitting user, including in public Projects. Revoked source access prevents later reads/downloads. Context fetched separately is not automatically included in the Record snapshot: preserve relevant source identities/digests in the returned method/report. Promotion to shared Knowledge is deliberately blocked until an explicit source-aware publication flow is available.

Confirmed snapshots remain attached to their result; expiry does not erase an accepted research asset. Token revocation prevents further delegated access but does not delete the user's own accepted result. Lab policy changes require a new snapshot for further delegated analysis. `snapshot_changes` reports later Record revisions/additions without modifying the snapshot or starting work; deleted or inaccessible sources fail closed.

## Local Protocol development

Call `download_protocol_source` with `{protocol_id, version, format: "aira" | "zip"}`. The archive is built from that immutable published version, not the running executor directory. Source retrieval does not authorize publication.

Use the official Airalogy Python syntax/Assigner checks and the bundled local preview below. Then call `preview_protocol_candidate` with a fresh request key, `files` (relative UTF-8 text paths) and optional `binary_files` (base64 image/PDF assets), or `archive_base64` for a `.aira`/ZIP package. Limits: 50 files, 1 MB uncompressed; hidden paths, symlinks, duplicate/unsafe archive paths and disguised image files are rejected. Existing Protocols require both `protocol_id` and the exact `base_version_id`; new Protocols omit both.

Platform runs official static validation and its isolated executor with no delegated user API key or Protocol environment secrets. The owner sees the source diff, binary checksums/downloads, destination, proposed version and schema compatibility report. Confirmation and execution recheck the source digest, permissions and base version. A concurrent publication returns a conflict requiring a new preview. Publication creates a new normal Protocol version; existing Records keep their original Protocol version. External tools cannot approve or publish unreviewed input.

## Local client and preview

From a Platform source checkout, the stdlib Python client can be imported as `from tools.airalogy_agent import Client` or run directly. Python 3.11+ is required; `check` and `candidate` additionally use the installed official `airalogy` package. For a matching version, use the API environment (`uv run` from `apps/api`). It never executes Protocol Python during local static checking.

```sh
python3 tools/airalogy_agent.py --instance https://your-platform.example context
python3 tools/airalogy_agent.py --instance https://your-platform.example snapshot selection.json snapshot.json
python3 tools/airalogy_agent.py check ./my-protocol
python3 tools/airalogy_agent.py --instance https://your-platform.example candidate ./my-protocol --protocol-id UUID --base-version-id UUID
python3 tools/airalogy_agent.py --instance https://your-platform.example status OPERATION_UUID
# After the user confirms in Platform:
python3 tools/airalogy_agent.py --instance https://your-platform.example execute OPERATION_UUID
pnpm agent:preview:build
pnpm agent:preview
```

Use `--help` for exact command arguments. `call TOOL request.json` exposes the same typed HTTP tools as MCP. Credentials come from `AIRALOGY_PLATFORM_TOKEN` or a private `AIRALOGY_PLATFORM_TOKEN_FILE`, never command-line token arguments. HTTPS is required except loopback development, redirects are refused, downloads verify checksums and never overwrite existing local files.

Preview opens at `http://127.0.0.1:3109/agent-preview.html` and uses official `AimdEditor`, `AimdRecorder` and example-data generation. It edits/downloads local AIMD and tests inline fields without uploading or creating Records. Python models/server Assigners still require server validation. The preview server binds loopback, disables directory browsing and external connections; do not expose it publicly.

## Browser authorization (OAuth + PKCE)

Account settings supports registering a public client name and exact callback URI. Callbacks require HTTPS or a literal loopback HTTP address, with no credentials, query or fragment. Registration returns a client ID, not a client secret. In a controlled local terminal:

```sh
python3 tools/airalogy_agent.py --instance https://your-platform.example login --client-id CLIENT_UUID --scopes 'protocols:read records:read records:export analysis:read analysis:write' --token-file /private/path/platform-token.json
```

Register `http://127.0.0.1:8765/callback` for this default CLI callback. The browser shows the client, instance, requested actions, Project, 1–7 day expiry and explicit consent. S256 PKCE, state validation, exact callback/resource binding, five-minute single-use authorization codes and audience-bound tokens are enforced. Credential files are created exclusively with owner-only permissions; expired, foreign-owned or broadly readable files are refused. Revoking a client revokes its associated grants and outstanding operations. No automatic refresh or dynamic registration is offered; clients without pre-registration support should use scoped bearer credentials.

Discovery lives at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource/api/mcp`. Proxies must forward these paths to the API in addition to `/api/*`; the supplied Caddy configuration and development proxy do so. `SITE_URL` must match the public instance origin. Tokens minted for `/api/mcp` cannot be used at `/api/external-access`, and vice versa. The HTTP and MCP workflows share validation, authorization, confirmation, audit and idempotency logic; actual compatibility with a particular desktop application's OAuth onboarding depends on that client's pre-registration support.
