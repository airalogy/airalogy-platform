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

```bash
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name source -- bash /private/ops/check-source.sh
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name artifact-acceptance -- bash /private/ops/check-artifacts.sh
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name recovery -- bash /private/ops/check-recovery.sh
python3 deploy/internal/platform-internal.py ready --bundle /private/ops/candidate
```

Source checks must use the exact clean checkout. Artifact acceptance loads the exact archived images and checks affected authenticated save/reload and permission flows with isolated synthetic data. Recovery checks establish an applicable recovery point, database restoration, file/Protocol integrity, old-application compatibility and treatment of new writes. A health probe alone is not acceptance. Missing, failed, mismatched or older-than-24-hour receipts block readiness; a failed retry replaces prior success.

Readiness does not perform cutover. A private instance adapter rechecks deployed SHA, configuration, schema and supporting images for drift; verifies transferred artifacts and mounted source; obtains a final consistent recovery point; preserves old configuration/images; and replaces only application services by exact image IDs with no build/pull. It must not replace infrastructure or restore over production data automatically. For compatible same-schema failures, restore the previous application and preserve new writes. Verify identity, health, existing data and affected user tasks after cutover, then retain the private receipt.

Keep recoverable source, artifacts and configuration in an independent encrypted backup. The tool does not replace a backup system. Public release notes and complete distributable packages are prepared at a later external release milestone.
