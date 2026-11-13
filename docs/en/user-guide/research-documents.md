# Research notes and original materials

Project **Overview** opens recent research notes. Choose **New document** to start blank or use a built-in or custom template. In a Project, **Use an existing Protocol** also copies an exact method version from this entry. A shared Protocol is not required. The home workbench links directly to your recent notes.

## Write, save and revisit

Use visual AIMD editing or source mode. Add fields when useful; you can leave prose, syntax and field values unfinished while saving. **Saved** only confirms persistence, not scientific or schema validation. The server retains revisions. Restoring a revision creates a new revision. Concurrent edits are rejected instead of overwriting another saved version.

Research notes also appear in the Log timeline: both views reference the same entry. Existing Log and Knowledge content is not converted or reinterpreted. Use **Tags** and **Collection** for lightweight organization; they do not change permissions.

## Record one experiment

Keep intended parameters in the plan and enter measurements in the relevant fields. Record actual operations and deviations in the corresponding sections. Adding a field does not turn a note into a shared Protocol. Changing definitions with existing values requires review. Removing fields retains their saved values until explicitly removed through **Review saved values**; history remains available.

**Validate** checks the saved definition and values. **Submit result** previews and seals a version containing the exact prose, field definitions, values and attachment checksums. Failed validation creates no result. This result belongs to the document; it is not a legacy Protocol-bound Record and does not appear automatically in Protocol Record analyses. Editing afterward creates a working revision without rewriting submitted evidence. **Repeat this experiment** copies the definition and provenance without measurements, signatures or attachments.

The initial declarative contract supports text, integers, numbers, booleans, dates, datetimes, optional values, scalar choices and tables with supported field constraints. Types needing Python, file/resource resolution, collectors or assigners remain in the ordinary Protocol runtime. Opening a note does not execute these capabilities.

## Archive existing material

Open **Materials** and upload original photographs, PDFs, tables or instrument files. Add a source note and, if known, a historical date. This date is separate from the upload timestamp. Supported PDFs and images have a safe preview; other formats remain downloadable. Associate materials with a note using **Attach material**.

Text PDFs and UTF-8 text files can be extracted, reviewed and used to create a new note with the original attached. This is deterministic text extraction, not OCR. Handwritten or scanned-only materials remain available for manual transcription. No extracted value is automatically submitted as a measurement.

Uploading a CSV here archives a file. It does **not** import Records. Use the existing Protocol CSV template/import operation to create Records; invalid imports still create zero Records.

## Export, restore and reuse

**Export document** downloads a versioned ZIP with the current AIMD, field values and attachment bytes/checksums. **Restore a document archive** checks integrity and previews the destination before creating an independent working document. It preserves current content, not the authority of prior approvals or submitted evidence. The original document's revision history remains on the source platform. Archive size is limited to 64 MiB; larger originals can be downloaded individually.

**Derive an asset** lets you review prose before creating a Knowledge draft or a downloadable Protocol draft package. Enter intended reusable defaults explicitly and remove private observations from the proposed method. Measured field values and attachments are excluded. The source revision is retained privately. Knowledge review and Protocol publication continue through their existing interfaces.

## Visibility and limits

Personal notes are private. Project and Lab notes use existing member permissions; a public Project does not expose notes or materials. Only the author can revise a note. Attachments must have the same audience, with every read and export checked again. A copy does not grant access to an original file.

