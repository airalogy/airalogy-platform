# Get started with Airalogy Platform

First visit? Open [Getting started and demos](../learn/) and choose an existing Protocol, a document, a new experiment or a spreadsheet import.

Airalogy Platform organizes research work so that a procedure, the data collected with it, and the people responsible for it stay connected. The exact sign-in and account-admission flow depends on how your organization operates its instance; the research workflow is the same in Community Edition and private deployments.

## Sign in or join an instance

- If self-registration is enabled, create an account with the fields shown on the sign-up page and then sign in.
- If the instance is invite-only, use the invitation link supplied by a Lab administrator. Existing users can accept the invitation after signing in; new users create their account through the invitation flow.
- If registration is disabled, ask the instance operator or a Lab administrator how accounts are provisioned.

Do not reuse passwords from other services. If your instance provides a password-reset link, treat it as a short-lived secret and do not forward it.

## Understand the workspace

Platform uses four connected resource types:

| Resource | Purpose                                                                     |
| -------- | --------------------------------------------------------------------------- |
| Lab      | Owns the research workspace, membership, and top-level governance.          |
| Project  | Groups work around a study, team, or objective.                             |
| Protocol | Defines what should be done and which structured fields should be recorded. |
| Record   | Captures one completed or in-progress use of a Protocol.                    |

A deployment may present one fixed Lab or allow users to join several Labs. Projects and Protocols can have additional access rules, so seeing a Lab does not automatically mean that every resource inside it is visible.

## Continue from Home

The signed-in home page leads with **Your projects**: pinned projects first, followed by your own recent visits. Without visit history, it offers available projects and explains how to start. Another member updating a project does not change your personal recency order.

The desktop header links to Home, Projects, Protocols, Documents, and Knowledge. Open More for research tasks and logs. Use New on the right to create content. On phones, tap the current section to navigate or open the account menu for language settings and Aira when enabled.

Ask Aira on Home opens a side panel. All chats in the panel opens the dedicated chat page in a new tab, keeping the Home draft in place. Account history lists saved general conversations for the signed-in account and lets you continue them on another device. On phones, open Chat history first. Older conversations with verified server ownership appear here. Legacy browser-only data without an identifiable owner is left unassigned.

- Select a project name to open Overview. Project navigation is Overview, Protocols, Documents, Materials, then Knowledge.
- **Continue** opens the last document, Protocol page or Record report. The Protocols and Documents shortcuts retain the project context.
- A compatible Record draft on this browser offers **Continue Record**, labeled **Saved on this device**. Visit history never uploads draft values. Another device can reopen a recent page, but cannot restore unsynchronized values from the original browser.
- **My documents** remains separate: personal writing is visible only to you and does not require a Project.
- The attention area shows real assigned work, approvals and result reviews. Other pinned resources and activity appear below.

History is private to the account and retains up to 50 projects; project pins reuse existing resource pins. Every history read rechecks permissions, so deleted or inaccessible assets no longer expose their titles or links. Migration `0081_project_visits` adds navigation history without changing research data.

## A practical first workflow

1. Open the relevant Lab and Project.
2. Choose an existing Protocol or create one if your role permits it.
3. Review the Protocol description, fields, steps, checks, and current version before recording.
4. Create a Record, enter the requested values, attach files where required, and save or submit it.
5. Open the Record again to confirm that the stored values, files, and context are correct.
6. Share the Project or Protocol with collaborators through the membership and access controls provided by your Lab.

## Where to go next

- [Protocols](./protocols) explains creation, versions, editing, and reuse.
- [Records](./records) covers entry, validation, files, history, and safe handling.
- [Research automation](./research-automation) explains auditable Research Tasks, human work, digital tools, external result boundaries, and scientific review.
- [Collaboration](./collaboration) explains workspace roles and sharing.
- [Search](./search) describes finding resources without assuming access you do not have.
- [Import and export](./import-export) covers CSV import and governed Record exports.

If an interface option described here is absent, it is usually disabled by the deployment profile or unavailable to your current role. Ask the relevant Lab or instance administrator rather than creating a parallel copy of the data elsewhere.

- [Coordinate R&D work](./rd-workbench.md)
