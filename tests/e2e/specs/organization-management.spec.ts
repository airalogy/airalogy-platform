import type { Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"
import { selectVisibleOption } from "./fixtures"

const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))
test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_organization", "Uses an isolated single-organization deployment")
test.use({ storageState: { cookies: [], origins: [] } })
test.beforeEach(({ page }) => page.setDefaultTimeout(15000))

async function login(page: Page, account: "owner" | "viewer") {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill(`dev.${account}@airalogy.dev`)
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
}

test("owner can reach management directly and save a one-character name without changing its UID", async ({ page }, testInfo) => {
  await login(page, "owner")
  const status = await (await page.request.get("/api/instance")).json()
  const original = status.organization
  await page.setViewportSize({ width: 1440, height: 980 })
  await page.getByTestId("organization-management-entry").click()
  await expect(page).toHaveURL(/\/organization\/members$/)
  await page.locator('.n-tabs-tab[data-name="lab-settings"]').click()
  const input = page.getByTestId("organization-settings-name").locator("input")
  const uid = page.getByTestId("organization-settings-uid").locator("input")
  await expect(uid).toHaveValue(original.uid)
  await expect(uid).toHaveAttribute("readonly")
  const originalDescription = await page.locator("textarea").first().inputValue()
  let auth: string | undefined
  let updates = 0
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().endsWith(`/organizations/${original.id}`))
      updates++
  })
  try {
    await input.fill(" \t ")
    await page.getByRole("button", { name: zh.page.labs.settingsPage.saveAction, exact: true }).click()
    await expect(page.locator(".n-form-item-feedback__line").first()).toBeVisible()
    expect(updates).toBe(0)
    await input.fill("  研  ")
    const saved = page.waitForResponse(response => response.request().method() === "PUT" && response.url().endsWith(`/organizations/${original.id}`))
    await page.getByRole("button", { name: zh.page.labs.settingsPage.saveAction, exact: true }).click()
    const response = await saved
    auth = (await response.request().allHeaders())["auth-token"]
    expect(response.ok(), await response.text()).toBeTruthy()
    expect(response.request().postDataJSON().name).toBe("研")
    await expect(page.getByTestId("single-lab-identity")).toHaveText("研")
    await page.reload()
    await expect(input).toHaveValue("研")
    await expect(uid).toHaveValue(original.uid)
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({ width, height: 980 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await page.screenshot({ path: testInfo.outputPath(`organization-settings-${width}.png`), fullPage: true })
    }
    const header = page.getByTestId("app-shell-header")
    await header.getByRole("button", { name: zh.common.more, exact: true }).click()
    await page.locator(".n-dropdown-menu").getByText("组织管理", { exact: true }).click()
    await expect(page).toHaveURL(/\/organization\/members$/)
  }
  finally {
    if (auth) {
      const restored = await page.request.put(`/api/organizations/${original.id}`, { headers: { "Auth-Token": auth }, data: { name: original.name, description: originalDescription } })
      expect(restored.ok(), await restored.text()).toBeTruthy()
    }
  }
})

test("ordinary members see their member directory instead of administrator controls", async ({ page }) => {
  await login(page, "viewer")
  const status = await (await page.request.get("/api/instance")).json()
  await page.setViewportSize({ width: 1440, height: 980 })
  // Wait for the authenticated membership request, not just the initial header render.
  await page.goto(`/labs/${status.lab.uid}/members`)
  await expect(page.locator('.n-tabs-tab[data-name="lab-members"]')).toBeVisible()
  await expect(page.getByTestId("organization-management-entry")).toHaveCount(0)
  await expect(page.locator('.n-tabs-tab[data-name="lab-settings"]')).toHaveCount(0)
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 980 })
    await page.getByTestId("app-shell-header").getByRole("button", { name: zh.common.more, exact: true }).click()
    await expect(page.locator(".n-dropdown-menu").getByText("组织管理", { exact: true })).toHaveCount(0)
    await expect(page.getByText(zh.page.singleLabWorkspace.membersAccess, { exact: true }).last()).toBeVisible()
    await page.keyboard.press("Escape")
  }
})

