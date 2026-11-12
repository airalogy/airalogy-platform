# Protocol ratings and adoption

Protocol Rating supplements Star with version-specific use feedback and a transparent recommendation. It does not certify scientific quality, physical execution, independent replication, or a success rate. Ratings do not require AI.

## Use the feature

Open **Ratings & use** in a Protocol, or the rating link on a Project list/Hub card. Select an exact version and **My accessible scope** or **Public sharing only**. Each summary is recomputed from currently accessible evidence; totals can differ between viewers. Original-version execution counts and derived adoption remain separate.

After saving a Record, **Optional: rate this use** opens the same panel. It is not a required step or a blocking dialog. Select your own Records from one execution together, select its outcome, and confirm whether it was actual use. A sample batch with several Records counts once. Leaving the actual-use box unchecked records test feedback without recommendation credit. An unknown outcome is also excluded until corrected. Stopped work is not a negative rating or scientific failure.

Existing `ResearchProtocolRun` identities are reused when linked Records identify a completed action. Otherwise the server records a minimal, audited use receipt for the user-declared group. Receipts do not schedule or execute experiments. Existing runs do not distinguish actual work from simulation reliably, so this release requires explicit actual-use confirmation for both paths. Old imports, revisions, previews and unclassified Records never become uses automatically. A receipt is evidence of a declaration plus saved Records, not verification of a physical experiment.

**Rate this version** maintains one overall 1–5 rating per user and version. Linking an eligible use makes it a use review; reading opinions and the creator's or linked author's/maintainer's self-assessment appear separately and do not enter the use average. Feedback on a direct fork can reference the source version as an adapted use. It does not claim that the source was executed unchanged. Conditions and adaptations should be described in the review.

Edit or withdraw your feedback under **My use feedback and corrections** and **My rating revision history**. A Record remains bound to its original receipt even after withdrawal, preventing repeated withdrawal/recreation from inflating adoption. Corrections preserve revisions; concurrent stale edits receive a conflict. The Protocol author cannot delete another user's rating.

## Trial policy: `protocol-rating-v1-trial`

This is an explicit product heuristic, calibrated against synthetic boundary examples, not a scientifically validated weighting scheme. Real authorized pilot feedback is still needed for calibration. Do not treat an 86 from one discipline as objectively better than an 82 from another.

For eligible, distinct non-author reviewers:

1. Display the unweighted raw average and five-bin distribution separately.
2. Let each Lab's effective reviewer weight be `min(n, 5)`. Multiply its mean score by that weight, sum across Labs, and combine with three neutral prior ratings: `posterior = (weighted_sum + 9) / (effective_reviewers + 3)`.
3. Let `q = (posterior - 1) / 4`. Rating contribution is `90q`.
4. Let `u = min(sum(min(real_uses_in_lab, 3)), 20)` and `r = min(distinct_cross_lab_adopters, 5)`.
5. Adoption contribution is `10q × (log(1+u)/log(21) + log(1+r)/log(6)) / 2`.
6. Round the sum to one decimal. Show no numeric recommendation until at least **3 distinct eligible users** have rated. A single-Lab deployment can meet this threshold; Lab diversity is explanatory, not a requirement.

Popularity can add at most 10 points and is attenuated by feedback quality. Coverage is not another additive bonus: this avoids counting correlated popularity signals repeatedly. Experts receive no multiplier. Missing ratings do not become zero or five; unclassified Record counts are displayed alongside the confirmed-use count. Latest/updated discovery is retained. Project lists can sort their authorized selection by confirmed uses or effective reuse, before pagination. There is no global composite ranking across disciplines.

A visible empty copy contributes to the raw copy count, not effective reuse. Effective reuse requires an eligible receipt on a direct derived Protocol, an adopting Lab different from the source Lab, and a creator different from the source creator. Repeated copies by the same creator within the same Lab count as one effective adoption. Several creators in one Lab can produce separate raw adoptions, but the score's reuse component counts that Lab only once. Recursion through a lineage tree is deliberately excluded to avoid double attribution. Lab IDs identify platform scopes, not verified independent organizations.

**How this is calculated** exposes the policy, components, distribution, scope and calculation time. **Download calculation basis** saves a JSON snapshot with anonymous score histograms and counters sufficient to reproduce that calculation, without review text, reviewer IDs or Record links. Current summaries are computed synchronously; a failed read shows an error instead of a stale cached private score. Revision audit events retain the algorithm policy used at the time of the write. Reopening a historical Protocol version computes its current eligible evidence under the explicitly displayed algorithm; it does not pretend to reproduce a past recommendation. Retain the exported basis when citing a historical score.

## Privacy and authorization

Feedback is private to its authorized source scope by default, including on a public Protocol. Public sharing is opt-in separately for use feedback and overall rating. It requires publicly readable source Protocols and Records; an internal review does not become public merely because its source becomes public or is copied. Public review sharing includes the user's display identity and submitted text. Source Record contents and links are not included in public reviews. Private installations send no telemetry to a Hub.

Every read rechecks current permissions, active receipts, source deletion and exact versions. Public summaries exclude private adoption, even in their counts. Source permission changes, withdrawal and deletion remove affected contributions on subsequent reads. A user who can only read their own Records does not gain others' receipt statistics. `scope=public` uses anonymous source permissions regardless of the caller. Overall ratings can be withdrawn even if their formerly linked evidence is no longer eligible.

No expert badge, self-declared verified identity, or unexecuted technical check is advertised. Formal expert governance, domain-specific evaluation, cross-instance opt-in aggregation and real-data policy calibration remain the follow-up items of Issue #23.

## API and verification

- `GET /protocol-ratings/{protocol_id}?version=...&scope=accessible|public`: live version summary.
- `GET/PUT /protocol-ratings/{protocol_id}/mine?version=...`: author-specific overall rating and history. PUT includes `expected_revision`; identical retries do not add votes or revisions.
- `GET /protocol-ratings/{protocol_id}/records?version=...&page=...`: own, latest valid Record identities for grouping.
- `POST /protocol-ratings/{protocol_id}/uses?version=...`: confirmed grouping and optional feedback. Includes a request key, immutable Record identities, actual/test declaration and visibility.
- `PUT /protocol-ratings/{protocol_id}/uses/{use_id}?version=...`: author-only correction/withdrawal with `expected_revision`.
- `GET /protocol-ratings/{protocol_id}/uses/{use_id}/history?version=...`: author-only execution feedback audit history.

Migration `0083_protocol_rating` follows `0082_external_research`. It creates separate feedback tables and does not backfill or alter research data. Local verification includes score bounds/diminishing returns, concurrent requests, version separation, private/public/revoked sources, derived adoption, real research identities, migration rollback in an isolated transaction, and bilingual desktop/mobile browser workflows. The real PostgreSQL suite is part of `pnpm research:integration` and the affected extended pre-push plan.

Explicit Lab hard-deletion cleans its own feedback and audit rows in the same transaction. If ratings in another scope still reference its use evidence, deletion is blocked rather than silently deleting foreign lineage. Normal soft deletion simply removes affected current contributions.
