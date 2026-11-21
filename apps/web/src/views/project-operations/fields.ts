import type { Kind } from "@/service/api/project-operations"
import { useI18n } from "vue-i18n"

export const fields: Record<Kind, string[]> = {
  contract: [
    "title",
    "customer",
    "number",
    "state",
    "gross",
    "net",
    "agreement_date",
    "signed_date",
    "terms",
    "signed_doc",
    "work_id",
    "acceptance_date",
    "acceptance_doc",
  ],
  installment: ["contract_id", "title", "amount", "condition", "due", "work_id"],
  cost: ["title", "day", "category", "days", "rate", "direct", "payable", "contract_id"],
  cash: [
    "direction",
    "receipt_purpose",
    "title",
    "day",
    "amount",
    "contract_id",
    "installment_id",
    "cost_id",
    "proof_file_id",
  ],
  forecast: ["day", "remaining", "basis"],
  closing: ["day", "basis"],
}
export const amountFields = new Set([
  "gross",
  "net",
  "amount",
  "rate",
  "direct",
  "payable",
  "remaining",
])
export const dateFields = new Set([
  "day",
  "agreement_date",
  "signed_date",
  "acceptance_date",
  "due",
])
export const enums: Record<string, string[]> = {
  direction: ["in", "out"],
  receipt_purpose: ["customer_receipt", "other_income"],
  state: ["draft", "signed"],
  category: ["labor", "subcontract", "material", "cloud", "travel", "other"],
}
export const textFields = new Set(["number", "terms", "condition"])
export const mandatory = new Set([
  "title",
  "customer",
  "state",
  "gross",
  "amount",
  "day",
  "category",
  "direct",
  "direction",
  "basis",
])
export function useOpsText() {
  const { t } = useI18n()
  return (key: string) => t(`page.operations.${key}` as I18n.I18nKey)
}
