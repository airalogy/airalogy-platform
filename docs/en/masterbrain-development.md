# Same-repository Masterbrain development

Platform owns the maintained Masterbrain source. Model adapters, research workflows, business tools and UI can be changed and verified together without first publishing another Python or npm package.

| Directory | Responsibility |
| --- | --- |
| `packages/masterbrain` | Python AI core, prompts, service endpoints and tests |
| `packages/masterbrain-client` | TypeScript client and generated code-edit contract |
| `packages/masterbrain-vue` | Vue composables and change-review UI |
| `apps/api`, `apps/web` | Platform identity, authorization, business execution, durable data and Aira UI |

Platform validates and authorizes model proposals before executing business operations. Studio is no longer actively maintained and remains a historical snapshot in the original Masterbrain repository; its frontend, launchers, native packaging and local workspace/library endpoints are not included in Platform. See [AI boundaries](architecture/ai-boundary.md).

## Development

From the repository root:

```sh
corepack pnpm install --frozen-lockfile
uv --directory apps/api sync --locked
corepack pnpm masterbrain:build
corepack pnpm masterbrain:test
```

The API's `tool.uv.sources` installs `../../packages/masterbrain` editable for development. Frontend consumers use `workspace:*`. Use `pnpm api:dev` to watch both API and AI Python sources. Rebuild client/Vue packages with `pnpm masterbrain:build` after frontend AI source changes. No package publication is required. `apps/api/uv.lock` is the shared Python runtime lock. Keep lockfiles updated when dependencies change.

Use `pnpm masterbrain:contract:generate` after changing the shared Python models, and commit the generated schema. `masterbrain:contract:check` verifies consistency. The default Python tests exclude live provider tests (`openai`, `qwen`, `e2e`, `integration`) and block network access for unmarked tests; passing offline tests is not evidence of provider availability.

## Production and compatibility

Build the API from the repository root with `docker build -f apps/api/Dockerfile -t platform-api-local .`. Its locked, non-editable installation builds the local Python source into a wheel inside the image. No development directory or sibling repository is needed at runtime. The Web image builds the local client and Vue packages first.

Platform `VERSION` and its exact Git SHA identify delivery. Migrated packages retain compatibility metadata, without requiring separate version bumps for everyday development. Internal npm packages are private and the Python module is marked against public upload. Previous published packages remain intact; the old repository's independent publishing workflows are not imported.

The optional `MASTERBRAIN_CALL_MODE=external` path remains compatible. Such installations still need a compatible remote service; a Platform update does not upgrade that separate process. The default package mode updates with the Platform image.

This source migration makes no database changes and does not rewrite chats, Protocols or Records. Commit, deployment and repository archival remain separate operations, subject to the existing deployment checks and recovery requirements.

## Provenance

The source baseline is `airalogy/masterbrain` commit `fda4d56` plus the existing grounded field-input repair. `packages/masterbrain/migration-source.json` records the exact commit, initial hashes and path mapping. Subsequent edits belong to Platform history. Original documentation and changelogs in `packages/masterbrain/history` are historical references, not current publishing instructions. The Apache-2.0 license is preserved.

All new AI development belongs here. Archive the original Masterbrain repository after the migration has been committed, verified and documented there, and stop its independent releases. Studio remains available as historical source without active development or synchronization from Platform. Preserve existing commits, tags and published packages. Importing the source does not update any running company instance.
