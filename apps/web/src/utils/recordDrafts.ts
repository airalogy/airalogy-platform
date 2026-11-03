import type { IRecordData } from "@airalogy/aimd-core/types"
import { localStg } from "@/utils/storage"
import { cloneDeep as _cloneDeep } from "lodash-es"
import { toRaw } from "vue"

const contextKeys = ["record", "recordVersion", "researchWorkItem", "chain", "target"] as const

export function recordDraftQuery(query: Record<string, unknown>): Record<string, string> {
  const selected: Record<string, string> = {}
  for (const key of contextKeys) {
    if (typeof query[key] === "string")
      selected[key] = query[key]
  }
  return selected
}

export interface DraftScope {
  version: string
  query: Record<string, string>
}

export interface RecordDraft<T = Partial<IRecordData>> {
  draftId: string
  scope?: DraftScope
  simulatedFields?: string[]
  protocolId: string
  data: T
  timestamp: number
}

type StoredRecordDraft<T = Partial<IRecordData>> = Omit<RecordDraft<T>, "protocolId" | "draftId"> & { protocolId?: string }
type DraftStorage = Record<string, Record<string, StoredRecordDraft<any>>>

/** Empty form initialization is not outstanding work; keep 0 and false as data. */
export function hasRecordDraftContent(value: unknown): boolean {
  if (value === null || value === undefined)
    return false
  if (typeof value === "string")
    return Boolean(value.trim())
  if (Array.isArray(value))
    return value.some(hasRecordDraftContent)
  if (typeof value === "object") {
    return Object.values(value).some(hasRecordDraftContent)
  }
  return true
}

function normalizeUserDraft(raw: unknown): Record<string, StoredRecordDraft> {
  if (!raw || typeof raw !== "object") {
    return {}
  }

  if (Array.isArray(raw)) {
    const result: Record<string, StoredRecordDraft> = {}
    for (const key of Object.keys(raw)) {
      const value = raw[Number(key)] as StoredRecordDraft | undefined
      if (value) {
        result[String(key)] = value
      }
    }
    return result
  }

  return raw as Record<string, StoredRecordDraft>
}

function readDraftStorage(): { storage: DraftStorage, migrated: boolean } {
  const raw = localStg.get("unitRecordDraft")
  if (!raw || typeof raw !== "object") {
    return { storage: {}, migrated: false }
  }

  let migrated = false
  if (Array.isArray(raw)) {
    migrated = true
  }

  const storage: DraftStorage = {}
  for (const [userKey, userDraft] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(userDraft)) {
      migrated = true
    }
    storage[userKey] = normalizeUserDraft(userDraft)
  }

  if (migrated) {
    localStg.set("unitRecordDraft", storage)
  }
  return { storage, migrated }
}

export function listRecordDrafts(userId: string | number): RecordDraft[] {
  const { storage } = readDraftStorage()
  const drafts = storage[String(userId)] || {}
  return Object.entries(drafts)
    .filter(([, draft]) => draft && hasRecordDraftContent(draft.data))
    .map(([draftId, draft]) => ({ ...draft, protocolId: draft.protocolId || draftId, draftId }))
    .sort((a, b) => b.timestamp - a.timestamp)
}

export function listProtocolDrafts(userId: string | number, protocolId: string | number, scope?: DraftScope) {
  return listRecordDrafts(userId).filter(item =>
    item.protocolId === String(protocolId)
    && (!scope || (item.scope
      ? item.scope.version === scope.version && JSON.stringify(item.scope.query) === JSON.stringify(scope.query)
      : !Object.keys(scope.query).length)),
  )
}

export function getRecordDraft<T = Partial<IRecordData>>(
  userId: string | number,
  protocolId: string | number,
  draftId?: string,
  scope?: DraftScope,
): RecordDraft<T> | null {
  const draft = listProtocolDrafts(userId, protocolId, scope).find(item => !draftId || item.draftId === draftId)
  return draft as RecordDraft<T> | undefined || null
}

export function saveRecordDraft<T>(
  userId: string | number,
  protocolId: string | number,
  data: T,
  options: { draftId?: string, scope?: DraftScope, simulatedFields?: string[] } = {},
): RecordDraft<T> {
  const { storage } = readDraftStorage()
  const userKey = String(userId)
  const draftId = options.draftId || String(protocolId)
  const draft = {
    protocolId: String(protocolId),
    scope: options.scope,
    simulatedFields: options.simulatedFields,
    data: _cloneDeep(toRaw(data)) as T,
    timestamp: Date.now(),
  }
  storage[userKey] ||= {}
  storage[userKey][draftId] = draft
  localStg.set("unitRecordDraft", storage)
  return { ...draft, draftId }
}

export function deleteRecordDraft(userId: string | number, protocolId: string | number, draftId = String(protocolId)) {
  const { storage } = readDraftStorage()
  const userKey = String(userId)
  const draft = storage[userKey]?.[draftId]
  if (!draft || (draft.protocolId || draftId) !== String(protocolId))
    return

  delete storage[userKey][draftId]
  if (Object.keys(storage[userKey]).length === 0) {
    delete storage[userKey]
  }
  localStg.set("unitRecordDraft", storage)
}
