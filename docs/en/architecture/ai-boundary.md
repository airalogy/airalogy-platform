# Platform and Masterbrain AI boundary

Platform uses the same-repository `packages/masterbrain` Python module for built-in model calls, including text embeddings. It does not require a separate AI service in the default package mode. This unifies model access, not ownership of the research system.

See [same-repository AI development](../masterbrain-development.md) for the shared build, tests and migration boundary. | Layer | Owns | | --- | --- | | Masterbrain | Reusable AI capabilities, provider clients, model request/response validation and per-call usage events. | | Platform | Identity, authorization, trusted context selection, operational budgets, approvals, durable assets, audit and execution state. | | Instrument Gateway / Compute Runner | Explicitly authorized execution and independent result/stop observations. |

Prompts and context assembly that depend on Platform objects remain in Platform. A model response cannot grant access, approve itself, write a final asset or authorize an instrument operation. Built-in provider SDK imports in API product code are guarded by an offline regression test; integration goes through `app/libs/masterbrain.py`. Protocol executor code supplied by users is a separate execution boundary, not a built-in model capability.

## Organization model services

In organization settings, open **Organization AI** and add a model service. Enter its name, API type, base URL, provider key and the upstream model IDs, one per line. DashScope and OpenAI can be configured together. For an internal OpenAI-compatible gateway, the deployment operator can add its exact API root to `ORGANIZATION_AI_ALLOWED_BASE_URLS` and restart the API. Test a model to send a short synthetic chat request. Save the service and select the default for new conversations.

Members can choose a configured model below the Aira message box. This affects subsequent messages in that conversation. Services without a key are unavailable. Previous organization settings remain active and the first catalog save preserves the existing credential. Changing a credential’s service address requires a new key.

## Conversational Record filling

Open Aira from the top bar of an editable Record. On desktop the form and conversation appear side by side. On a phone, close the panel to return to the draft. In the form or Fields panel, select Add to chat beside a variable to reference it, then enter its observed value. Use the same conversation to ask about the Protocol or request a draft update. Attach observations with the plus button or dictate and review the text before sending. If the target or value is unclear, Aira asks for clarification. Aira can resolve references such as “the second field”. Review replacements of existing values or undo the last fill. Ask explicitly for simulated data to see an isolated preview. Exit the preview to return to the original draft. File and resource references and calculated fields require their normal input paths.

The embedded package and external Masterbrain service must support the 0.14.0 Field Input turn API. An external service must also support attachment observations to fill from uploaded files.

Analyze this report opens Aira with the displayed Record revision and Protocol version. Reopening the action resumes the analysis. Ask about this Protocol waits for a question. Assist with revision opens the conversation with the diff review. Organize minutes uses the current notes and lets the editor review the proposal before returning it to the meeting and saving.

## Protocol authoring and client calculations

Platform opts in to `prefer_client_assigners=true` for single-file Protocol generation and code editing. Masterbrain prefers small deterministic calculations in `protocol.aimd` client Assigner blocks, while external services, privileged operations and heavy computation remain server-side Python. Existing runtime choices are preserved when editing; generated code still requires validation and user review.

Platform owns the restricted browser runtime, dependency scheduling and input/output validation. CSV/API imports must supply derived values; they do not execute browser calculations. Client calculations are available without AI and do not bypass server-side Record validation or permissions.

This preference requires Masterbrain 0.13.0 or newer in external mode. Updating Platform's Python dependency does not upgrade a separately deployed Masterbrain service; older services retain their prior generation behavior. No new database migration or embedding reindex is required for this dependency upgrade.

## Embeddings and non-AI search

- The index contract remains Qwen `text-embedding-v4`, 1024 dimensions, at most six texts per call. Changing only a model setting would mix incompatible vector spaces; a model change requires an explicit reindex migration.
- Protocol and discussion indexing, public Hub retrieval and chat retrieval now use the same Masterbrain embedding endpoint. Requests carry server-derived usage context; interactive callers supply the authorized user and Lab/Project, while internal Hub retrieval identifies an internal service rather than inventing a user.
- `AI_ENABLED=false` prevents embedding model requests. A GPT-only configuration does not silently substitute an OpenAI embedding model. Missing Qwen capability, model failure or invalid embedding responses leave the local keyword path available.
- Keyword-only chunks store a nullable vector, never a zero vector or fabricated similarity score. Existing vectors remain intact during the schema upgrade. Keyword-only rows also remain searchable after AI recovers.
- Resource index replacement commits deletion and insertion together. Public recommendations exclude private Projects, protocol-level permission Projects, and deleted Projects/Protocols; scoped discussion retrieval retains its Protocol boundary. Retrieval does not grant access to the source asset.
- Model calls do not log raw research text or provider error bodies. Provider-reported tokens are metered; an unavailable price remains unknown rather than being reported as free. Cancelled calls remain cancelled.

This fallback covers the Protocol/discussion embedding index. Knowledge, Record and other deterministic search interfaces retain their existing implementations; the change does not add an AI requirement to them.

## Deployment and migration

Install the locked production dependency and run the normal database migration before starting the upgraded API. Revision `0058_optional_embeddings` makes only the embedding column nullable; it does not delete text or rewrite existing vectors.

External mode (`MASTERBRAIN_CALL_MODE=external`) needs a compatible Masterbrain service with `POST /api/endpoints/embeddings` (available in 0.12.0), private transport/access controls, the matching Qwen provider configuration and its own usage sink integration. An older service without this endpoint degrades to keyword search; Platform never bypasses it with a direct provider call. External mode is not a shared database or a fallback to another provider.

There is no automatic bulk vector backfill when AI is re-enabled. Existing keyword-only chunks stay searchable; subsequent supported resource indexing can generate vectors. A deployment needing complete semantic coverage should separately plan a scoped, metered reindex. Do not change model/dimensions or claim backfill has completed merely by restarting the API.

Downgrading the migration refuses to set `NOT NULL` while keyword-only rows exist. Restore a verified pre-upgrade backup, or complete and verify a deliberate compatible reindex before downgrade; never delete rows or fabricate vectors just to satisfy the old schema. Follow the normal backup/restore procedure for any rollback.

## Verification

Offline API tests cover the published package endpoint, batching, disabled AI, transport failures, cancellation, malformed vectors, model/dimension consistency and usage attribution. Isolated PostgreSQL tests cover migration upgrade/downgrade, concurrent atomic replacement, punctuation-safe keyword queries, AI recovery and public/private/deleted scope isolation. They use synthetic model responses and do not claim live provider quality or availability.
