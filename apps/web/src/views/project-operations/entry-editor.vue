<script setup lang="ts">
import type {
  Book,
  Choices,
  DocRef,
  Entry,
  EntryData,
  Kind,
} from "@/service/api/project-operations"
import { readOps, toFen, writeOps } from "@/service/api/project-operations"
import {
  amountFields,
  dateFields,
  enums,
  fields,
  mandatory,
  textFields,
  useOpsText,
} from "./fields"

const props = defineProps<{
  pid: string
  book: Book
  kind: Kind
  entry?: Entry
  action: "save" | "return" | "void" | "verify"
}>()
const emit = defineEmits<{ saved: [], close: [] }>()
const tr = useOpsText()
const entryId = props.entry?.id ?? crypto.randomUUID()
const revision = ref(props.entry?.revision ?? 0)
const reason = ref("")
const form = reactive<Record<string, string>>({})
for (const key of fields[props.kind]) {
  const v = props.entry?.data[key]
  if (v != null) {
    form[key]
      = typeof v === "object"
        ? `${v.id}:${v.version}`
        : amountFields.has(key)
          ? (Number(v) / 100).toFixed(2)
          : String(v)
  }
  else {
    form[key] = key === "receipt_purpose"
      ? ""
      : enums[key]?.[0] ?? ""
  }
}
const choices = ref<Choices>({ work: [], documents: [], files: [] })
const error = ref("")
const busy = ref(false)
const latest = ref<Entry>()
const conflict = ref(false)
onMounted(async () => {
  if (props.action !== "save")
    return
  try {
    choices.value = await readOps<Choices>(`/projects/${props.pid}/sources`)
  }
  catch {
    error.value = tr("sourceFailed")
  }
})
function options(key: string): { value: string, label: string }[] | undefined {
  if (enums[key])
    return enums[key].map(value => ({ value, label: tr(value) }))
  if (key === "signed_doc" || key === "acceptance_doc") {
    return choices.value.documents.map(d => ({
      value: `${d.id}:${d.version}`,
      label: `${d.title} · v${d.version}`,
    }))
  }
  if (key === "work_id" || key === "proof_file_id") {
    return choices.value[key === "work_id" ? "work" : "files"].map(s => ({
      value: s.id,
      label: s.title,
    }))
  }
  const kind = { contract_id: "contract", installment_id: "installment", cost_id: "cost" }[key]
  if (kind) {
    return props.book.entries
      .filter(
        e =>
          e.kind === kind
          && e.status !== "void"
          && (key !== "installment_id"
            || !form.contract_id
            || e.data.contract_id === form.contract_id),
      )
      .map(e => ({ value: e.id, label: String(e.data.title) }))
  }
}
const visible = computed(() =>
  fields[props.kind].filter((k) => {
    if (["days", "rate"].includes(k))
      return form.category === "labor"
    if (props.kind !== "cash")
      return true
    if (k === "receipt_purpose")
      return form.direction === "in"
    if (k === "installment_id" || k === "contract_id")
      return form.direction === "in" && form.receipt_purpose !== "other_income"
    return k !== "cost_id" || form.direction === "out"
  }),
)
const calculatedLabor = computed(() => {
  if (props.kind !== "cost" || form.category !== "labor" || !form.days || !form.rate)
    return undefined
  try {
    const days = BigInt(toFen(form.days))
    const cents = (days * BigInt(toFen(form.rate)) + 50n) / 100n
    return cents <= 999999999999n ? (Number(cents) / 100).toFixed(2) : undefined
  }
  catch {
    return undefined
  }
})
watch(
  calculatedLabor,
  (amount) => {
    if (amount !== undefined)
      form.direct = amount
  },
  { immediate: true },
)
watch(
  () => form.contract_id,
  (id) => {
    if (
      props.kind === "cash"
      && id
      && form.installment_id
      && !props.book.entries.some(e => e.id === form.installment_id && e.data.contract_id === id)
    ) {
      form.installment_id = ""
    }
  },
)
function content() {
  const data: EntryData = { kind: props.kind }
  for (const key of visible.value) {
    const v = form[key]?.trim()
    if (!v) {
      if (key === "payable")
        data[key] = 0
      else if (textFields.has(key))
        data[key] = ""
      else data[key] = null
    }
    else if (amountFields.has(key)) {
      data[key] = toFen(v)
    }
    else if (key.endsWith("_doc")) {
      const [id, version] = v.split(":")
      data[key] = { id, version: Number(version) } satisfies DocRef
    }
    else {
      data[key] = v
    }
  }
  return data
}
let lastBody = ""
let requestId = ""
async function save() {
  if (busy.value)
    return
  error.value = ""
  busy.value = true
  try {
    const body = {
      entry_id: entryId,
      expected_revision: revision.value,
      action: props.action,
      reason: reason.value,
      data: props.action === "save" ? content() : null,
    }
    const serialized = JSON.stringify(body)
    if (serialized !== lastBody) {
      requestId = crypto.randomUUID()
      lastBody = serialized
    }
    await writeOps(`/projects/${props.pid}/entries`, { ...body, request_id: requestId }, "POST")
    emit("saved")
  }
  catch (e: any) {
    if (e.response?.status === 409) {
      conflict.value = true
      error.value = tr("conflict")
      latest.value = (await readOps<Book>(`/projects/${props.pid}`)).entries.find(
        r => r.id === entryId,
      )
    }
    else {
      error.value = e.message === "amount" ? tr("badAmount") : tr("invalid")
    }
  }
  finally {
    busy.value = false
  }
}
function compareDone() {
  if (!latest.value)
    return
  revision.value = latest.value.revision
  conflict.value = false
  error.value = ""
}
</script>

