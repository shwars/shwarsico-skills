// Optional authoring QA, not a runtime dependency. Requires Playwright (not @playwright/test).
// Usage: node browser_check.cjs /absolute/project; PLAYWRIGHT_PATH may point to a local installation.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const pw = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const root = path.resolve(process.argv[2] || '.');
const output = path.join(root, 'qa/browser');
const story = JSON.parse(fs.readFileSync(path.join(root, 'script.json'), 'utf8'));
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.webp':'image/webp','.json':'application/json; charset=utf-8'};
const server = http.createServer((req, res) => {
  let relative = decodeURIComponent(req.url.split('?')[0]);
  if (relative.startsWith('/stage/')) relative = relative.slice(6);
  const file = path.resolve(root, '.' + (relative.endsWith('/') ? relative + 'index.html' : relative));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

async function checkPage(page, browserName, url, localBase) {
  const errors = [], external = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!/^(file:|data:)/.test(r.url()) && !r.url().startsWith(localBase)) external.push(r.url()); });
  await page.goto(url);
  await page.waitForFunction(() => globalThis.SpriteTheater?.ready || document.documentElement.dataset.ready === 'error', null, {timeout:10000});
  if (!await page.evaluate(() => SpriteTheater.ready)) throw new Error(await page.locator('#load-status').textContent());
  assert.equal(await page.locator('h1').textContent(), story.title);
  assert.equal(await page.locator('[data-scene]').count(), story.scenes.length);
  let frames = 0, sceneStart = 0;
  for (const size of [{width:1440,height:1000},{width:390,height:844},{width:900,height:800}]) {
    await page.setViewportSize(size);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    sceneStart = 0;
    for (const scene of story.scenes) {
      for (const cue of scene.cues) {
        const at = sceneStart + cue.at + Math.min(.8, cue.duration / 2);
        const info = await page.evaluate(async at => {
          SpriteTheater.seek(at); await new Promise(requestAnimationFrame);
          const bubble = document.getElementById('dialogue'), stage = document.getElementById('stage');
          const b = bubble.getBoundingClientRect(), s = stage.getBoundingClientRect();
          return {hidden:bubble.hidden, x:b.x, right:b.right, top:b.top, bottom:b.bottom, stageBottom:s.bottom,
            viewport:innerWidth, overflow:document.documentElement.scrollWidth > innerWidth,
            overflowItems:[...document.querySelectorAll('body *')].map(e => ({id:e.id, tag:e.tagName, right:e.getBoundingClientRect().right})).filter(e => e.right > innerWidth + 1).slice(0,5),
            text:document.getElementById('speech').textContent, state:SpriteTheater.inspect()};
        }, at);
        assert.equal(info.state.scene, scene.id);
        assert.equal(info.state.cue, cue.id);
        assert.equal(info.overflow, false, 'horizontal overflow: ' + JSON.stringify(info.overflowItems));
        if (!info.hidden) {
          assert.equal(info.text, cue.text);
          assert.ok(info.x >= 0 && info.right <= info.viewport + 1, 'dialogue outside viewport');
          if (info.state.caption) assert.ok(info.top >= info.stageBottom, 'caption overlaps stage');
        }
        frames++;
      }
      sceneStart += scene.duration;
    }
    const first = story.scenes[0].cues[0];
    await page.evaluate(t => SpriteTheater.seek(t), first.at + Math.min(1, first.duration / 2));
    await page.screenshot({path:path.join(output, `${browserName}-${url.startsWith('file:')?'file':url.includes('/stage/')?'subdir':'http'}-${size.width}.png`), fullPage:true});
  }
  const fullShowFrames = await page.evaluate(() => {
    let count = 0;
    for (let time = 0; time <= SpriteTheater.playback.total; time += .5) {
      SpriteTheater.seek(time); count++;
    }
    SpriteTheater.seek(SpriteTheater.playback.total);
    if (!SpriteTheater.inspect().ended) throw new Error('Playback did not reach its end');
    return count;
  });
  await page.evaluate(() => SpriteTheater.seek(3));
  const paused = await page.evaluate(() => SpriteTheater.inspect().time);
  await page.waitForTimeout(150);
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().time), paused);
  await page.locator('#play').click();
  await page.waitForFunction(t => SpriteTheater.inspect().time > t, paused, {timeout:5000});
  await page.locator('#play').click();
  await page.locator('#speed').selectOption('2');
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().speed), 2);
  await page.locator('#timeline').scrollIntoViewIfNeeded();
  const slider = await page.locator('#timeline').boundingBox();
  await page.mouse.move(slider.x + slider.width * .2, slider.y + slider.height / 2);
  await page.mouse.down();
  await page.mouse.move(slider.x + slider.width * .4, slider.y + slider.height / 2);
  await page.mouse.up();
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().paused), true);
  await page.locator('#play').click();
  await page.mouse.move(slider.x + slider.width * .3, slider.y + slider.height / 2);
  await page.mouse.down();
  await page.mouse.move(slider.x + slider.width * .5, slider.y + slider.height / 2);
  await page.mouse.up();
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().paused), false);
  await page.locator('#play').click();
  const firstCue = story.scenes[0].cues[0];
  await page.evaluate(t => { SpriteTheater.seek(t, false); document.activeElement?.blur(); }, firstCue.at + .01);
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.evaluate(() => SpriteTheater.playback.revealed), firstCue.id);
  await page.keyboard.press('ArrowRight');
  assert.ok(await page.evaluate(t => SpriteTheater.inspect().time > t, firstCue.at + .01));
  await page.locator('[data-scene]').last().click();
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().scene), story.scenes.at(-1).id);
  await page.evaluate(() => SpriteTheater.seek(SpriteTheater.playback.total));
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().ended), true);
  await page.locator('#restart').click();
  assert.ok(await page.evaluate(() => SpriteTheater.inspect().time < 1 && !SpriteTheater.inspect().paused));
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', {configurable:true, value:true});
    document.dispatchEvent(new Event('visibilitychange'));
    Object.defineProperty(document, 'hidden', {configurable:true, value:false});
    document.dispatchEvent(new Event('visibilitychange'));
  });
  assert.equal(await page.evaluate(() => SpriteTheater.inspect().paused), true);
  await page.evaluate(() => { document.getElementById('player').requestFullscreen = () => Promise.reject(new Error('QA fallback')); });
  await page.locator('#fullscreen').click();
  assert.equal(await page.locator('#player').evaluate(p => p.classList.contains('is-expanded')), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#player').evaluate(p => p.classList.contains('is-expanded')), false);
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(t => SpriteTheater.seek(t, false), firstCue.at + .01);
  await page.waitForFunction(text => document.getElementById('speech').textContent === text, firstCue.text, {timeout:5000});
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  return {frames, fullShowFrames, externalRequests:external.length, pageErrors:errors.length, checks:['full-show','responsive','pause','scrub-paused-playing','reveal-next','scene-select','restart','speed','visibility-event','fullscreen-fallback','reduced-motion']};
}

