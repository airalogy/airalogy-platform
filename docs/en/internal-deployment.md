# Internal application deployment

Frequent internal deployments can share a development version such as `0.5.0-beta.1`. Identify each by its full committed SHA, immutable image IDs and source/image archive hashes. Image tags include the full version and SHA; never overwrite them. This path does not push release tags or create GitHub Releases. Public product publication retains the [formal release gates](./release-and-deployment-identity.md).

The initial fast path supports healthy, existing, same-schema installations. Build API and Web for the target architecture; retain the existing database, Redis and object storage. Reuse the executor only when its labeled source commit is available and its Dockerfile, dependencies and mounted execution code match exactly. API and Web are rebuilt so diagnostics identify the candidate. Changed migrations, database images, storage or base Compose definitions block this path and require a separate source-to-target migration/recovery plan.

From the clean candidate checkout:

```bash
python3 deploy/internal/platform-internal.py prepare \
  --base <full-deployed-SHA> --platform linux/amd64 \
  --web-origin https://workspace.example.org \
  --output /private/ops/candidate \
  --reuse-executor <verified-executor-image>
```

Omit executor reuse to rebuild it. The tool exports only selected images and committed API/deployment source, and binds their bytes in a private manifest. It neither publishes nor connects to production. Store credentials, instance configuration and evidence under persistent ignored `.private/ops/<instance>/`, outside build contexts. Investigate failed builds before retrying with a new output directory; existing image identities cannot be overwritten.

Review the actual deployed-to-candidate diff and run applicable version/lock, unit/type, permission and browser checks. The delivery tool tests are `python3 -m unittest discover -s tests/deployment`. Reuse successful results for the same exact candidate; changing the commit invalidates receipts. Record real reviewed commands:

For local source checks, use the shared runner, for example `node scripts/pre-push.mjs --check types` and `node scripts/pre-push.mjs --check api-tests`. The runner and pre-push reuse the most recent successful result for at most 24 hours, only for the same clean commit, working directory, command, environment, tool binaries and installed dependency metadata. Logs are bound by SHA256 under ignored `.cache/local-checks/`; environment values and credentials are not written to receipts. Dirty/untracked source, changed configuration, a failed/interrupted retry, missing or altered logs, or expired evidence require a real run. Use `--fresh` to force one. Commands run directly outside this runner do not produce reusable receipts.

This cache is local feedback, not release certification or a cache of build artifacts. CI, live image availability, real database integration, browser/artifact acceptance and recovery checks are never reused through it. No cache is used when `CI`, `GITHUB_ACTIONS` or `RESOURCE_TEST_DATABASE_URL` is set. Internal artifact/migration/recovery receipts below remain separate requirements.

Hosted checks run for affected pull requests and pushes to `main`, with manual dispatch retained. Development-branch pushes no longer launch a duplicate copy of the PR suite. A merged main revision is still independently checked; unchanged job names and formal release gates remain in place. Superseded research/network validation runs are cancelled, while release publication is not. Internal deployments do not wait for all hosted workflows; public releases still require the exact-commit source CI evidence defined in `scripts/release-ci.mjs`.

```bash
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name source -- bash /private/ops/check-source.sh
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name artifact-acceptance -- bash /private/ops/check-artifacts.sh
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name recovery -- bash /private/ops/check-recovery.sh
python3 deploy/internal/platform-internal.py ready --bundle /private/ops/candidate
```

Source checks must use the exact clean checkout. Artifact acceptance loads the exact archived images and checks affected authenticated save/reload and permission flows with isolated synthetic data. Recovery checks establish an applicable recovery point, database restoration, file/Protocol integrity, old-application compatibility and treatment of new writes. A health probe alone is not acceptance. Missing, failed, mismatched or older-than-24-hour receipts block readiness; a failed retry replaces prior success.

Readiness does not perform cutover. A private instance adapter rechecks deployed SHA, configuration, schema and supporting images for drift; verifies transferred artifacts and mounted source; obtains a final consistent recovery point; preserves old configuration/images; and replaces only application services by exact image IDs with no build/pull. It must not replace infrastructure or restore over production data automatically. For compatible same-schema failures, restore the previous application and preserve new writes. Verify identity, health, existing data and affected user tasks after cutover, then retain the private receipt.

Keep recoverable source, artifacts and configuration in an independent encrypted backup. The tool does not replace a backup system. Public release notes and complete distributable packages are prepared at a later external release milestone.

## Additive schema delivery

For a reviewed additive schema upgrade, pass `--migration-plan /private/ops/migration-plan.json` to `prepare`. This is a separate migration lane, not a relaxation of the same-schema path. The private JSON identifies exact `base_commit` and `target_commit`, `source_revision` and `target_revision`, the complete `changed_paths`, and concrete `backup_plan`, `migration_validation`, `rollback_policy` and `write_impact`. Only newly added migration files and model registration changes are supported; edits to prior migrations or infrastructure still require another procedure.

The plan is embedded in the immutable candidate manifest and requires an additional exact-artifact `check --name migration` receipt. Restore the source database independently, verify its revision and existing data, run the target migration using the candidate image/source, and compare data and permission behavior. Readiness rejects missing migration evidence. Recovery must consider application-level permissions as well as SQL compatibility: a pre-meeting application cannot safely serve a database after restricted meetings have been created. Never automatically downgrade populated meeting tables or restore over writes after cutover.
