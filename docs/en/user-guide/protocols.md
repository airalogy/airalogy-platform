# Protocols

A Protocol is a reusable, versioned description of a research procedure and its structured data fields. It can combine readable instructions with steps, checks, variables, files, and other typed inputs.

## Find or create a Protocol

Open a Project to see Protocols owned by that Project. Depending on your role, you can create a Protocol directly, start from an available example, import a supported package, or use the AI-assisted drafting flow. Review generated or imported content before it becomes part of a real research process.

Use a stable, descriptive Protocol ID where the interface requests one. Display names and descriptions can explain the scientific purpose; identifiers are used in routes and integrations and may not be safely changeable later.

Visitors opening a private shared link can sign in and return to the original page. If the link is still unavailable, ask the person who shared it to check the URL and your project, Protocol or Record access. Public Protocols that allow anonymous reading in the community edition can still be opened directly.

Aira-generated Protocols are checked before being handed over as drafts. If a deterministic check fails, Aira attempts one minimal repair and the result is checked again. A failed or ambiguous repair retains the original draft. The editor also checks current AIMD, Python and TOML sources after edits and before saving, showing file names and line numbers when available. Choose **Ask Aira to repair** to review a proposed diff; it is not applied until you confirm. Changes made while waiting are protected by the existing conflict check.

**Static checks passed** covers AIMD structure, references, assigner dependencies and Python/TOML syntax. It does not certify scientific correctness, external dependencies or client JavaScript execution. Saving still validates the complete package in the isolated Protocol executor. A checker outage is reported separately from invalid syntax. Manual checks remain available with AI disabled; fix reported issues or retry before saving. Failed checks retain the local draft.

## Practice without AI or equipment

In a Project, choose **New protocol → From template → First Record practice**. Give the draft a recognizable name, open it in the editor, and choose **Save**. Check the destination Lab, Project and version before confirming. You need permission to create Protocols; a recorder can ask the Protocol owner to prepare this once for the team.

The bilingual practice template contains two required fields, example values and instructions for saving, submitting and revising a Record. It creates an ordinary editable, versioned Protocol, not a separate demo mode. Its data is explicitly synthetic: keep it in a practice Project and do not treat it as research evidence. No AI service is needed.

Use **WYSIWYG** to edit the procedure alongside its field controls. Switch to **Source** to edit AIMD directly. A published version opens read-only. Start a draft to change the procedure.

In **Preview**, choose **Test with example data**. Edit the example values and choose **Validate test form** to see which fields need attention. **Exit test** discards the test form. Draft checks use current AIMD declarations. A published version can also use its stored validation schema. Python code runs only in the normal Platform execution workflow.

## Edit with intent

Before changing a Protocol that already has Records:

1. Confirm which version is active and whether downstream work depends on its fields.
2. Prefer additive, compatible changes when existing Records must remain comparable.
3. Treat renamed, removed, or retyped fields as schema changes that need explicit review.
4. Preview the rendered Protocol and resolve validation errors before publishing or recording.

AI assistance can draft or explain changes, but the responsible researcher remains accountable for scientific correctness, safety, and the final field definitions.

## Calculated fields: client or server

Small deterministic calculations can stay in one `protocol.aimd` file:

````aimd
Length: {{var|length: float, ge=0}}
Width: {{var|width: float, ge=0}}
Area: {{var|area: float, ge=0}}
```assigner runtime=client
assigner(
  {mode: "auto", dependent_fields: ["length", "width"], assigned_fields: ["area"]},
  function calculate_area({length, width}) { return {area: length * width}; }
);
```
````

Client modes are `auto`, `auto_first` and `manual`. Inputs and outputs must be declared fields; each output has one writer and dependencies cannot form cycles. Calculations run only in an editable Record, using the restricted AIMD JavaScript runtime. Invalid inputs or outputs show an error rather than saving a partial result. Read-only reports retain their saved values.

Use server-side Python for external services, files, secrets, scientific libraries, heavy computation or authoritative verification. A browser result is not a security or scientific-integrity guarantee. Do not store JavaScript in `assigner.py`; Python may remain in a plain `assigner` fence or a standalone `assigner.py`, without duplicate implementations.

CSV/API imports do not run browser calculations. Supply the derived fields required by the downloaded template; missing or invalid required values are rejected. Review formulas and source observations before using either runtime for real research.

## Reuse and workflows

Protocols can be reused across experiments when the procedure and data contract are genuinely the same. Use a separate Protocol or an explicit new version when the scientific meaning changes.

Where Protocol Workflow is available, multiple Protocols can be connected into a directed research process. Check the starting Protocol, transitions, and data mapping before execution. A workflow should make hand-offs visible; it should not hide undocumented assumptions between steps.

## Share in a single-organization workspace

Open **Share** on the project or Protocol to see who can open the workspace link.

- New projects default to **Project members only**. Add collaborators under **Team** to grant ongoing access by role.
- In **Project settings → Project visibility**, enable organization reading to let signed-in members read the project introduction and Protocols that inherit project permissions. Records, meetings, finances and Protocols with individual permissions keep their own access rules. To share only one version internally, publish an organization link from that Protocol.
- For external readers, an organization owner or administrator first enables external publishing under **Organization management → Settings**. An authorized publisher then opens **Share**, selects the version and public audience, previews the text, selects the accompanying materials, and confirms publication. Anyone who can reach the deployment and has this link can read it without signing in.
- A project introduction can be published separately. Its page lists only explicitly published public versions. Later versions require publication of their own. Withdraw a link in **Share** to disable the page and its downloads. Turning off external publication withdraws all of the organization's public links; turning it back on requires fresh publications.

Upgrading a single-organization instance converts its legacy public projects to organization reading. To share externally, review and publish the content and use the resulting link.

## Share and cite

Access is determined by Lab, Project, and Protocol rules. Share through Platform membership and grants rather than copying unpublished content to an uncontrolled location. Stable Platform routes can be used to reference a Protocol, but recipients still need the required access.

See [Collaboration](./collaboration) for role guidance and [Records](./records) for using a Protocol to capture data.

## Ratings and use

Use **Ratings & use** for version-specific reviews, optional execution feedback and the transparent trial recommendation. See [Protocol ratings and adoption](../product/protocol-rating.md) for counting, scoring and privacy rules.

## Reading a saved Record

Open the report from the Record list or its detail page. Reports open in **Detailed** to highlight step levels and recorded values. Choose **Compact** for a text-first layout. In either view, each checkpoint is labeled **Checkpoint**, followed by its title, saved status and any notes. This browser remembers your selection.
