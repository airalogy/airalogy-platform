import type { APIResponse, Browser, Page } from "@playwright/test"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import zh from "../../../packages/shared/src/locales/langs/zh-cn.json" with { type: "json" }

const labels = zh.page.operations
interface Account { key: string, email: string, password: string }
type Input = Record<string, string>

async function check(response: APIResponse) {
  expect(response.ok(), `${new URL(response.url()).pathname}: ${response.status()}`).toBeTruthy()
  return response
}

async function accountPage(browser: Browser, account: Account, mobile = false) {
  const savedSession = account.key === "owner" || account.key === "viewer"
  const page = await browser.newPage({
    baseURL: process.env.E2E_WEB_URL || "http://127.0.0.1:3100",
    storageState: savedSession ? `tests/e2e/.auth/${account.key}.json` : { cookies: [], origins: [] },
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
  })
  page.setDefaultTimeout(15_000)
  page.setDefaultNavigationTimeout(60_000)
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  if (savedSession)
    return page
  await page.goto("/login", { waitUntil: "domcontentloaded" })
  await page.getByTestId("login-email").locator("input").fill(account.email)
  await page.getByTestId("login-password").locator("input").fill(account.password)
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/)
  return page
}

function detail(page: Page) {
  return page.getByTestId("entry-detail")
}
function entry(page: Page, title: string) {
  return page.getByTestId("operations-book").getByRole("button", { name: title, exact: true })
}
async function save(page: Page, fields: Input = {}, reason?: string) {
  const editor = page.getByTestId("ops-editor")
  for (const [name, text] of Object.entries(fields)) {
    const control = editor.getByTestId(`field-${name}`)
    if (name.endsWith("_id"))
      await control.selectOption({ label: text })
    else if (["direction", "receipt_purpose", "state", "category"].includes(name))
      await control.selectOption(text)
    else
      await control.fill(text)
  }
  if (reason)
    await editor.getByLabel(labels.reason).fill(reason)
  const saved = page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/entries"))
  await editor.locator("button[type=\"submit\"]").click()
  const response = await saved
  expect(response.ok(), `ledger save: ${response.status()}`).toBeTruthy()
  await expect(editor).toBeHidden()
  await expect(page.getByTestId("operations-book").getByText(labels.saved, { exact: true })).toBeVisible()
  return response.request().postDataJSON()
}
async function create(page: Page, kind: string, fields: Input) {
  await page.getByTestId(`new-${kind}`).click()
  return save(page, fields)
}
async function edit(page: Page, title: string, fields: Input, reason: string) {
  await entry(page, title).click()
  await detail(page).getByRole("button", { name: labels.edit, exact: true }).click()
  return save(page, fields, reason)
}
async function verify(page: Page, title: string) {
  await page.reload({ waitUntil: "domcontentloaded" })
  await entry(page, title).click()
  await detail(page).getByRole("button", { name: labels.verify, exact: true }).click()
  await save(page)
}
async function amounts(page: Page, expected: Record<string, number | null>) {
  const cny = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" })
  for (const [metric, value] of Object.entries(expected)) {
    await expect(page.getByTestId(`metric-${metric}`).locator("strong"))
      .toHaveText(value === null ? labels.unknown : cny.format(value))
  }
}

