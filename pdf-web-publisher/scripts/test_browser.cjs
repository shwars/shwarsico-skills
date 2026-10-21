/* Optional development check: requires Playwright and its Chromium browser.
 * node test_browser.cjs <preview-parent> <screenshot-directory>
 * Preview parent must have <theme>/nested/site/presentations for each theme.
 * Rename/edit cases use isolated copies; original preview decks stay unchanged.
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
      let filename = path.resolve(base, `.${name}`);
      if (!filename.startsWith(`${base}${path.sep}`)) throw new Error("Outside fixture");
      if ((await fs.stat(filename)).isDirectory()) filename = path.join(filename, "index.html");
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
  const cases = await fs.mkdtemp(path.join(base, ".browser-cases-"));
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

    // Move a deck and change just its catalog link; its internal files must not
    // need regeneration. Then edit metadata and reload without a rebuild.
    for (const theme of themes) {
      const archive = path.join(cases, theme, "presentations");
      await fs.cp(path.join(base, theme, "nested", "site", "presentations"), archive, { recursive: true });
      const original = await fs.readFile(path.join(archive, "working-system", "deck.js"));
      await fs.rename(path.join(archive, "working-system"), path.join(archive, "renamed-talk"));
      const catalogPath = path.join(archive, "catalog.js");
      const source = await fs.readFile(catalogPath, "utf8");
      const catalog = JSON.parse(source.slice(source.indexOf("=") + 1).trim().replace(/;$/, ""));
      const entry = catalog.presentations.find((item) => item.href === "working-system/index.html");
      entry.href = "renamed-talk/index.html";
      await fs.writeFile(catalogPath, `window.PDFWebPublisherCatalog = ${JSON.stringify(catalog, null, 2)};\n`);
      assert.deepEqual(await fs.readFile(path.join(archive, "renamed-talk", "deck.js")), original);
      const relative = path.relative(base, archive).split(path.sep).join("/");
      for (const protocol of ["file", "http"]) {
        const page = await browser.newPage();
        page.on("pageerror", (error) => errors.push(error.message));
        const rootURL = protocol === "file" ? pathToFileURL(path.join(archive, "index.html")).href : `${origin}/${relative}/index.html`;
        await page.goto(rootURL);
        const link = page.locator('.deck-link[href="renamed-talk/index.html"]');
        await link.waitFor();
        await page.waitForFunction(() => {
          const image = document.querySelector('.deck-link[href="renamed-talk/index.html"] img');
          return image.complete && image.naturalWidth > 0;
        });
        await link.click();
        await page.locator("canvas:visible").waitFor();
        const deckURL = page.url().split("#")[0];
        const direct = protocol === "http" ? deckURL.replace(/index\.html$/, "") : deckURL;
        await page.goto(`${direct}?from=catalog#slide=2`);
        await page.locator("canvas:visible").waitFor();
        assert.equal(await page.locator(".slide-counter").textContent(), "2 / 3");
        entry.title = "Renamed talk — hand edited";
        await fs.writeFile(catalogPath, `window.PDFWebPublisherCatalog = ${JSON.stringify(catalog, null, 4)};\n`);
        await page.reload();
        await page.getByRole("heading", { name: entry.title, exact: true }).waitFor();
        await page.goto(rootURL);
        await page.getByRole("heading", { name: entry.title, exact: true }).waitFor();
        await page.close();
        checks++;
      }
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: checks, browser: "chromium", pageErrors: errors, screenshots }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
    // Only delete the unique temporary directory created by this run.
    assert.ok(path.resolve(cases).startsWith(`${base}${path.sep}.browser-cases-`));
    await fs.rm(cases, { recursive: true });
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