(async () => {
  fs.mkdirSync(output, {recursive:true});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const results = [];
  try {
    for (const name of (process.env.TEST_BROWSERS || 'chromium,firefox,webkit').split(',')) {
      const browser = await pw[name].launch(name === 'chromium' ? {channel:'chrome',headless:true} : {headless:true});
      try {
        for (const url of [pathToFileURL(path.join(root, 'index.html')).href, base + '/', base + '/stage/']) {
          const context = await browser.newContext({viewport:{width:1440,height:1000}});
          try {
            if (url.startsWith('file:') && name !== 'webkit') await context.setOffline(true);
            results.push({browser:name, url, passed:true, ...await checkPage(await context.newPage(), name, url, base)});
          } catch (e) { results.push({browser:name,url,passed:false,error:e.message}); }
          finally { await context.close(); }
        }
        // Error/retry is tested through HTTP so interception works in every engine.
        const context = await browser.newContext();
        try {
          const page = await context.newPage();
          await page.route('**/assets/letter.png', r => r.abort());
          await page.goto(base + '/');
          await page.waitForFunction(() => document.documentElement.dataset.ready === 'error');
          assert.match(await page.locator('#load-status').textContent(), /letter/);
          await page.waitForTimeout(200);
          assert.equal(await page.locator('#start').isEnabled(), true);
          await page.unroute('**/assets/letter.png');
          await page.locator('#start').click();
          await page.waitForFunction(() => SpriteTheater.ready);
          results.push({browser:name,passed:true,check:'missing-asset-retry'});
        } finally { await context.close(); }
      } finally { await browser.close(); }
    }
  } finally {
    server.close();
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(results,null,2) + '\n');
  }
  console.log(JSON.stringify(results, null, 2));
  if (results.some(r => !r.passed)) process.exitCode = 1;
})().catch(e => { server.close(); console.error(e); process.exitCode=1; });
