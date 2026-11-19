<script setup lang="ts">
import type { Book, Entry, Kind, Metric, Revision, Value } from "@/service/api/project-operations"
import { money, readOps } from "@/service/api/project-operations"
import { request } from "@/service/request"
import { localDocumentDate } from "@/utils/documentBrowse"
import { useOrProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import EntryEditor from "./entry-editor.vue"
import { amountFields, enums, fields, useOpsText } from "./fields"

const { projectInfo } = useOrProvideProjectInfoStore(null)
const pid = computed(() => projectInfo.value?.id)
const tr = useOpsText()
const router = useRouter()
const route = useRoute()
const book = ref<Book>()
const error = ref("")
const notice = ref("")
const loading = ref(false)
const selected = ref("")
const asOf = ref(String(route.query.as_of || localDocumentDate()))
const filter = ref("")
const query = ref("")
const history = ref<Revision[]>([])
const preview = ref("")
const editor = ref<{ kind: Kind, entry?: Entry, action: "save" | "void" | "return" | "verify" }>()
const current = computed(() => book.value?.entries.find(e => e.id === selected.value))
let requestNumber = 0
async function load() {
  const token = ++requestNumber
  const id = pid.value
  if (!id)
    return
  loading.value = true
  error.value = ""
  try {
    const b = await readOps<Book>(`/projects/${id}`, { as_of: asOf.value || localDocumentDate() })
    if (token === requestNumber)
      book.value = b
  }
  catch {
    if (token === requestNumber) {
      book.value = undefined
      error.value = tr("unavailable")
    }
  }
  finally {
    if (token === requestNumber)
      loading.value = false
  }
}
watch(
  pid,
  () => {
    book.value = undefined
    selected.value = String(route.query.entry || "")
    history.value = []
    preview.value = ""
    editor.value = undefined
    void load()
  },
  { immediate: true },
)
watch(asOf, load)
watch(
  () => route.query,
  (q) => {
    asOf.value = String(q.as_of || localDocumentDate())
    filter.value = String(q.metric || "")
    selected.value = String(q.entry || "")
  },
  { immediate: true },
)
const metrics: Metric[] = [
  "gross",
  "received",
  "paid",
  "net_cash",
  "direct",
  "profit",
  "unpaid",
  "overdue",
  "unmatched",
  "pending",
  "shared",
]
const rows = computed(() =>
  (book.value?.entries ?? []).filter((r) => {
    const s = book.value!.summary
    const ids = s.sources[filter.value] ?? s.contracts[filter.value]?.entries
    return (
      (!filter.value || (ids ? ids.includes(r.id) : r.kind === filter.value))
      && (!query.value
        || String(r.data.title || r.data.basis || "")
          .toLowerCase()
          .includes(query.value.toLowerCase()))
    )
  }),
)
function caption(e: Entry) {
  return String(e.data.title || e.data.basis || tr(e.kind))
}
function value(key: string, v: Value, e?: Entry): string {
  if (v == null || v === "")
    return "—"
  if (typeof v === "object")
    return `v${v.version} · ${v.id}`
  if (amountFields.has(key) && typeof v === "number")
    return money(v)
  if (key === "kind" || enums[key])
    return tr(String(v))
  const linked = book.value?.entries.find(r => r.id === v)
  if (linked)
    return caption(linked)
  if (key === "work_id" && e)
    return tr("openWork")
  return String(v)
}
function pick(id: string) {
  selected.value = id
  history.value = []
  preview.value = ""
  editor.value = undefined
}
function selectMetric(metric: Metric) {
  filter.value = metric
  pick("")
}
function open(kind: Kind) {
  const existing = ["forecast", "closing"].includes(kind)
    ? book.value?.entries.find(e => e.kind === kind && e.status !== "void")
    : undefined
  editor.value = { kind, entry: existing, action: "save" }
  notice.value = ""
}
async function saved() {
  editor.value = undefined
  preview.value = ""
  history.value = []
  await load()
  notice.value = tr("saved")
}
async function showHistory(id: string) {
  const p = pid.value
  try {
    const result = await readOps<{ events: Revision[] }>(`/projects/${p}/entries/${id}/history`)
    if (p === pid.value && id === selected.value)
      history.value = result.events
  }
  catch {
    error.value = tr("unavailable")
  }
}
async function openEvidence(e: Entry, field: string, download = false) {
  const path = `/projects/${pid.value}/entries/${e.id}/evidence/${field}`
  try {
    if (field.endsWith("_doc") && download) {
      const { data, error } = await request<Blob, "blob">({
        url: `/project-operations${path}`,
        params: { download: true },
        responseType: "blob",
      })
      if (error || !data)
        throw new Error("Evidence unavailable")
      const url = URL.createObjectURL(data)
      const a = document.createElement("a")
      a.href = url
      a.download = `${field}.aimd`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
    else {
      const d = await readOps<{ href?: string, url?: string, title?: string, body?: string }>(
        path,
        { download: String(download) },
      )
      if (d.href) {
        await router.push(d.href)
        return
      }
      if (d.url) {
        const { data, error } = await request<Blob, "blob">({ url: d.url, responseType: "blob" })
        if (error || !data)
          throw new Error("Evidence unavailable")
        const u = URL.createObjectURL(data)
        const a = document.createElement("a")
        a.href = u
        if (
          download
          || !["application/pdf", "image/jpeg", "image/png", "image/webp", "text/plain"].includes(
            data.type.split(";")[0],
          )
        ) {
          a.download = "receipt"
        }
        else {
          a.target = "_blank"
          a.rel = "noopener"
        }
        a.click()
        setTimeout(() => URL.revokeObjectURL(u), 60000)
      }
      else if (e.id === selected.value) {
        preview.value = [d.title, d.body].join("\n\n")
      }
    }
  }
  catch {
    error.value = tr("unavailable")
  }
}
function canEdit(e: Entry) {
  if (!book.value || book.value.role === "viewer" || e.status === "void")
    return false
  return book.value.role === "finance"
    ? ["cost", "cash", "closing"].includes(e.kind)
    : !["cash", "closing"].includes(e.kind)
}
const createKinds = computed<Kind[]>(() =>
  book.value?.role === "lead"
    ? ["cost", "contract", "installment", "forecast"]
    : book.value?.role === "finance"
      ? ["cash", "closing", "cost"]
      : [],
)
</script>

<template>
  <section class="ops" data-testid="operations-book">
    <div class="ops-line">
      <h2>{{ tr("book") }}</h2>
      <template v-if="book && projectInfo">
        <span>{{ book.owner?.name }} · {{ tr(book.role) }}</span>
        <router-link :to="{ name: 'lab-operations', params: { labUid: projectInfo.lab_uid } }">
          {{ tr("overview") }}
        </router-link>
      </template>
    </div>
    <p v-if="error" role="alert">
      {{ error }}
    </p>
    <p v-if="loading" role="status">
      {{ tr("loading") }}
    </p>
    <template v-if="book">
      <div class="ops-line">
        <label>
          {{ tr("overdueDate") }}
          <input v-model="asOf" type="date">
        </label>
      </div>
      <div class="ops-metrics">
        <button
          v-for="m in metrics"
          :key="m"
          :data-testid="`metric-${m}`"
          @click="selectMetric(m)"
        >
          {{ tr(m === "direct" ? "verifiedCost" : m) }}
          <strong :class="{ loss: (book.summary[m] ?? 0) < 0 }">
            {{
              m === "pending"
                ? book.summary[m]
                : book.summary[m] === null
                  ? tr("unknown")
                  : money(book.summary[m])
            }}
          </strong>
        </button>
      </div>
      <div class="ops-actions">
        <button v-for="k in createKinds" :key="k" :data-testid="`new-${k}`" @click="open(k)">
          {{ tr(k) }} +
        </button>
      </div>
      <p v-if="notice" role="status">
        {{ notice }}
      </p>
      <entry-editor
        v-if="editor && pid"
        :key="editor.kind + editor.action + (editor.entry?.id || '')"
        :pid="pid"
        :book="book"
        v-bind="editor"
        @saved="saved"
        @close="editor = undefined"
      />
      <div class="ops-panel">
        <div class="ops-line">
          <h3>{{ tr("entries") }}</h3>
          <select v-model="filter" :aria-label="tr('filter')">
            <option value="">
              {{ tr("all") }}
            </option>
            <option v-for="(_, k) in fields" :key="k" :value="k">
              {{ tr(k) }}
            </option>
            <option v-for="m in metrics" :key="m" :value="m">
              {{ tr(m) }}
            </option>
            <option
              v-for="e in book.entries.filter(r => r.kind === 'contract')"
              :key="e.id"
              :value="e.id"
            >
              {{ caption(e) }}
            </option>
          </select>
          <input v-model="query" :placeholder="tr('search')">
        </div>
        <div v-if="!rows.length">
          {{ tr("empty") }}
        </div>
        <div v-else class="ops-scroll">
          <table>
            <thead>
              <tr>
                <th>{{ tr("title") }}</th>
                <th>{{ tr("kind") }}</th>
                <th>{{ tr("day") }}</th>
                <th>{{ tr("amount") }}</th>
                <th>{{ tr("status") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in rows" :key="e.id">
                <td>
                  <button class="link" @click="pick(e.id)">
                    {{ caption(e) }}
                  </button>
                </td>
                <td>{{ tr(e.kind) }}</td>
                <td>{{ e.data.day || e.data.signed_date || e.data.due || "—" }}</td>
                <td>
                  {{
                    money(
                      Number(
                        e.data.amount ?? e.data.gross ?? e.data.direct ?? e.data.remaining ?? NaN,
                      )
                        || (e.data.remaining === 0 || e.data.direct === 0 || e.data.gross === 0
                          ? 0
                          : null),
                    )
                  }}
                </td>
                <td>{{ tr(e.status) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <article v-if="current" class="ops-panel" data-testid="entry-detail">
        <h3>{{ caption(current) }} · v{{ current.revision }}</h3>
        <dl>
          <template v-for="key in fields[current.kind]" :key="key">
            <dt>{{ tr(key) }}</dt>
            <dd>
              <template
                v-if="
                  current.data[key]
                    && ['work_id', 'proof_file_id', 'signed_doc', 'acceptance_doc'].includes(key)
                "
              >
                <button class="link" @click="openEvidence(current, key)">
                  {{ tr(key === "work_id" ? "openWork" : "preview") }}
                </button>
                <button
                  v-if="key !== 'work_id'"
                  class="link"
                  @click="openEvidence(current, key, true)"
                >
                  {{ tr("download") }}
                </button>
              </template>
              <template v-else>
                {{ value(key, current.data[key], current) }}
              </template>
            </dd>
          </template>
          <template v-if="current.updated_by">
            <dt>{{ tr("changedBy") }}</dt>
            <dd>
              {{ book.people[current.updated_by] }} ·
              {{ current.updated_at ? new Date(current.updated_at).toLocaleString() : "" }}
            </dd>
          </template>
          <dt>{{ tr("createdBy") }}</dt>
          <dd>{{ book.people[current.created_by] }}</dd>
          <dt>{{ tr("verifiedBy") }}</dt>
          <dd>
            {{ current.verified_by ? book.people[current.verified_by] : "—" }}
            {{ current.verified_at ? new Date(current.verified_at).toLocaleString() : "" }}
          </dd>
          <template v-if="book.summary.contracts[current.id]">
            <dt>{{ tr("outstanding") }}</dt>
            <dd>{{ money(book.summary.contracts[current.id].outstanding) }}</dd>
            <dt>{{ tr("unscheduled") }}</dt>
            <dd>{{ money(book.summary.contracts[current.id].unscheduled) }}</dd>
          </template>
          <template v-if="book.summary.installments[current.id]">
            <dt>{{ tr("balance") }}</dt>
            <dd>
              {{ money(book.summary.installments[current.id].balance) }}
              {{ book.summary.installments[current.id].conditional ? tr("conditional") : "" }}
            </dd>
            <dt>{{ tr("overdue") }}</dt>
            <dd>{{ money(book.summary.installments[current.id].overdue) }}</dd>
          </template>
        </dl>
        <div class="ops-actions">
          <button @click="showHistory(current.id)">
            {{ tr("history") }}
          </button>
          <template v-if="canEdit(current)">
            <button @click="editor = { entry: current, kind: current.kind, action: 'save' }">
              {{ tr("edit") }}
            </button>
            <button
              v-if="book.role === 'finance' || current.status !== 'verified'"
              @click="editor = { entry: current, kind: current.kind, action: 'void' }"
            >
              {{ tr("void") }}
            </button>
          </template>
          <template
            v-if="
              book.role === 'finance'
                && current.kind === 'cost'
                && ['pending', 'returned'].includes(current.status)
            "
          >
            <button @click="editor = { entry: current, kind: current.kind, action: 'verify' }">
              {{ tr("verify") }}
            </button>
            <button @click="editor = { entry: current, kind: current.kind, action: 'return' }">
              {{ tr("return") }}
            </button>
          </template>
        </div>
        <pre v-if="preview" class="whitespace-pre-wrap">{{ preview }}</pre>
        <details v-for="h in history" :key="h.after.revision">
          <summary>
            v{{ h.after.revision }} · {{ h.actor }} · {{ new Date(h.at).toLocaleString() }} ·
            {{ h.reason || tr("created") }}
          </summary>
          <dl>
            <dt>{{ tr("status") }}</dt>
            <dd>{{ h.before ? `${tr(h.before.status)} → ` : "" }}{{ tr(h.after.status) }}</dd>
            <template v-for="key in fields[current.kind]" :key="key">
              <dt>{{ tr(key) }}</dt>
              <dd>
                {{ h.before ? `${value(key, h.before.data[key])} → ` : ""
                }}{{ value(key, h.after.data[key]) }}
              </dd>
            </template>
          </dl>
        </details>
      </article>
    </template>
  </section>
</template>

<style src="./operations.css"></style>