<template>
  <form class="ops-panel" data-testid="ops-editor" @submit.prevent="save">
    <h3>{{ tr(action) }} · {{ tr(kind) }}</h3>
    <p v-if="kind === 'cash' && action === 'save'" class="text-secondary text-sm">
      {{ tr("cashHint") }}
    </p>
    <div v-if="action === 'save'" class="ops-grid">
      <label v-for="key in visible" :key="key">
        {{ tr(key) }}
        <select
          v-if="options(key)"
          v-model="form[key]"
          :data-testid="`field-${key}`"
          :required="mandatory.has(key) || (key === 'receipt_purpose' && !entry) || (key === 'contract_id' && kind === 'installment')"
        >
          <option value="">—</option>
          <option v-for="o in options(key)" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <input
          v-else
          v-model="form[key]"
          :data-testid="`field-${key}`"
          :type="dateFields.has(key) ? 'date' : 'text'"
          :readonly="key === 'direct' && calculatedLabor !== undefined"
          :inputmode="amountFields.has(key) || key === 'days' ? 'decimal' : undefined"
          :required="mandatory.has(key) || (key === 'signed_date' && form.state === 'signed')"
        >
      </label>
    </div>
    <label v-if="entry && action !== 'verify'">
      {{ tr("reason") }}
      <input v-model="reason" required>
    </label>
    <p v-if="error" role="alert" class="notice">
      {{ error }}
    </p>
    <template v-if="conflict && latest">
      <dl>
        <template v-for="(v, k) in latest.data" :key="k">
          <dt>{{ tr(String(k)) }}</dt>
          <dd>
            {{
              typeof v === "object" && v
                ? `${v.id} · v${v.version}`
                : amountFields.has(String(k)) && typeof v === "number"
                  ? (v / 100).toFixed(2)
                  : (v ?? "—")
            }}
          </dd>
        </template>
      </dl>
      <button type="button" @click="compareDone">
        {{ tr("compareDone") }} · v{{ latest.revision }}
      </button>
    </template>
    <div class="ops-actions">
      <button class="primary" type="submit" :disabled="busy || conflict">
        {{ tr("confirm") }}
      </button>
      <button type="button" @click="emit('close')">
        {{ tr("cancel") }}
      </button>
    </div>
  </form>
</template>
