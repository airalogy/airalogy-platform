<script setup lang="ts">
import type { Metric, PortfolioRow } from "@/service/api/project-operations"
import { money, readOps } from "@/service/api/project-operations"
import { useOrProvideLabInfoStore } from "../labs/hooks/useLabsInfoStore"
import { useOpsText } from "./fields"

const { labInfo } = useOrProvideLabInfoStore(null)
const tr = useOpsText()
const org = computed(() => labInfo.value?.id)
const rows = ref<PortfolioRow[]>([])
const error = ref("")
const ready = ref(false)
const who = ref("")
const flag = ref("")
const expanded = ref("")
const asOf = ref("")
const metrics: Metric[] = ["gross", "received", "paid", "net_cash", "overdue", "direct", "profit"]
watch(
  [org, asOf],
  async ([id, day], _, cleanup) => {
    let active = true
    cleanup(() => {
      active = false
    })
    rows.value = []
    ready.value = false
    error.value = ""
    expanded.value = ""
    if (!id)
      return
    try {
      const result = await readOps<{ projects: PortfolioRow[] }>(
        `/organizations/${id}/overview`,
        day ? { as_of: day } : {},
      )
      if (active) {
        rows.value = result.projects
        ready.value = true
      }
    }
    catch {
      if (active)
        error.value = tr("unavailable")
    }
  },
  { immediate: true },
)
const owners = computed(() => [
  ...new Map(rows.value.filter(r => r.owner).map(r => [r.owner!.id, r.owner!.name])).entries(),
])
const filtered = computed(() =>
  rows.value.filter(
    r =>
      (!who.value || r.owner?.id === who.value)
      && (!flag.value
        || {
          advance: r.summary.net_cash < 0,
          late: r.summary.overdue > 0,
          loss: r.summary.profit !== null && r.summary.profit < 0,
          needsCheck: r.summary.needs_review,
          unknown: r.summary.profit === null,
        }[flag.value]),
  ),
)
const known = computed(() => filtered.value.filter(r => r.summary.profit !== null))
const knownProfit = computed(() => known.value.reduce((s, r) => s + r.summary.profit!, 0))
function link(r: PortfolioRow, metric?: string) {
  return {
    path: r.href,
    query: { ...(metric ? { metric } : {}), ...(asOf.value ? { as_of: asOf.value } : {}) },
  }
}
</script>

<template>
  <section class="ops" data-testid="operations-overview">
    <h2>{{ tr("overview") }}</h2>
    <p v-if="error" role="alert">
      {{ error }}
    </p>
    <template v-else-if="ready">
      <div class="ops-line">
        <label>
          {{ tr("owner") }}
          <select v-model="who">
            <option value="">{{ tr("all") }}</option>
            <option v-for="[id, name] in owners" :key="id" :value="id">{{ name }}</option>
          </select>
        </label>
        <label>
          {{ tr("exception") }}
          <select v-model="flag">
            <option value="">{{ tr("all") }}</option>
            <option
              v-for="k in ['advance', 'late', 'loss', 'needsCheck', 'unknown']"
              :key="k"
              :value="k"
            >
              {{ tr(k) }}
            </option>
          </select>
        </label>
        <label>
          {{ tr("overdueDate") }}
          <input v-model="asOf" type="date">
        </label>
      </div>
      <details data-testid="ops-coverage">
        <summary>
          {{ tr("profit") }}
          <strong>{{ known.length ? money(knownProfit) : "—" }}</strong>
          · {{ tr("coverage") }} {{ known.length }} / {{ filtered.length }} · {{ tr("unknown") }}
          {{ filtered.length - known.length }}
        </summary>
        <div class="ops-line">
          <router-link v-for="r in filtered" :key="r.id" :to="link(r, 'profit')">
            {{ r.name }} · {{ r.summary.profit === null ? tr("unknown") : money(r.summary.profit) }}
          </router-link>
        </div>
      </details>
      <p v-if="!filtered.length">
        {{ tr("emptyProjects") }}
      </p>
      <div v-else class="ops-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ tr("project") }}</th>
              <th>{{ tr("owner") }}</th>
              <th v-for="m in metrics" :key="m">
                {{ tr(m === "direct" ? "verifiedCost" : m) }}
              </th>
              <th>{{ tr("estimateDate") }}</th>
              <th>{{ tr("verifiedThrough") }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in filtered" :key="r.id">
              <tr>
                <td>
                  <button
                    class="link"
                    :aria-expanded="expanded === r.id"
                    @click="expanded = expanded === r.id ? '' : r.id"
                  >
                    {{ expanded === r.id ? "▾" : "▸" }} {{ r.name }}
                  </button>
                </td>
                <td>{{ r.owner?.name || "—" }}</td>
                <td v-for="m in metrics" :key="m">
                  <router-link :to="link(r, m)" :class="{ loss: (r.summary[m] ?? 0) < 0 }">
                    {{ r.summary[m] === null ? tr("unknown") : money(r.summary[m]) }}
                  </router-link>
                </td>
                <td>{{ r.summary.estimate_date || "—" }}</td>
                <td>{{ r.summary.verified_through || "—" }}</td>
              </tr>
              <tr v-if="expanded === r.id">
                <td colspan="11">
                  <div class="ops-line">
                    <router-link :to="link(r)">
                      {{ tr("book") }}
                    </router-link>
                    <router-link v-for="c in r.contracts" :key="c.id" :to="link(r, c.id)">
                      {{ c.title }} · {{ tr("outstanding") }}
                      {{ money(r.summary.contracts[c.id].outstanding) }}
                    </router-link>
                    <router-link :to="link(r, 'shared')">
                      {{ tr("shared") }} {{ money(r.summary.shared) }}
                    </router-link>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </template>
    <p v-else role="status">
      {{ tr("loading") }}
    </p>
  </section>
</template>

<style src="./operations.css"></style>
