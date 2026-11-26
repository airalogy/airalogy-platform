import { Buffer } from "node:buffer"
import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

// Four seconds of 8-bit mono silence, long enough to seek into the second cue.
function recording() {
  const samples = 32000
  const wav = Buffer.alloc(44 + samples, 128)
  wav.write("RIFF", 0)
  wav.writeUInt32LE(36 + samples, 4)
  wav.write("WAVEfmt ", 8)
  wav.writeUInt32LE(16, 16)
  wav.writeUInt16LE(1, 20)
  wav.writeUInt16LE(1, 22)
  wav.writeUInt32LE(8000, 24)
  wav.writeUInt32LE(8000, 28)
  wav.writeUInt16LE(1, 32)
  wav.writeUInt16LE(8, 34)
  wav.write("data", 36)
  wav.writeUInt32LE(samples, 40)
  return wav
}

test("import a transcript and confirm speaker accounts on desktop and mobile", async ({
  page,
  request,
}) => {
  const email = process.env.E2E_OWNER_EMAIL || "dev.owner@airalogy.dev"
  const password = process.env.E2E_OWNER_PASSWORD || "AiralogyDev123!"
  const login = await request.post("/api/signin_by_email", { data: { email, password } })
  expect(login.ok()).toBeTruthy()
  const { token } = await login.json()
  const headers = { "Auth-Token": token }
  const organizations = await request.get("/api/meeting-workspace/organizations", { headers })
  const [{ id: lab }] = await organizations.json()
  const options = await (
    await request.get(`/api/meeting-workspace/organizations/${lab}/options`, { headers })
  ).json()
  const speaker
    = options.people.find((p: { username: string }) => p.username === "dev_owner")
    || options.people[0]

  await page.addInitScript(() =>
    localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })),
  )
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill(email)
  await page.getByTestId("login-password").locator("input").fill(password)
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 850 })
    await page.goto("/my-work?room=new")
    const title = `Minutes ${width} ${Date.now()}`
    await page.getByLabel("会议主题").fill(title)
    await page.getByLabel("会议纪要", { exact: true }).fill("参会人校订的会议纪要")
    await page.getByRole("button", { name: "保存", exact: true }).click()
    await expect(page.getByRole("heading", { name: title })).toBeVisible()
    await page.getByRole("button", { name: "录音与逐字稿" }).click()
    await page.locator("input[accept=\".srt,.vtt,.txt\"]").setInputFiles({
      name: "test.srt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        `1\n00:00:00,000 --> 00:00:01,125\n${speaker.username}：原稿署名\n\n2\n00:00:02,000 --> 00:00:03,500\n访客：未关联的发言\n`,
      ),
    })
    await expect(page.getByText("按说话人关联账号", { exact: true })).toBeVisible()
    const links = page.getByRole("combobox", { name: "关联账号", exact: true })
    const allUnique = page.getByRole("button", { name: "选中全部唯一匹配" })
    if (width === 390) {
      await page.getByRole("button", { name: "跳过关联，保留逐字稿" }).click()
      await expect(page.getByText(speaker.username, { exact: true })).toBeVisible()
      await page.getByRole("button", { name: "校对逐字稿与说话人" }).click()
      const firstSpeaker = page.getByRole("group", { name: "按说话人关联账号" }).getByRole("combobox").first()
      await firstSpeaker.selectOption({ label: "不关联账号" })
      await allUnique.click()
      await expect(links.first().locator("option:checked")).toHaveText("不关联账号")
      await firstSpeaker.selectOption(speaker.id)
    }
    else {
      await allUnique.click()
    }
    await expect(links.first()).toHaveValue(speaker.id)
    await expect(links.last().locator("option:checked")).toHaveText("不关联账号")
    await page.getByRole("button", { name: "保存", exact: true }).click()
    await expect(page.getByText("未关联的发言", { exact: true })).toBeVisible()
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    ).toBeTruthy()
    await page.reload()
    await page.getByRole("button", { name: "录音与逐字稿" }).click()
    await expect(page.getByText(speaker.name, { exact: true })).toBeVisible()
    await expect(page.getByText("访客", { exact: true })).toBeVisible()
    await page.locator("input[accept*=\".wav\"]").setInputFiles({ name: "meeting.wav", mimeType: "audio/wav", buffer: recording() })
    await page.getByRole("button", { name: "00:00:02" }).click()
    await expect.poll(() => page.locator("audio").evaluate(el => (el as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(2)
    const format = page.getByRole("button", { name: "VTT", exact: true })
    const downloadable = page.waitForEvent("download")
    await format.click()
    expect((await downloadable).suggestedFilename()).toBe("transcript.vtt")
  }
})
