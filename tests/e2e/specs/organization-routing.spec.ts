import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

// Real local API/account permissions; override only the deployment presentation contract.
// This also proves that a multi-organization site with one visible organization keeps /orgs.
test.use({ storageState: { cookies: [], origins: [] } })

for (const mode of ["single_organization", "single_lab", "community"] as const) {
  test(`${mode}: old project bookmarks, generated links, reload and management preserve context`, async ({ page }, testInfo) => {
    const single = mode !== "community"
    await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await page.route("**/api/instance", async (route) => {
      const response = await route.fetch()
      const status = await response.json()
      const organization = status.organization ?? status.lab ?? { ...(await loadFixtures()).lab, name: "Synthetic route organization", organization_type: "company" }
      await route.fulfill({ response, json: {
        ...status,
        deployment_mode: mode,
        single_lab: single,
        single_organization: single,
        default_organization_uid: single ? "dev_lab" : "",
        organization: single ? organization : null,
        lab: single ? organization : null,
      } })
    })
    const failures: string[] = []
    page.on("pageerror", error => failures.push(error.message))
    const visit = async (navigate: () => Promise<unknown>, section: string) => {
      const saved = page.waitForResponse(response => response.url().endsWith("/api/workspace/project-visits") && response.ok() && response.request().postDataJSON()?.section === section)
      await navigate()
      await saved
    }
    const base = single ? "/projects/quickstart" : "/orgs/dev_lab/projects/quickstart"
    await page.goto("/labs/dev_lab/projects/quickstart/documents?read_context=synthetic#result")
    await expect(page).toHaveURL(/\/login\?redirect=/)
    expect(new URL(page.url()).searchParams.get("redirect")).toBe(`${base}/documents?read_context=synthetic#result`)
    await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
    await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
    const signedIn = page.waitForResponse(response => response.url().endsWith("/api/signin_by_email") && response.ok())
    const loadedProject = page.waitForResponse(response => response.url().includes("/api/projects/by_uid?") && response.ok())
    await page.getByTestId("login-submit").click()
    const projectName = (await (await loadedProject).json()).name as string
    const headers = { "Auth-Token": (await (await signedIn).json()).token }
    await expect(page).toHaveURL(`${base}/documents?read_context=synthetic#result`)
    await expect(page.getByRole("heading", { name: projectName, exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { name: projectName, exact: true })).toBeVisible()
    await visit(() => page.locator(".n-tabs-tab[data-name=\"project-protocols\"]").click(), "protocols")
    await expect(page).toHaveURL(`${base}/protocols`)
    await visit(() => page.locator(".n-tabs-tab[data-name=\"project-overview\"]").click(), "overview")
    await expect(page).toHaveURL(`${base}/overview`)
    await visit(() => page.goBack(), "protocols")
    await expect(page).toHaveURL(`${base}/protocols`)
    await visit(() => page.goForward(), "overview")
    await expect(page).toHaveURL(`${base}/overview`)
    await page.goto("/home")
    const card = page.getByTestId("home-project-card").filter({ hasText: projectName })
    await expect(card).toBeVisible()
    await expect(card.getByTestId("home-resume-project")).toHaveAttribute("href", `${base}/overview`)
    await card.getByTestId("home-resume-project").click()
    await expect(page).toHaveURL(`${base}/overview`)
    await page.goto("/labs/dev_lab/members")
    await expect(page).toHaveURL(single ? "/organization/members" : "/orgs/dev_lab/members")
    await page.locator(".n-tabs-tab[data-name=\"lab-settings\"]").click()
    await expect(page).toHaveURL(single ? "/organization/settings" : "/orgs/dev_lab/settings")
    await page.reload()
    await expect(page.getByTestId("organization-settings-uid").locator("input")).toHaveValue("dev_lab")
    await page.setViewportSize({ width: 390, height: 900 })
    await page.goto(`${base}/overview`)
    await expect(page.getByRole("heading", { name: projectName, exact: true })).toBeVisible()
    await expect(page.locator(".n-spin-body")).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`${mode}-project-mobile.png`), fullPage: true, animations: "disabled" })
    // Read existing synthetic assets only: no Record writes or Protocol publication.
    await page.setViewportSize({ width: 1440, height: 980 })
    const listing = await page.request.get("/api/protocols?lab_uid=dev_lab&project_uid=quickstart&page_size=100", { headers })
    expect(listing.ok()).toBeTruthy()
    const protocol = (await listing.json()).protocols.find((item: { uid: string }) => item.uid === "record_analysis_e2e")
    expect(protocol).toBeTruthy()
    const records = await page.request.get(`/api/protocols/${protocol.id}/records?page_size=1`, { headers })
    expect(records.ok()).toBeTruthy()
    const record = (await records.json()).records[0]
    const legacyProtocol = `/labs/dev_lab/projects/quickstart/protocols/${protocol.uid}`
    await page.goto(`${legacyProtocol}/v${record.metadata.protocol_version}/record/${record.record_id}/v${record.record_version}`)
    await expect(page).toHaveURL(`${base}/protocols/${protocol.uid}/v${record.metadata.protocol_version}/record/${record.record_id}/v${record.record_version}`)
    await expect(page.getByTestId("record-source-version").first()).toContainText(record.metadata.protocol_version)
    await page.goto(`${legacyProtocol}/add`)
    await expect(page.getByTestId("record-save-draft")).toBeVisible()
    expect(new URL(page.url()).pathname).toBe(`${base}/protocols/${protocol.uid}/add`)
    await page.goto(`/labs/dev_lab/projects/quickstart/${protocol.uid}/editor/v${protocol.latest_version}`)
    await expect(page.locator("[data-testid=\"protocol-source-editor\"], [data-testid=\"protocol-visual-editor\"]").first()).toBeVisible({ timeout: 30000 })
    expect(new URL(page.url()).pathname).toBe(`${base}/${protocol.uid}/editor/v${protocol.latest_version}`)
    await expect(page.locator(".n-spin-body")).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath(`${mode}-protocol-editor.png`), animations: "disabled" })
    if (single) {
      await page.goto("/orgs/another_org/projects/quickstart/overview")
      await expect(page).toHaveURL("/404/lab")
      await expect(page.getByRole("heading", { name: projectName, exact: true })).toHaveCount(0)
    }
    expect(failures).toEqual([])
  })
}