test("organization owner configures an AI model and can remove the saved key", async ({ page }) => {
  await login(page, "owner")
  await page.goto("/organization/settings")
  const card = page.getByTestId("organization-ai-settings")
  const toggle = card.getByRole("switch")
  const field = card.locator('input[type="password"]')
  const save = card.getByRole("button", { name: zh.page.organization.ai.save })
  const testKey = card.getByRole("button", { name: zh.page.organization.ai.test })
  await expect(toggle).toBeVisible()
  if (await toggle.isDisabled()) {
    await expect(card.getByText(zh.page.organization.ai.blocked)).toBeVisible()
    await expect(testKey).toBeDisabled()
    return
  }
  // The provider directory alone is simulated. Saving and read-back use the real API.
  await page.route("**/ai-settings/test", route => route.fulfill({ json: { status: "ok" } }))
  await field.fill("synthetic-browser-config-only")
  await testKey.click()
  await expect(card.getByRole("status")).toHaveText(zh.page.organization.ai.ok)
  await toggle.click()
  await save.click()
  await expect(card.getByRole("status")).toHaveText(zh.page.organization.ai.saved)
  await page.reload()
  await expect(toggle).toBeChecked()
  await expect(field).toHaveValue("")
  await expect(field).toHaveAttribute("placeholder", zh.page.organization.ai.keepKey)
  await toggle.click()
  await card.getByRole("checkbox").click()
  await save.click()
  await expect(card.getByRole("status")).toHaveText(zh.page.organization.ai.saved)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(toggle).not.toBeChecked()
  await expect(field).toHaveAttribute("placeholder", zh.page.organization.ai.enterKey)
})

test("privately invite a member who chooses their own email and username", async ({ page, browser }) => {
  await login(page, "owner")
  await page.goto("/organization/members")
  await page.getByRole("button", { name: zh.page.instance.inviteMember }).click()
  const modal = page.locator(".n-modal")
  const username = `invite_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`
  await modal.locator("input").first().fill(username)
  const createResponse = page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/instance/invitations"))
  await modal.getByRole("button", { name: zh.page.instance.createInvite }).click()
  const created = await createResponse
  expect(created.ok(), await created.text()).toBeTruthy()
  const invite = await created.json()
  expect(invite.email).toBe("")
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  try {
    const recipient = await context.newPage()
    await recipient.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await recipient.goto(invite.url)
    await expect(recipient.getByRole("button", { name: zh.page.instance.signInToJoin })).toBeVisible()
    await recipient.getByRole("button", { name: zh.page.login.register.confirm }).click()
    const common = zh.page.login.common
    await recipient.getByPlaceholder(common.emailPlaceholder).fill(`${username}@example.org`)
    await recipient.getByPlaceholder(common.displayNamePlaceholder).fill("邀请验收")
    await recipient.getByPlaceholder(common.usernamePlaceholder).fill(username)
    await recipient.getByPlaceholder(common.passwordPlaceholder, { exact: true }).fill("MemberPass123!")
    await recipient.getByPlaceholder(common.confirmPasswordPlaceholder, { exact: true }).fill("MemberPass123!")
    const signup = recipient.waitForResponse(r => r.url().endsWith("/signup") && r.request().method() === "POST")
    await recipient.getByRole("button", { name: zh.page.login.register.confirm }).click()
    const saved = await signup
    expect(saved.ok(), await saved.text()).toBeTruthy()
    await recipient.goto(invite.url)
    await expect(recipient.getByText(zh.page.instance.invitationInvalid)).toBeVisible()
    await modal.getByText(zh.page.instance.inviteHistory, { exact: true }).click()
    const entry = modal.getByRole("listitem").filter({ hasText: username })
    await expect(entry).toContainText(zh.page.instance.inviteStates.claimed)
    await expect(entry).toContainText(`· ${username}`)
  }
  finally {
    await context.close()
  }
})

