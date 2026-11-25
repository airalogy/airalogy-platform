import { expect, test } from "@playwright/test"

for (const ui of [
  {
    locale: "zh-CN",
    width: 390,
    create: "新建协议",
    syntaxError: /请检查 TOML 第 1 行、第 \d+ 列/,
    save: "保存",
    title: "保存协议",
    basic: "基础信息",
    version: "版本",
    globalId: "全局 ID（自动生成）",
    idExample: "例如 airalogy_protocol",
    name: "请输入协议名称",
    addAuthor: "添加作者",
    author: "作者 1",
    addMaintainer: "添加维护者",
    maintainer: "维护者 1",
    remove: "移除作者 1",
    description: "描述",
    descriptionPlaceholder: "请输入协议描述",
    keywords: "关键词",
    toml: "TOML 预览",
    edit: "修改",
    idRule: "仅支持小写英文字母",
    cancel: "取消",
  },
  {
    locale: "en-US",
    width: 1280,
    create: "New protocol",
    syntaxError: /Check the TOML syntax at line 1, column \d+/i,
    save: "Save",
    title: "Save Protocol",
    basic: "Basic information",
    version: "Version",
    globalId: "Global ID (auto-generated)",
    idExample: "e.g. airalogy_protocol",
    name: "Enter protocol name",
    addAuthor: "Add Author",
    author: "Author 1",
    addMaintainer: "Add Maintainer",
    maintainer: "Maintainer 1",
    remove: "Remove author 1",
    description: "Description",
    descriptionPlaceholder: "Describe your protocol",
    keywords: "Keywords",
    toml: "Preview TOML",
    edit: "Edit",
    idRule: /lowercase/i,
    cancel: "Cancel",
  },
]) {
  test(`the save dialog shows protocol metadata in ${ui.locale}`, async ({ page }) => {
    await page.setViewportSize({ width: ui.width, height: 985 })
    await page.addInitScript(locale => localStorage.setItem("lang", JSON.stringify({ data: locale, expire: null })), ui.locale)
    await page.goto("/orgs/dev_lab/projects/quickstart/protocols")
    await page.getByRole("button", { name: ui.create, exact: true }).click()
    await page.getByTestId("protocol-create-template").click()
    const protocolName = "Practice ABC 练习"
    await page.getByTestId("template-name").locator("input").fill(protocolName)
    await page.getByTestId("template-create-confirm").click()
    await expect(page.getByTestId("protocol-validation")).toContainText(/静态检查通过|Static checks passed/)
    await page.getByRole("button", { name: ui.save, exact: true }).click()
    const dialog = page.getByRole("dialog")
    for (const text of [ui.title, ui.basic, ui.version, ui.globalId, ui.keywords, ui.toml])
      await expect(dialog.getByText(text, { exact: true })).toBeVisible()
    await expect(dialog.getByPlaceholder(ui.name, { exact: true })).toHaveValue(protocolName)
    const id = dialog.getByPlaceholder(ui.idExample)
    const protocolId = await id.inputValue()
    await expect(dialog).toContainText(`.protocol.${protocolId}.v.0.1.0`)
    await id.fill("INVALID!")
    await id.blur()
    await expect(dialog.getByText(ui.idRule, { exact: false }).first()).toBeVisible()
    await id.fill(protocolId)
    await dialog.getByText(ui.description, { exact: true }).click()
    await expect(dialog.getByPlaceholder(ui.descriptionPlaceholder)).toBeVisible()
    await dialog.getByRole("button", { name: ui.addAuthor }).click()
    await expect(dialog.getByText(ui.author, { exact: true })).toBeVisible()
    await dialog.getByRole("button", { name: ui.remove }).click()
    await expect(dialog.getByText(ui.author, { exact: true })).toHaveCount(0)
    await dialog.getByRole("button", { name: ui.addMaintainer }).click()
    await expect(dialog.getByText(ui.maintainer, { exact: true })).toBeVisible()
    await dialog.getByRole("button", { name: ui.edit, exact: true }).click()
    const tomlSection = dialog.locator(".n-collapse-item").filter({ has: page.getByText(ui.toml, { exact: true }) })
    const tomlInput = tomlSection.locator("textarea")
    await expect(tomlInput).toHaveValue(/\[airalogy_protocol\]/)
    await tomlInput.fill("invalid = ]")
    await tomlSection.getByRole("button", { name: ui.save, exact: true }).click()
    await expect(page.getByText(ui.syntaxError)).toBeVisible()
    await expect(tomlInput).toHaveValue("invalid = ]")
    await dialog.getByRole("button", { name: ui.cancel, exact: true }).click()
    await expect(dialog).toBeHidden()
  })
}
