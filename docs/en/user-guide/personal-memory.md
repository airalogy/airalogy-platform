# Aira personal memory

Personal memory carries explicitly chosen communication preferences into new conversations. This first version supports **language, detail, format and explanation style**. It does not scan old conversations, infer habits or store measurements, patient information or project content.

## Set preferences

Open **Aira personal memory** in account settings, or **Personal memory** above the Aira input. Save your choices; clearing one option forgets that preference. The management panel can undo its last edit.

You can also send explicit commands, combining preferences with commas:

- `Remember: reply in English, be concise`
- `Remember: use numbered steps`
- `Remember: be detailed, use technical terms`
- `Forget language`
- `Forget all my preferences`

Platform processes these commands deterministically without a model. Unsupported or mixed commands are declined without partially saving them. More specific current instructions take priority.

Preferences guide ordinary chat, explanatory prose in Protocol generation, and explanations of computed analysis results. They cannot change field IDs, units, types, validation or calculations. Recorder conversational filling does not yet receive these preferences: it retains its strict requirement for actual values supplied in the current message.

## Turn off or forget

- **Turn memory off and save** to keep preferences without reading them or accepting chat memory writes. You can enable it again.
- **Do not use memory in this conversation** stops further reading and saving for that conversation. Start a new conversation to use memory again. Chat history is still retained; this is not incognito mode.
- **Clear all** deletes current preferences. Subsequent requests no longer use them, and retries of old successful requests cannot restore them.
- **Export** downloads current preferences with provenance and timestamps. Change history keeps operation times, preference categories and revisions, not deleted values.

These actions do not retroactively delete in-flight model requests, existing answers, user messages or browser-local conversation history. Deleting a chat does not delete personal memory. Concurrent changes in another window require reloading before saving.

Only the current account can manage its memory, in the current Platform instance. It is not shared with Lab or Project members or exposed through external Agent project tokens. Ordinary chat continues without personalization if memory is unavailable. Account settings remain available for viewing, editing, clearing and exporting when AI is off.

Automatically suggested memories, work-progress memory and project knowledge retrieval are later phases, not part of this first version.
