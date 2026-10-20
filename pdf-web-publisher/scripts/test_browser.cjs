/* Optional development check: requires Playwright and its Chromium browser.
 * node test_browser.cjs <preview-parent> <screenshot-directory>
 * Preview parent must have <theme>/nested/site/presentations for each theme.
 * The preview fixture is external; this script never modifies source decks.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");
const { pathToFileURL } = require("node:url");
const { chromium } = require("playwright");

async function main() {
  const base = path.resolve(process.argv[2]);
  const screenshots = path.resolve(process.argv[3]);
  await fs.mkdir(screenshots, { recursive: true });
  const server = http.createServer(async (request, response) => {
    try {
      const name = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
      const filename = path.resolve(base, `.${name}`);
      if (!filename.startsWith(`${base}${path.sep}`)) throw new Error("Outside fixture");
      const data = await fs.readFile(filename);
      response.setHeader("Content-Type", ({ ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css", ".webp": "image/webp" })[path.extname(filename)] || "application/octet-stream");
      response.end(data);
    } catch (_) { response.writeHead(404); response.end("Not found"); }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  server.unref();
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined });
  const errors = [];
  let checks = 0;
  const themes = ["programme", "screening-room", "field-notes"];
  try {
    for (const theme of themes) {
      for (const protocol of ["file", "http"]) {
        const relative = `${theme}/nested/site/presentations`;
        const url = protocol === "file" ? pathToFileURL(path.join(base, relative, "index.html")).href : `${origin}/${relative}/index.html`;
        const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
        const page = await context.newPage();
        page.on("pageerror", (error) => errors.push(error.message));
        await page.goto(url);
        await page.locator(".deck-entry").first().waitFor();
        assert.equal(await page.locator(".deck-entry").count(), 3);
        assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
        await page.locator("#archive-search").fill("evaluation");
        assert.equal(await page.locator(".deck-entry:visible").count(), 1);
        await page.locator("#archive-search").fill("no matches expected");
        assert.equal(await page.locator(".empty-state:visible").count(), 1);
        await page.locator("#archive-search").fill("");
        assert.equal(await page.locator(".deck-entry:visible").count(), 3);
        if (protocol === "http") {
          await page.screenshot({ path: path.join(screenshots, `${theme}-gallery-desktop.png`), fullPage: true });
          await page.setViewportSize({ width: 390, height: 844 });
          await page.screenshot({ path: path.join(screenshots, `${theme}-gallery-mobile.png`), fullPage: true });
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
          await page.setViewportSize({ width: 1440, height: 1000 });
        }
        await page.locator(".deck-link").first().click();
        await page.locator("canvas:visible").waitFor();
        assert.equal(await page.locator(".slide-counter").textContent(), "1 / 3");
        assert.equal(await page.locator("#previous-slide").isDisabled(), true);
        await page.keyboard.press("ArrowRight");
        await page.waitForFunction(() => !document.querySelector("canvas").hidden && location.hash === "#slide=2");
        assert.equal(await page.locator(".slide-counter").textContent(), "2 / 3");
        await page.keyboard.press("End");
        await page.waitForFunction(() => !document.querySelector("canvas").hidden && location.hash === "#slide=3");
        assert.equal(await page.locator("#next-slide").isDisabled(), true);
        const proportions = await page.locator("canvas").evaluate((node) => {
          const box = node.getBoundingClientRect();
          return { intrinsic: node.width / node.height, displayed: box.width / box.height };
        });
        assert.ok(Math.abs(proportions.intrinsic - proportions.displayed) < .01, "Portrait slide must retain proportions");
        await page.keyboard.press("t");
        await page.locator(".thumbnail-panel:visible").waitFor();
        assert.equal(await page.locator(".thumbnail-button").count(), 3);
        await page.locator(".thumbnail-button").first().click();
        await page.waitForFunction(() => !document.querySelector("canvas").hidden && location.hash === "#slide=1");
        assert.equal(await page.locator(".thumbnail-panel:visible").count(), 0);
        await page.evaluate(() => { document.querySelector(".player").requestFullscreen = undefined; });
        await page.locator(".back-link").focus();
        await page.keyboard.press("f");
        assert.equal(await page.locator(".player.is-expanded").count(), 1);
        assert.equal(await page.evaluate(() => document.querySelector(".slide-stage") === document.activeElement), true);
        await page.keyboard.press("Shift+Tab");
        assert.equal(await page.evaluate(() => document.querySelector(".player").contains(document.activeElement)), true);
        await page.keyboard.press("Tab");
        assert.equal(await page.evaluate(() => document.querySelector(".slide-stage") === document.activeElement), true);
        await page.keyboard.press("Escape");
        assert.equal(await page.locator(".player.is-expanded").count(), 0);
        assert.equal(await page.evaluate(() => document.querySelector(".back-link") === document.activeElement), true);
        assert.equal(await page.locator("[inert]").count(), 0);
        const prevented = await page.locator(".slide-stage").evaluate((node) => {
          const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
          node.dispatchEvent(event);
          return event.defaultPrevented;
        });
        assert.equal(prevented, true);
        if (protocol === "http") {
          await page.screenshot({ path: path.join(screenshots, `${theme}-viewer-desktop.png`), fullPage: true });
          await page.setViewportSize({ width: 390, height: 844 });
          await page.screenshot({ path: path.join(screenshots, `${theme}-viewer-mobile.png`), fullPage: true });
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        }
        await page.emulateMedia({ media: "print" });
        assert.equal(await page.locator(".player:visible").count(), 0);
        await page.emulateMedia({ media: "screen", reducedMotion: "reduce" });
        const transition = await page.locator(".slide-progress-fill").evaluate((node) => getComputedStyle(node).transitionDuration);
        assert.equal(transition, "0s");
        checks++;
        await context.close();
      }
    }
    // Explicit touch navigation on a phone-sized browser context.
    const touchContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    const touchPage = await touchContext.newPage();
    await touchPage.goto(`${origin}/programme/nested/site/presentations/working-system/index.html#slide=2`);
    await touchPage.locator("canvas:visible").waitFor();
    assert.equal(await touchPage.locator(".slide-counter").textContent(), "2 / 3");
    await touchPage.locator(".slide-stage").evaluate((node) => {
      node.dispatchEvent(new TouchEvent("touchstart", { touches: [new Touch({ identifier: 1, target: node, clientX: 280, clientY: 150 })] }));
      node.dispatchEvent(new TouchEvent("touchend", { changedTouches: [new Touch({ identifier: 1, target: node, clientX: 90, clientY: 155 })] }));
    });
    await touchPage.waitForFunction(() => location.hash === "#slide=3");
    await touchContext.close();
    checks++;

    // Failed current slides remain visibly failed when adjacent preloads finish.
    const failurePage = await browser.newPage();
    await failurePage.route("**/slides/*", (route) => route.abort());
    await failurePage.goto(`${origin}/programme/nested/site/presentations/working-system/index.html`);
    await failurePage.locator(".slide-error:visible").waitFor();
    await failurePage.unroute("**/slides/*");
    await failurePage.getByRole("button", { name: "Retry loading slide" }).click();
    await failurePage.locator("canvas:visible").waitFor();
    await failurePage.close();
    checks++;

    const unsafePage = await browser.newPage();
    await unsafePage.route("**/catalog.js", async (route) => {
      const response = await route.fetch();
      const source = (await response.text()).replace("From prompt to working system", "<img src=x onerror=window.__unsafeMetadata=true>");
      await route.fulfill({ response, body: source });
    });
    await unsafePage.goto(`${origin}/programme/nested/site/presentations/index.html`);
    await unsafePage.getByRole("heading", { name: "<img src=x onerror=window.__unsafeMetadata=true>" }).waitFor();
    assert.equal(await unsafePage.evaluate(() => window.__unsafeMetadata), undefined);
    await unsafePage.close();
    checks++;
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: checks, browser: "chromium", pageErrors: errors, screenshots }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
