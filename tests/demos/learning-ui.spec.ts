import { expect, test } from "@playwright/test"
import manifest from "../../docs/demos/manifest.json" with { type: "json" }

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
}

for (const locale of ["zh", "en"]) {
  for (const width of [390, 820, 1440]) {
    test(`learning UI: ${locale} at ${width}px can play, seek and read captions`, async ({ page }) => {
      const externalRequests: string[] = []
      const origin = new URL(process.env.DEMO_WEB_URL || "http://127.0.0.1:3100").origin
      page.on("request", (request) => {
        const url = new URL(request.url())
        if (["http:", "https:"].includes(url.protocol) && url.origin !== origin)
          externalRequests.push(url.origin)
      })
      await page.setViewportSize({ width, height: 900 })
      await page.goto(`/docs/${locale}/learn/`)
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
      await page.goto(`/docs/${locale}/learn/first-record`)
      const video = page.locator("video")
      await expect(video).toBeVisible()
      await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState)).toBeGreaterThanOrEqual(1)
      expect(await video.evaluate((element: HTMLVideoElement) => element.duration)).toBeGreaterThan(20)
      expect(await video.evaluate((element: HTMLVideoElement) => element.paused && !element.autoplay)).toBe(true)
      await page.getByRole("heading", { level: 1 }).click()
      await video.evaluate(async (element: HTMLVideoElement) => {
        await element.play()
      })
      await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime)).toBeGreaterThan(0)
      await video.evaluate((element: HTMLVideoElement) => {
        element.pause()
        element.currentTime = Math.min(15, element.duration - 1)
      })
      await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime)).toBeCloseTo(15, 0)
      const track = video.locator(`track[srclang=${locale}]`)
      await expect(track).toHaveAttribute("default", "")
      await expect.poll(() => track.evaluate((element: HTMLTrackElement) => element.track.cues?.length || 0)).toBeGreaterThan(5)
      const captions = await track.evaluate((element: HTMLTrackElement) => ({ mode: element.track.mode, first: (element.track.cues?.[0] as VTTCue)?.text }))
      expect(captions.mode).toBe("showing")
      expect(captions.first.length).toBeGreaterThan(10)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
      for (const link of await page.locator(".demo-lesson a[download]").all()) {
        const href = await link.getAttribute("href")
        const response = await page.request.get(href!)
        expect(response.ok(), href!).toBeTruthy()
        expect((await response.body()).length).toBeGreaterThan(20)
      }
      expect(externalRequests).toEqual([])
    })
  }
}

for (const [lesson, media] of Object.entries(manifest)) {
  test(`learning narration: ${lesson} has audible Chinese speech aligned with both captions`, async ({ page }) => {
    await page.goto(`/docs/zh/learn/${lesson}`)
    const video = page.locator("video")
    await expect(page.locator(".demo-note").first()).toContainText("中文 AI 配音")
    await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState)).toBeGreaterThanOrEqual(1)
    expect(await video.evaluate((element: HTMLVideoElement) => element.duration)).toBeCloseTo(media.duration, 1)
    const levels = await video.evaluate(async (element: HTMLVideoElement, timeline) => {
      const response = await fetch(element.currentSrc)
      const context = new OfflineAudioContext(1, 1, 48000)
      const decoded = await context.decodeAudioData(await response.arrayBuffer())
      const samples = decoded.getChannelData(0)
      return timeline.map((step) => {
        const start = Math.floor((step.audio_start + 0.1) * decoded.sampleRate)
        const end = Math.floor((step.audio_end - 0.1) * decoded.sampleRate)
        let power = 0
        for (let i = start; i < end; i++) power += samples[i] ** 2
        return Math.sqrt(power / (end - start))
      })
    }, media.narration.timeline)
    for (const level of levels) expect(level).toBeGreaterThan(0.01)
    // Both language tracks must seek to the same current step after retiming.
    for (const [index, step] of media.narration.timeline.entries()) {
      await video.evaluate((element: HTMLVideoElement, at) => {
        for (const track of Array.from(element.textTracks)) track.mode = "hidden"
        element.currentTime = at
      }, step.audio_start + 0.1)
      for (const locale of ["zh", "en"]) {
        const track = video.locator(`track[srclang=${locale}]`)
        await expect.poll(() => track.evaluate((element: HTMLTrackElement) => element.track.activeCues?.[0]?.id)).toBe(String(index + 1))
      }
    }
    await page.getByRole("heading", { level: 1 }).click()
    await video.evaluate(async (element: HTMLVideoElement) => {
      element.currentTime = 0
      element.muted = true
      await element.play()
    })
    expect(await video.evaluate((element: HTMLVideoElement) => element.muted)).toBe(true)
    await video.evaluate((element: HTMLVideoElement) => {
      element.muted = false
      element.pause()
    })
    expect(await video.evaluate((element: HTMLVideoElement) => element.paused && !element.muted)).toBe(true)
  })
}

test("learning UI: introduction is optional, persists dismissal and remains in help", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await login(page)
  await page.goto("/home")
  const intro = page.getByTestId("learning-intro")
  await expect(intro).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await intro.getByRole("button").click()
  await expect(intro).toHaveCount(0)
  await page.reload()
  await expect(intro).toHaveCount(0)
  await page.goto("/help")
  await expect(page.getByTestId("learning-link")).toHaveAttribute("href", /\/docs\/zh\/learn\//)
})

test("learning UI: final visual keystrokes survive immediate navigation and source switch", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await login(page)
  await page.goto("/research-documents")
  await page.getByTestId("new-research-document").click()
  await page.getByTestId("new-document-title").locator("input").fill("虚构测试：保存最后一次输入")
  await page.getByTestId("create-document-confirm").click()
  const prose = page.locator(".ProseMirror[contenteditable=true]")
  await expect(prose).toBeVisible()
  const url = page.url()
  await prose.fill("DEMO: immediate navigation must preserve this sentence.")
  // Do not wait for the editor's delayed Markdown event or autosave.
  await page.getByTestId("document-back").click()
  await expect(page).not.toHaveURL(url)
  await page.goto(url)
  await expect(prose).toContainText("immediate navigation")
  await prose.fill("DEMO: final edit before switching to source.")
  await page.getByTestId("document-source-mode").click()
  await page.getByTestId("document-back").click()
  await expect(page).not.toHaveURL(url)
  const readDocument = () => page.waitForResponse(response => response.url().endsWith(`/api/research-documents/${url.split("/").pop()}`) && response.request().method() === "GET")
  const firstRead = readDocument()
  await page.goto(url)
  await expect(prose).toContainText("final edit before switching")
  const originalRevision = (await (await firstRead).json()).revision
  expect(originalRevision).toBeGreaterThan(1)
  await page.getByTestId("document-back").click()
  await expect(page).not.toHaveURL(url)
  const secondRead = readDocument()
  await page.goto(url)
  await expect(prose).toContainText("final edit before switching")
  expect((await (await secondRead).json()).revision).toBe(originalRevision)
})