test("invitation preview preserves the link and administrators can revoke it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, "owner")
  await page.goto("/organization/members")
  await page.getByRole("button", { name: zh.page.instance.inviteMember }).click()
  const modal = page.locator(".n-modal")
  const note = `撤销验收_${crypto.randomUUID().slice(0, 8)}`
  await modal.locator("input").first().fill(note)
  const creation = page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/instance/invitations"))
  await modal.getByRole("button", { name: zh.page.instance.createInvite }).click()
  const invite = await (await creation).json()
  await page.goto(invite.url)
  await expect(page.getByRole("button", { name: /dev_owner/ })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("button", { name: /dev_owner/ })).toBeVisible()
  await page.goto("/organization/members")
  await page.getByRole("button", { name: zh.page.instance.inviteMember }).click()
  await modal.getByText(zh.page.instance.inviteHistory, { exact: true }).click()
  const entry = modal.getByRole("listitem").filter({ hasText: note })
  await expect(entry).toContainText(zh.page.instance.inviteStates.pending)
  await entry.getByRole("button", { name: zh.page.instance.revokeInvite }).click()
  await page.locator(".n-popconfirm__action").getByRole("button").last().click()
  await expect(entry).toContainText(zh.page.instance.inviteStates.revoked)
  await page.goto(invite.url)
  await expect(page.getByText(zh.page.instance.invitationInvalid)).toBeVisible()
})

for (const width of [1440, 390]) {
  test(`invite consecutive people from the same panel at ${width}px`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 844 })
    await login(page, "owner")
    await page.goto("/organization/members")
    await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(page.url()).origin })
    await page.getByRole("button", { name: zh.page.instance.inviteMember }).click()
    const modal = page.locator(".n-modal")
    const form = modal.locator("form")
    const note = form.locator("input").first()
    const role = form.locator(".n-base-selection")
    await expect(role).toHaveCount(2)
    const defaultRoles = await role.allTextContents()
    const first = `连续邀请_${crypto.randomUUID().slice(0, 8)}`
    const second = `${first}_2`
    const email = `${crypto.randomUUID()}@example.org`
    await note.fill(first)
    for (const field of await role.all()) {
      await field.click()
      await selectVisibleOption(page, zh.role.manager)
    }
    await form.locator("input").last().fill(email)
    const create = modal.getByRole("button", { name: zh.page.instance.createInvite, exact: true })
    const link = modal.locator("textarea")
    await create.click()
    await expect(link).toBeVisible()
    const firstUrl = await link.inputValue()
    await expect(modal.getByText(email, { exact: true })).toBeVisible()
    await modal.getByRole("button", { name: zh.page.instance.copyInviteLink }).click()
    expect(await page.evaluate(() => navigator.clipboard.readText()) === firstUrl).toBe(true)
    const next = modal.getByRole("button", { name: zh.page.instance.inviteNext })
    await expect(next).toBeInViewport()
    await next.click()
    await expect(note).toBeFocused()
    await expect(note).toHaveValue("")
    await expect(role).toHaveText(defaultRoles)
    await expect(form.getByRole("checkbox")).not.toBeChecked()
    await expect(link).toHaveCount(0)
    await note.fill(second)
    await create.click()
    await expect(link).toBeVisible()
    const secondUrl = await link.inputValue()
    expect(secondUrl !== firstUrl).toBe(true)
    for (const url of [firstUrl, secondUrl]) {
      const preview = await page.request.get(`/api/instance/invitations/${new URL(url).searchParams.get("token")}`)
      expect(preview.status()).toBe(200)
      expect((await preview.json()).email).toBe(url === firstUrl ? email : "")
    }
    await modal.getByText(zh.page.instance.inviteHistory, { exact: true }).click()
    for (const person of [first, second]) {
      const row = modal.getByRole("listitem").filter({ has: page.getByText(person, { exact: true }) })
      await expect(row).toContainText(zh.page.instance.inviteStates.pending)
    }
  })
}
