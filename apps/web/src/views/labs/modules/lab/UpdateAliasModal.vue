<template>
  <n-form ref="formRef" :model="model" :rules="rules">
    <n-form-item path="alias" :label="props.label">
      <n-input v-model:value="model.alias" :placeholder="props.placeholder" :maxlength="maxlength" :aria-describedby="hint ? hintId : undefined" />
    </n-form-item>
    <p v-if="hint" :id="hintId" class="mt-0 text-sm text-gray-600">{{ hint }}</p>
  </n-form>
</template>

<script setup lang="ts">
import type { FormInst, FormRules } from "naive-ui"
import { useId } from "vue"

const props = withDefaults(defineProps<{
  alias?: string | null
  label?: string
  placeholder?: string
  hint?: string
  maxlength?: number
  requiredMessage?: string
  required?: boolean
}>(), {
  alias: "",
  label: "Alias",
  placeholder: "Enter Alias",
  requiredMessage: "Please enter an alias",
  required: true,
})

const hintId = useId()
const formRef = ref<FormInst | null>(null)

const model = reactive({
  alias: props.alias || "",
})

const rules: FormRules = props.required
  ? {
      alias: {
        required: true,
        message: props.requiredMessage,
        trigger: ["input", "blur"],
      },
    }
  : {}

async function getAlias() {
  await formRef.value?.validate()
  return model.alias
}

defineExpose({
  getAlias,
})
</script>