test("the instrument project goes from its first purchase to management review and revocation", async ({ browser, request }) => {
  test.setTimeout(240_000)
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const fixture = await (await check(await request.post(`${api}/dev/fixtures/quickstart`))).json()
  const account = (key: string): Account => fixture.accounts.find((a: Account) => a.key === key)
  const sessions = await Promise.all(["owner", "collaborator", "viewer"].map(async (key) => {
    const { email, password } = account(key)
    return (await check(await request.post(`${api}/signin_by_email`, { data: { email, password } }))).json()
  }))
  const [owner, financeUser, manager] = sessions
  const headers = { "Auth-Token": owner.token }
  const uid = `ops_${randomUUID().replaceAll("-", "").slice(0, 12)}`
  const guest = { key: "client", email: `${uid}@example.org`, password: account("viewer").password }
  const signup = await check(await request.post(`${api}/signup`, { data: {
    username: uid,
    email: guest.email,
    password: guest.password,
    confirm_password: guest.password,
    name: "虚构项目客户",
  } }))
  const clientUser = (await signup.json()).user
  await check(await request.post(`${api}/labs/${fixture.lab.id}/users`, { headers, data: { user_id: clientUser.id, role: 3 } }))
  const project = await (await check(await request.post(`${api}/projects`, {
    headers,
    data: { uid, name: `虚构验收 · 仪器数据接入 ${uid}`, type: 1, lab_id: fixture.lab.id },
  }))).json()
  for (const [userId, role] of [[financeUser.user.id, 30], [manager.user.id, 60], [clientUser.id, 60]]) {
    await check(await request.post(`${api}/projects/${project.id}/users`, { headers, data: { user_id: userId, role } }))
  }
  const apiOrg = `${api}/project-operations/organizations/${fixture.lab.id}`
  const status = await (await check(await request.get(`${apiOrg}/access`, { headers }))).json()
  if (!status.enabled)
    await check(await request.put(apiOrg, { headers, data: { enabled: true, expected_revision: status.revision } }))
  const apiBook = `${api}/project-operations/projects/${project.id}`
  const org = `/orgs/${fixture.lab.uid}`
  const book = `${org}/projects/${uid}/operations`
  const overview = `${org}/operations`
  const lead = await accountPage(browser, account("owner"))
  const finance = await accountPage(browser, account("collaborator"))
  const ceo = await accountPage(browser, account("viewer"), true)
  const client = await accountPage(browser, guest)
  try {
    const settings = lead.getByTestId("ops-settings")
    async function openSettings() {
      await lead.goto(`${org}/settings`, { waitUntil: "domcontentloaded" })
      await settings.getByLabel(labels.project, { exact: true }).selectOption(project.id)
    }
    async function saveGrants() {
      await settings.getByRole("button", { name: labels.saveAccess }).click()
      await expect(settings.getByRole("status")).toHaveText(labels.saved)
    }
    await lead.goto(book, { waitUntil: "domcontentloaded" })
    await lead.getByRole("link", { name: labels.orgSettings, exact: true }).click()
    await expect(settings.getByLabel(labels.project, { exact: true })).toHaveValue(project.id)
    await settings.getByRole("checkbox").check()
    await settings.getByLabel(/@dev_owner/).selectOption("lead")
    await settings.getByLabel(/@dev_collaborator/).selectOption("finance")
    await settings.getByLabel(/@dev_viewer/).selectOption("viewer")
    await saveGrants()
    await Promise.all([lead.goto(book, { waitUntil: "domcontentloaded" }), finance.goto(book, { waitUntil: "domcontentloaded" })])
    const equipment = "采集设备"
    const cost = { title: equipment, day: "2026-10-30", category: "material", direct: "6000", payable: "6000" }
    const contract = { title: "合同 A", customer: "虚构客户", state: "signed", signed_date: "2026-11-01", gross: "106000", net: "100000" }
    const payment = { title: "设备首付", day: "2026-10-30", direction: "out", amount: "4000", cost_id: equipment }
    await test.step("1. 签约前设备投入与分次付款", async () => {
      await create(lead, "cost", cost)
      await verify(finance, equipment)
      await create(finance, "cash", payment)
      await lead.reload({ waitUntil: "domcontentloaded" })
      await amounts(lead, { gross: 0, direct: 6000, paid: 4000, net_cash: -4000, unpaid: 2000, profit: null })
      await ceo.goto(overview, { waitUntil: "domcontentloaded" })
      await expect(ceo.getByRole("row").filter({ hasText: uid })).toContainText(labels.unknown)
    })
    await test.step("2. 补入合同和预测，保留原成本日期", async () => {
      await create(lead, "contract", contract)
      await edit(lead, equipment, { contract_id: contract.title }, "签约前投入归入 A")
      await create(lead, "forecast", { day: "2026-11-09", remaining: "34000", basis: "剩余实施投入" })
      await finance.reload({ waitUntil: "domcontentloaded" })
      await create(finance, "closing", { day: "2026-11-11", basis: "财务已核实当期成本" })
      await lead.reload({ waitUntil: "domcontentloaded" })
      await amounts(lead, { direct: 6000, profit: 60000 })
      await entry(lead, equipment).click()
      await expect(detail(lead)).toContainText("2026-10-30")
    })
    let receiptRequest: object
    await test.step("3. 匹配实际回款并按日计算逾期", async () => {
      await create(lead, "installment", { contract_id: contract.title, title: "首期", amount: "50000", due: "2026-11-10" })
      await create(lead, "installment", { contract_id: contract.title, title: "尾款", amount: "56000", condition: "客户签回验收单后 30 天" })
      await finance.reload({ waitUntil: "domcontentloaded" })
      receiptRequest = await create(finance, "cash", { title: "首期回款", direction: "in", receipt_purpose: "customer_receipt", day: "2026-11-09", amount: "30000" })
      await amounts(finance, { unmatched: 30000, received: 30000 })
      await edit(finance, "首期回款", { contract_id: contract.title, installment_id: "首期" }, "核销到首期")
      await finance.reload({ waitUntil: "domcontentloaded" })
      await amounts(finance, { unmatched: 0, received: 30000, net_cash: 26000, profit: 60000 })
      await entry(finance, contract.title).click()
      await expect(detail(finance)).toContainText("76,000.00")
      await entry(finance, "尾款").click()
      await expect(detail(finance)).toContainText(labels.conditional)
      for (const [day, overdue] of [["10", 0], ["11", 20000]] as const) {
        await finance.getByLabel(labels.overdueDate).fill(`2026-11-${day}`)
        await amounts(finance, { overdue })
      }
    })
    await test.step("4. 重试同笔到账并支付设备余款", async () => {
      await check(await request.post(`${apiBook}/entries`, { headers: { "Auth-Token": financeUser.token }, data: receiptRequest }))
      await create(finance, "cash", { ...payment, title: "设备尾款", amount: "2000" })
      await finance.reload({ waitUntil: "domcontentloaded" })
      await expect(entry(finance, "首期回款")).toHaveCount(1)
      await amounts(finance, { received: 30000, paid: 6000, unpaid: 0, net_cash: 24000, direct: 6000, profit: 60000 })
    })
    await test.step("5. 第二份合同和项目共用成本", async () => {
      await create(lead, "contract", { ...contract, title: "合同 B", gross: "10000", net: "10000" })
      await create(lead, "cost", { ...cost, title: "共用耗材", day: "2026-11-10", direct: "1000", payable: "1000" })
      await verify(finance, "共用耗材")
      await finance.reload({ waitUntil: "domcontentloaded" })
      await amounts(finance, { gross: 116000, direct: 7000, shared: 1000, net_cash: 24000, profit: 69000 })
    })
    await test.step("6. 管理层追溯，普通成员和撤权后访问受限", async () => {
      await ceo.goto(overview, { waitUntil: "domcontentloaded" })
      const projectButton = ceo.getByRole("button", { name: new RegExp(uid) })
      await projectButton.click()
      const row = ceo.getByRole("row").filter({ has: projectButton })
      await expect(row).toContainText("69,000.00")
      await expect(ceo.getByRole("link", { name: /合同 A.*76,000/ })).toBeVisible()
      await expect(ceo.getByRole("link", { name: /合同 B.*10,000/ })).toBeVisible()
      await ceo.getByRole("link", { name: new RegExp(`${labels.shared}.*1,000`) }).click()
      await expect(entry(ceo, "共用耗材")).toBeVisible()
      await expect(entry(ceo, equipment)).toHaveCount(0)
      await entry(ceo, "共用耗材").click()
      await detail(ceo).getByRole("button", { name: labels.history }).click()
      await expect(detail(ceo).locator("details")).toHaveCount(2)
      await expect(ceo.getByTestId("new-cash")).toHaveCount(0)
      await expect(lead.getByTestId("new-cash")).toHaveCount(0)
      async function denied(page: Page) {
        await page.goto(book, { waitUntil: "domcontentloaded" })
        await expect(page.getByTestId("operations-book").getByRole("alert")).toContainText(labels.bookAccessHint)
        await expect(page.getByTestId("metric-profit")).toHaveCount(0)
        await page.goto(overview, { waitUntil: "domcontentloaded" })
        await expect(page.getByTestId("ops-coverage")).toBeVisible()
        await expect(page.getByRole("button", { name: new RegExp(uid) })).toHaveCount(0)
      }
      await denied(client)
      await openSettings()
      await settings.getByLabel(/@dev_viewer/).selectOption("")
      await saveGrants()
      await denied(ceo)
    })
    await test.step("逾期明细只含选定日及之前的收款", async () => {
      await create(finance, "cash", { title: "后续收款", direction: "in", receipt_purpose: "customer_receipt", day: "2026-11-12", amount: "5000", installment_id: "首期" })
      await finance.getByLabel(labels.overdueDate).fill("2026-11-11")
      await amounts(finance, { overdue: 20000 })
      await finance.getByTestId("metric-overdue").click()
      await expect(entry(finance, "首期")).toBeVisible()
      await expect(entry(finance, "首期回款")).toBeVisible()
      await expect(entry(finance, "后续收款")).toHaveCount(0)
      await finance.getByLabel(labels.overdueDate).fill("2026-11-12")
      await amounts(finance, { overdue: 15000 })
      await expect(entry(finance, "后续收款")).toBeVisible()
    })
    await test.step("手机端从项目导航进入账本并登记其他收入", async () => {
      await finance.setViewportSize({ width: 390, height: 844 })
      await finance.goto(book.replace(/operations$/, "overview"), { waitUntil: "domcontentloaded" })
      await finance.getByTestId("project-more").click()
      await finance.locator(".n-dropdown-option").getByText(labels.book, { exact: true }).click()
      await expect(finance.getByRole("button", { name: labels.addCash })).toBeVisible()
      await create(finance, "cash", { title: "押金退回", direction: "in", receipt_purpose: "other_income", day: "2026-11-13", amount: "125" })
      await finance.reload({ waitUntil: "domcontentloaded" })
      await amounts(finance, { received: 35125, unmatched: 0 })
      await finance.getByRole("button", { name: labels.cashEntries }).click()
      await expect(entry(finance, "押金退回")).toBeVisible()
      await expect(entry(finance, equipment)).toHaveCount(0)
    })
  }
  finally {
    await Promise.all([lead, finance, ceo, client].map(p => p.close()))
  }
})
