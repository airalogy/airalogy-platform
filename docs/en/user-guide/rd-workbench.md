# Coordinate R&D in a Project

Open **Project → R&D work** to create requirements, tasks, issues and milestones. A Protocol, automated Run or AI service is not required. Protocols remain a prominent Project entry and can be linked when repeatable execution is useful.

Under **Organization management → Members**, owners and authorized administrators can set an organization display name. Clearing it restores the member’s profile name. Personal notes are visible only to their author. Meeting and work-item pickers show the organization display name and store the account ID. Renaming a member preserves existing assignments and the participant names recorded in earlier meetings.

Drag a board card to another status column or use its Move to menu. Moving to Blocked requires a blocker. Completing work requires acceptance conditions and completed dependencies. The change appears in the item history.

## Start with a concrete goal

For a glasses prototype, create a work item such as “Verify the first optical prototype.” Define the goal and completion conditions, optionally assign a responsible person and collaborators, and enter priority and planned dates. Let the team determine scientific thresholds; the platform does not invent acceptance criteria.

Split design, procurement, firmware and testing into separate work items with dependencies. List, board and planning timeline read the same task identity and state. The home assignment inbox opens unfinished assigned work directly.

Create a project design document from an item, or link existing documents, Protocols, Records, materials, analyses and research executions. Document, Protocol and Record links pin exact versions. Document and Protocol evidence can be inspected as the linked snapshot. Edit the ordinary asset through its original entry point.

Creating a design document saves that document first; saving the work item establishes the association. If linking fails, the document is still available in Project Documents.

## State, testing and acceptance are separate

Work states are pending, in progress, blocked, in review, done and cancelled. A blocker needs an explanation. Completing work requires stated completion conditions and completed prerequisites. Reopen completed dependents before reopening a prerequisite.

A test result is separately passed, failed or inconclusive and requires evidence, reasoning and actual occurrence time. Business acceptance is an explicit authorized action with its own outcome and evidence. Marking work done creates neither a passing test nor acceptance. Item counts are not project completion percentages.

The planning timeline shows entered start/end dates only. It does not infer duration. User-entered actual occurrence time and server-recorded entry time remain separate.

## Discussion and decisions

Contributors can add discussion, progress, test results and proposed decisions. Project approvers can adopt decisions and record business acceptance. Activities retain their author and recorded time and cannot be edited or deleted. A new decision can supersede an earlier one without erasing it; replacing an adopted decision requires another authorized adoption.

Project Log projects creation, state transitions, progress, decisions, tests and acceptance from the authoritative events and links back to work. Text-only edits and ordinary discussion are not presented as progress.

## Saving, concurrent work and permissions

Successful saves identify the Project and revision. Stale updates fail without discarding local input. Inspect the current server version and explicitly compare/merge before saving again. Browser recovery can preserve unfinished input on the same device; it is not a server save or cross-device synchronization.

Work uses existing Project permissions. Public visibility does not expose work, discussion or work log events to nonmembers. Read-only members cannot write. Assignment never grants project membership. Only authorized same-project evidence can be linked; personal or other-scope assets require explicit publication first. Reads recheck current source permissions and redact unavailable references.

## Delivery boundary

This is the local P0 workflow for [Issue #26](https://github.com/airalogy/platform/issues/26), with a basic planning timeline. Time sheets, resource scheduling, cost accounting, BD synchronization, shared identity and autonomous coding agents are separate follow-ups. Validate task granularity and review habits with the real team before expanding those areas.

## Daily navigation

Open R&D work directly from a Home project card, or create an item from Project overview. A title is enough to create a pending item; add owners, dates and evidence later. The drawer footer keeps the save action and persistence state visible. Missing required fields receive specific feedback and focus.

Saved items separate details from discussion and progress. Switching between these areas preserves input. Save changed details before posting activity so the activity references the current item revision. Activity recovery includes dates, outcomes and evidence even before body text is entered.

List, board and plan views share search, assignee and state filters. Filter unfinished items or a specific state; clear filters when no results match. Loading is distinct from an empty project. The assigned-work section on Home can load additional pages beyond its first six items.

## Organization research overview

On a single-organization instance, open Projects → Research overview, or use the Research overview link beside All projects on Home. Existing bookmarks under Organization management open the same page. On a multi-organization instance, open the relevant organization and select Research overview beside Projects.

The overview shows project owners, blockers, recorded next steps and the next open milestone. Blocked projects appear first. Milestones use the earliest planned end date, falling back to the planned start date. Overdue open milestones remain visible. Follow a link to open the original work item.

Select a day on the 90-day heatmap to see its project activities and sources in your browser time zone. Select it again to return to recent activity. Organization owners and managers can use this page. Source permissions still apply to meetings, records and other research assets.
