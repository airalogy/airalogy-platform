import { Buffer } from "node:buffer"
import { createHash, randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

for (const [locale, width] of [["en-US", 390], ["zh-CN", 1440]] as const) {
  test(`external research: snapshot, report, method, candidate and OAuth (${locale})`, async ({ page, request }, testInfo) => {
    test.setTimeout(240_000)
    const fixtures = await loadFixtures()
    const language = JSON.parse(await readFile(new URL(`../../../packages/shared/src/locales/langs/${locale === "zh-CN" ? "zh-cn" : "en-us"}.json`, import.meta.url), "utf8"))
    const strings = language.externalAccess
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const origin = process.env.E2E_WEB_URL || "http://127.0.0.1:3100"
    const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    const headers = { "Auth-Token": (await signIn.json()).token }
    const policy = await request.get(`${api}/external-access/labs/${fixtures.lab.id}/policy`, { headers })
    const currentPolicy = await policy.json()
    const enabled = await request.put(`${api}/external-access/labs/${fixtures.lab.id}/policy`, { headers, data: { enabled: true, blocked_fields: [], expected_revision: currentPolicy.revision } })
    expect(enabled.ok(), await enabled.text()).toBeTruthy()
    const uid = `synthetic_${randomUUID().replaceAll("-", "")}`
    const files = {
      "protocol.aimd": "# Synthetic measurement\n{{var|value: float, ge=0, le=100}}",
      "protocol.toml": `[airalogy_protocol]\nid="${uid}"\nname="Synthetic external research"\nversion="0.1.0"\n`,
    }
    const published = await request.post(`${api}/protocols`, { headers, multipart: { project_id: fixtures.project.id, file: { name: "synthetic.zip", mimeType: "application/zip", buffer: Buffer.from(zipSync(Object.fromEntries(Object.entries(files).map(([k, v]) => [k, strToU8(v)])))) } } })
    expect(published.ok(), await published.text()).toBeTruthy()
    const protocol = (await published.json()).data
    const issuance = await request.post(`${api}/external-access/grants`, { headers, data: { project_id: fixtures.project.id, name: `Synthetic ${uid}`, expires_in_days: 1, scopes: ["protocols:read", "records:read", "records:export", "records:import", "analysis:read", "analysis:write", "files:read", "protocols:source", "protocols:candidate", "protocols:publish"] } })
    expect(issuance.ok(), await issuance.text()).toBeTruthy()
    const { token } = await issuance.json()
    const delegated = { Authorization: `Bearer ${token}` }
    async function call(name: string, data: object) {
      const response = await request.post(`${api}/external-access/tools/${name}`, { headers: delegated, data })
      expect(response.ok(), await response.text()).toBeTruthy()
      return response.json()
    }
    const imported = await call("preview_import", { protocol_id: protocol.id, csv: "var.value\n2\n4\n", request_key: randomUUID() })
    expect((await request.post(`${api}/external-access/operations/${imported.id}/decision`, { headers, data: { digest: imported.digest, approve: true } })).ok()).toBeTruthy()
    await call("execute_operation", { operation_id: imported.id })
    const snapshot = await call("create_snapshot", { sources: [{ protocol_id: protocol.id, fields: ["value"] }], request_key: randomUUID() })
    const mean = snapshot.items.reduce((sum: number, row: { values: { value: number } }) => sum + row.values.value, 0) / snapshot.items.length
    expect(mean).toBe(3)
    const code = Buffer.from("values = [2, 4]\nprint(sum(values) / len(values))\n")
    const operation = await call("preview_analysis", { snapshot_id: snapshot.snapshot_id, snapshot_digest: snapshot.digest, request_key: randomUUID(), title: `Synthetic mean ${uid}`, question: "Mean?", report: `Mean = ${mean}`, method: "Arithmetic mean", parameters: {}, environment: { javascript: "Playwright" }, execution: "computed", executor: "Synthetic browser test", limitations: "Synthetic data only", files: [{ filename: "method.py", kind: "code", content_base64: code.toString("base64"), sha256: createHash("sha256").update(code).digest("hex") }] })
    await page.addInitScript(lang => localStorage.setItem("lang", JSON.stringify({ data: lang, expire: null })), locale)
    await page.setViewportSize({ width, height: 900 })
    async function approveInBrowser(id: string) {
      await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/analysis?view=external&operation_id=${id}`)
      const dialog = page.getByTestId("external-operation-dialog")
      await expect(dialog).toBeVisible()
      const approve = dialog.getByRole("button", { name: strings.approve, exact: true })
      await expect(approve).toBeDisabled()
      await dialog.getByRole("checkbox", { name: strings.reviewed, exact: true }).check()
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await page.screenshot({ path: testInfo.outputPath(`review-${locale}-${id}.png`) })
      const decided = page.waitForResponse(response => response.url().endsWith(`/operations/${id}/decision`))
      await approve.click()
      expect((await decided).ok()).toBeTruthy()
    }
    await approveInBrowser(operation.id)
    const execution = await call("execute_operation", { operation_id: operation.id })
    const report = await call("get_external_analysis", { run_id: execution.result.run_id })
    expect(report.result.report).toBe("Mean = 3")
    expect(report.result.method.revision).toBe(1)
    const orgPrefix = (process.env.E2E_DEPLOYMENT_MODE ?? "community") === "community" ? `/orgs/${fixtures.lab.uid}` : ""
    const projectReports = `${orgPrefix}/projects/${fixtures.project.uid}/analysis?view=external`
    expect(execution.result.links[0]).toBe(`${projectReports}&analysis_id=${execution.result.run_id}`)
    await page.goto(projectReports)
    const reports = page.getByTestId("external-project-reports")
    await expect(reports).toContainText(`Synthetic mean ${uid}`)
    await reports.getByRole("textbox").fill(uid)
    await reports.getByTestId(`external-report-${execution.result.run_id}`).getByRole("button").click()
    await expect(page.getByTestId("external-analysis-report")).toContainText("Mean = 3")
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`project-report-${locale}.png`) })
    const downloaded = page.waitForEvent("download")
    await page.getByTestId("external-analysis-report").getByRole("button", { name: "method.py", exact: true }).click()
    expect((await downloaded).suggestedFilename()).toBe("method.py")

    const source = await call("download_protocol_source", { protocol_id: protocol.id, version: "0.1.0", format: "zip" })
    files["protocol.toml"] = files["protocol.toml"].replace("version=\"0.1.0\"", "version=\"0.1.1\"")
    files["protocol.aimd"] += "\nA synthetic clarification.\n"
    const candidate = await call("preview_protocol_candidate", { protocol_id: protocol.id, base_version_id: source.protocol_version_id, files, request_key: randomUUID() })
    await approveInBrowser(candidate.id)
    const release = await call("execute_operation", { operation_id: candidate.id })
    await page.goto(release.result.links[0])
    await expect(page).toHaveURL(new RegExp(`/protocols/${uid}`))
    await expect(page.getByText("Synthetic external research", { exact: true }).first()).toBeVisible()

    const callback = "http://127.0.0.1:8765/callback"
    const registered = await request.post(`${api}/external-access/oauth/clients`, { headers, data: { name: "Synthetic PKCE client", redirect_uris: [callback] } })
    const { client_id: clientId } = await registered.json()
    const verifier = "v".repeat(64)
    const query = new URLSearchParams({ response_type: "code", client_id: clientId, redirect_uri: callback, state: randomUUID(), code_challenge: createHash("sha256").update(verifier).digest("base64url"), code_challenge_method: "S256", resource: `${origin}/api/mcp`, scope: "protocols:read records:read" })
    // Intercept only the loopback delivery; all consent and code exchange use the real API.
    await page.route(`${callback}*`, route => route.fulfill({ contentType: "text/plain", body: "Synthetic callback received" }))
    const cashOnly = new URLSearchParams(query)
    cashOnly.set("scope", "cash:read")
    await page.goto(`/api/external-access/oauth/authorize?${cashOnly}`)
    await expect(page.getByTestId("oauth-contract-receipt")).toBeDisabled()
    const missing = page.getByRole("status").filter({ hasText: strings.createContracts })
    await expect(missing).toContainText(strings.readContracts)
    await expect(missing).toContainText(strings.linkReceipt)
    await page.goto(`/api/external-access/oauth/authorize?${query}`)
    await expect(page.getByTestId("oauth-contract-receipt")).toHaveCount(0)
    await expect(page.getByText("Synthetic PKCE client", { exact: true })).toBeVisible()
    const selector = page.getByTestId("oauth-project")
    if (!(await selector.textContent() || "").includes("Quickstart Protocol Testing")) {
      await selector.click()
      await selectVisibleOption(page, "Quickstart Protocol Testing")
    }
    await page.getByRole("button", { name: language.accountSettings.clear, exact: true }).click()
    await expect(page.getByRole("checkbox", { name: strings.readProtocols, exact: true })).not.toBeChecked()
    await page.getByRole("button", { name: language.accountSettings.allScopes, exact: true }).click()
    await expect(page.getByRole("checkbox", { name: strings.readProtocols, exact: true })).toBeChecked()
    await expect(page.getByRole("button", { name: strings.approve, exact: true })).toBeDisabled()
    await page.getByRole("checkbox", { name: strings.authorizationReviewed, exact: true }).check()
    await page.getByRole("button", { name: strings.approve, exact: true }).click()
    await expect(page).toHaveURL(/127\.0\.0\.1:8765\/callback\?code=/)
    const codeValue = new URL(page.url()).searchParams.get("code")!
    const exchanged = await request.post(`${api}/external-access/oauth/token`, { form: { grant_type: "authorization_code", client_id: clientId, redirect_uri: callback, code: codeValue, code_verifier: verifier, resource: `${origin}/api/mcp` } })
    expect(exchanged.ok(), await exchanged.text()).toBeTruthy()
    const reconnect = new URLSearchParams(query)
    reconnect.set("scope", "protocols:read records:read cash:read contracts:read contracts:create cash:link")
    await page.goto(`/api/external-access/oauth/authorize?${reconnect}`)
    if (!(await selector.textContent() || "").includes("Quickstart Protocol Testing")) {
      await selector.click()
      await selectVisibleOption(page, "Quickstart Protocol Testing")
    }
    await expect(page.getByTestId("oauth-source")).toContainText(strings.readProtocols)
    await expect(page.getByRole("checkbox", { name: strings.readProtocols, exact: true })).toBeChecked()
    await expect(page.getByRole("checkbox", { name: strings.readRecords, exact: true })).toBeChecked()
    await expect(page.getByRole("checkbox", { name: strings.createContracts, exact: true })).not.toBeChecked()
  })
}