The initial implementation does not include OCR, handwriting recognition, real-time collaboration, automatic cross-Lab sharing or full downstream analysis of document results. Core writing, material archiving and submission work without AI. See [RFC #21](https://github.com/airalogy/platform/issues/21) for the follow-up phases.

## Document templates

Use the single **New document** entry to start blank or select an experiment, meeting or research-progress template. Preview the content and destination before creating an independent document. In a Project, the existing Protocol source picker is available inside this dialog. A template is a starting point, not a requirement to publish a Protocol.

The **Document templates** tab supports custom starters. Use **Save as template** on an existing document, or **New template** in the library. Edit the name, purpose, headings, instructions and field definitions in visual or source mode, select Personal, Project or Lab scope, then preview and confirm. Filled field values, attachment reference lists and submission authority are never carried over. Review the prose yourself and remove specific observations and private links. Author intended parameter defaults explicitly in AIMD, for example:

```text
{{var|temperature: float = 25, ge=0, le=100}}
```

The server validates these defaults and leaves unanswered result fields blank.

Personal templates are private. Project and Lab templates are restricted to authorized members, including in public Projects. Creation uses existing document write permissions: Project member capabilities, and Lab Owner/Manager or explicitly granted Lab Log publishing capability. Authors and scope managers can revise, archive and restore templates. Readers may use a template in a destination where they can create documents. Every read, copy and use rechecks current access.

**Copy to a scope** creates a separate reviewed template without moving the source or widening document/file permissions. Template edits create revisions; existing documents retain their selected version and content. Stale selections require a new preview. Archiving prevents future use while preserving documents; archived templates can be restored.

## Audience and chronological browsing

The scope selector chooses Personal, Project or Lab storage. The list, creation dialog and reading/editor views display the destination and actual audience. Personal documents are private. Project documents are visible to authorized Project members and the Lab Owner/Managers; Lab documents are visible to Lab members. Working drafts follow the same audience. Only the author can revise a document, and public Project visibility does not publish documents.

Set **Record date** to when the experiment, meeting or research happened, including historical work. Editing prose changes **Updated**, not the record date. Date filters and day headings use your device's timezone, including daylight-saving boundaries. **Recently updated** helps resume work; **By record date** groups notes chronologically. **Browse calendar** shows matching document counts for the selected month and current search/type. Choosing a day applies a date filter; **Clear dates** returns to the wider list.

Select a document to read its prose, saved fields and attachments. Desktop screens show the list beside the reading pane; narrow screens show one document at a time. **Previous document / Next document** continue across list pages using the same scope, search and date filters. **Edit document** opens the existing editor with its normal autosave and unsaved-change protection. Returning preserves the browsing context; if an edit moves the document outside the current filter, the list explains that instead of silently changing the filter. Browsing does not write or submit data. The Log timeline references the same document and occurrence time.

## Focused writing and optional actions

**Documents** in the main navigation opens personal documents, with Project and Lab scope switching. New documents start with common templates; **Browse more templates** exposes shared templates and the Project's Protocol sources. Recently used custom templates store only identifiers per account on this browser; every opening re-fetches their current content and permissions. Record date defaults to today and can be expanded for historical entries.

Writing emphasizes the title and body with visible autosave status, retry on failure and unsaved-change protection. Visual mode uses the SDK's input insertion controls; source mode retains field insertion assistance. **Details** contains tags, collections, attachments and provenance. **More** groups history, submitted results, reuse and file actions. Ordinary writing requires no submission. Expand **Check and submit experiment results** when a fixed result snapshot is needed; validation, preview, confirmation and immutability remain enforced.

Lists emphasize content, search and sorting. **Filters** contains type, dates and calendar navigation. Active conditions remain visible with a clear action even when collapsed. Reading retains scope, filters and return context.

The home workbench retains real task priority and compares the latest document with the latest local Record draft to offer the relevant continuation. Recent documents open directly in the editor. Project overview emphasizes recent content and creation; its Documents tab and new-document action retain the current Project scope.

The document list keeps New document visible for members with write access. More contains document templates and archive import. Empty spaces show a getting-started prompt; populated lists group search, sort and filters in one toolbar. A search with no matches offers to clear the search and filters without creating documents or changing scope.

Use the header **New → New document** shortcut from any workspace. From a Project, Lab or an existing document, it opens the same template dialog in that explicit scope after checking write access. From Home or other global pages, it starts in private personal storage; having only one Lab does not make personal writing shared. Review the destination and audience before creating. The workspace navigation menu opens existing content; New creates content. Project and Lab creation sit below the everyday content actions.
