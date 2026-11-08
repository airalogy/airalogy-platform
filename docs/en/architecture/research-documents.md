# Research document contract

`ResearchDocument` composes one-to-one with `ResearchLogEntry`. The latter remains the sole owner of scope, title, AIMD body, occurrence time and revision identity. Existing plain Log entries have no document metadata and keep their old behavior. Document writes require the document API so an old Log edit cannot discard structured state.

`ResearchDocumentSubmission` is a separate immutable evidence object. It seals the exact source revision, body, server-derived schema, values, file manifests and source identity. Existing `Record.protocol_id` and `ProtocolVersion` constraints are unchanged. A document submission cannot masquerade as a Protocol Record or automatically enter its analysis. Future adapters must select an explicit definition and perform validated conversion.

The official Python SDK parses AIMD. A bounded adapter converts its declarations to Pydantic/JSON Schema without compiling or executing generated Python. The initial supported types and constraints are explicit; unknown executable/custom contracts fail submission but remain saveable prose. The official WYSIWYG Recorder surface edits prose and values without installing runtime assigners or collectors.

Writes compare the expected revision under a row lock. Definition-changing edits, restoration, submission and derivation bind confirmation to an exact digest. Submitted evidence and derivation receipts have database-level mutation guards. Copying starts a new identity with empty measured state. Revisions restore into a new revision.

`ResearchMaterial` stores archive source metadata on an existing `ResearchFile`, retaining shared quotas, authorization, blob deduplication, short-lived access tokens and audits. Deduplication never supplies permissions. Upload request identities survive retries, including full-quota retries. Portable archives contain current content and original attachment bytes, not authentication, scope grants or approval authority. Restore creates new logical files in the confirmed scope in one transaction; rollback removes only the operation's uncommitted storage objects.

Migration `0079_research_documents` is additive after `0078_external_agent_access`. Empty downgrade is supported; populated downgrade deliberately fails to avoid data loss. No existing Log/Knowledge/Record bodies are rewritten. Use a suitable backup and rehearse the source-to-target migration before any production upgrade.

Remaining RFC work includes OCR and source regions, richer collaboration, organization-wide method selection, inline publication into the Protocol editor, and explicit downstream analysis of document submissions. These are not implied by the initial archive or method-package workflows.

## Template contract

Migration `0080_document_templates` adds independent `DocumentTemplate` and `DocumentTemplateRevision` tables after `0079`. Built-in, bilingual templates are versioned source constants; custom templates have immutable ownership scope, a checked current revision, revision snapshots and reversible archival. Initial scopes reuse `log.read` / `log.write`; only the author or scope manager may manage an existing template. Public Project visibility never supplies template access.

Creation and updates bind explicit confirmation to the actor, exact content, destination, source revision and current template revision. A per-author lock and retained creation UUID make retries idempotent; a reused key with different content is rejected. Cross-scope publication copies into a new template with private provenance instead of moving the original. Template payloads never disclose a private source document identity.

Template models cannot accept Record values, file grants or submission authority. The SDK parses the AIMD definition, a non-executing adapter validates it, and JSON Schema checks all explicitly declared defaults. Using a template rechecks source read and destination write access and records the exact template revision/content digest on an independent working document. Only explicit parameter defaults initialize its field values. Unfilled results remain empty. Updates, revocation or archival do not rewrite documents already created.

Saving from a document requires explicit prose review: prose may itself contain observations or private links, so removing Record data is not a content redaction guarantee. Attachments are never implicitly copied or authorized. Empty downgrade is supported; populated downgrade fails to protect user templates.

## Browsing contract

Document lists and monthly calendar counts reuse the same scope-authorized query and `ResearchLogEntry.occurred_at`; no separate diary copy or date column is introduced. Inclusive local calendar dates are converted to a half-open UTC interval using the supplied IANA timezone, with separate local-midnight boundaries for DST. Record-date and update-date ordering both use document ID as a stable tie-breaker. Monthly counts include only unarchived documents readable within the exact requested scope and matching search/type; public Project visibility supplies no additional access.

Reading uses the normal document/file authorization paths and a readonly SDK surface. The UI retains allowlisted browsing filters across pagination and editor navigation, fetches adjacent pages on demand, and rejects late responses after a scope/filter change. Missing or changed results never silently broaden filters. Editing a record date uses the existing revision-checked document save, so Research Log and document views stay consistent without migration or duplicate events.
