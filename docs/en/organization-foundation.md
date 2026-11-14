# Organizations and single-organization workspaces

An Airalogy Platform organization can represent a company, research institution, or independent laboratory. It owns membership, projects and policy boundaries. Projects remain the daily work entry point; optional organizational units do not introduce a mandatory department/laboratory navigation hierarchy. Organization type does not restrict Protocols, documents, knowledge or scenario kits.

This is the compatibility foundation for Issue #25. Issue #26 covers the subsequent R&D workbench. Neither BD nor an identity server is required.

## New company installation

Reuse the single-instance services, deployment and recovery tooling. The `deploy/single-lab` directory remains stable for existing operators:

```sh
bash deploy/single-lab/scripts/generate-env.sh \
  --organization-name 'Example R&D' \
  --organization-uid example_rd \
  --organization-type company \
  --site-url https://research.example.org \
  --tls-email admin@example.org
```

Follow the [single-instance deployment guide](./single-lab-deployment.md) for network preflight, backups and startup. This generates `DEPLOYMENT_MODE=single_organization`. `/setup` accepts the organization name and type and creates the first administrator; upload the logo in **Organization management → Settings**.

The name is editable display text. The organization identifier (UID, such as `example_rd`) comes from `SINGLE_ORGANIZATION_UID`, defaulting to `main`. Setup shows this identifier read-only for confirmation and checks the submitted value against current configuration. A mismatch rejects setup without creating accounts or organizations. To change the identifier, update configuration and restart before initial setup. After creation it remains read-only because links and Protocol identifiers use it. The internal database UUID is generated automatically. Setup does not edit deployment configuration or rename an existing UID.

Users land on recent projects and personal work without selecting the only organization. Setup accepts an optional name for the first private project; a blank field uses “通用项目” in Chinese or “General” in English. The name is saved in the creation language and can be edited later; switching UI language does not rename projects. The identifier remains `workspace` (`lab_protocols` for legacy single-lab mode). Existing names, identifiers, permissions and links remain unchanged. The bootstrap API accepts optional `project_name`, trimming surrounding whitespace and retaining the usual 3–64-character constraint for nonblank names. The UI submits the chosen name or localized default. Older clients that omit the field still use the configured deployment name; new deployment configuration defaults to `General`. New company invitations default to Contributor; administrators can choose a different role before confirming. Existing `single_lab` installations keep Recorder defaults. No existing memberships or issued invitations change.

Personal documents stay private, and organization type does not expand Restricted access. Existing API permissions control membership, projects and settings. Companies/institutions use organization terminology; laboratories retain laboratory terminology. All core paths work with AI disabled.

## Browser addresses

- Single-organization deployments (`single_organization` and legacy `single_lab`) use `/projects/{projectUid}/overview`. Protocols, Records, the editor and other project pages share this short prefix. Organization management uses `/organization/members`, `/organization/settings` and related paths.
- Multi-organization deployments (`community`) use `/orgs/{organizationUid}/projects/{projectUid}/overview` and `/orgs/{organizationUid}/members`. Having only one visible organization does not change the URL scheme.
- Legacy `/labs/{uid}/...` links redirect with replacement, preserving queries and fragments. Login return URLs use canonical paths. Legacy organization-list entries lead to the project dashboard in single-instance mode.
- A foreign organization's link on a single instance shows organization-not-found instead of opening a same-named local project. The implicit organization comes only from the `/instance` deployment contract; API authorization remains unchanged.
- A central frontend routing adapter retains the internal `labUid` context for existing pages. Backend sharing, analysis results, Records and work-item evidence use a common browser-path builder. Database identities, project UIDs and published Protocol identifiers do not change.

## Existing installations

Back up and rehearse the upgrade on an isolated copy first. Do not rerun bootstrap, recreate users, or change an existing UID.

Migration `0085_organization_foundation` adds a constrained `organization_type` column to `labs`, defaulting existing rows to `laboratory`. UUIDs, membership, foreign keys, projects, assets and permission grants are preserved. Bootstrap still rejects any instance containing users or organizations.

To use an existing single-lab instance as a company workspace, preserve its original organization and default project UIDs, select `single_organization` after upgrade verification, and explicitly change its stored type in Settings. Environment type is a bootstrap default, not an override of existing data. The new mode changes future invitation defaults; review them before inviting people.

`SINGLE_ORGANIZATION_{UID,NAME,DESCRIPTION,DEFAULT_PROJECT_UID,DEFAULT_PROJECT_NAME}` are the canonical aliases of the corresponding `SINGLE_LAB_*` keys. `ORGANIZATION_STRUCTURE_MODE` aliases `LAB_STRUCTURE_MODE`. Conflicting new/legacy values fail startup. `SINGLE_ORGANIZATION_TYPE` accepts `company`, `institution`, `laboratory`, or `other`. Old configuration remains usable without renaming; community multi-organization behavior remains compatible.

## Compatibility contract and impact inventory

| Area | P0 behavior |
| --- | --- |
| ORM/storage | `Organization`, `OrganizationMember`, and `OrganizationRole` alias the existing mapper; physical `labs`, `lab_users`, and `lab_id` remain. Project/member `organization_id` is a synonym, not new ownership. |
| Organization API | `/organizations` lists, creates, reads by UUID/UID, and updates through the existing authorization handlers. `/{organization_id}/members` provides member operations. Single-instance membership still requires invitations. |
| Projects | Create accepts `organization_id` or `lab_id`; conflicting values fail. Responses preserve `lab_id` and add the same `organization_id`. |
| Instance | Adds `single_organization`, `organization`, structure and defaults. Legacy `single_lab` and `lab` describe the same capability/identity; the boolean is not an organization-type classifier. |
| Permissions | Existing scope grants, organizational units, private and Restricted boundaries remain unchanged. |
| Deep links/specialized APIs | Legacy browser `/labs/...` links redirect to deployment-specific URLs. Existing `/labs` APIs and `lab` scope values retain the same authorization. |
| IDs/SDK/MCP/archives | Existing `airalogy.id.lab.…` Protocol IDs and Record references are not rewritten. A possible `.org.` format requires a separately verified SDK transition. No SDK upgrade is required now. |
| Queues/cache/audit | No global replacement of persisted identifiers or historical audit text. |
| Deployment/recovery | Existing backup mechanisms remain; configuration revision includes new organization settings. |

Compare UUIDs, member/project counts, grants and version references on the isolated upgrade copy. Restore a verified database recovery point with matching application artifacts when needed; downgrading refuses to discard non-laboratory organization types. Account for writes made after cutover. Switching the application image alone is not database recovery.

Local acceptance covers historical-schema upgrade/downgrade, foreign-key preservation, legacy/canonical API authorization parity, company bootstrap, invitation defaults, private document isolation and browser workflows for both profiles. Synthetic tests do not replace the target deployment's backup/restore rehearsal.

Organization names accept 1–64 characters after trimming surrounding whitespace. URL identifiers and personal usernames retain their own rules. Organization owners/managers have a dedicated header entry (a first-level menu item on mobile); ordinary members keep their existing read-only member links. Personal account settings and system administration remain separate.
