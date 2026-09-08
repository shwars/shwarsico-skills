import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFile, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const helper = join(root, 'scripts', 'render.mjs');
const fixture = join(root, 'tests', 'fixtures', 'sample.md');
const run = (args, cwd) => spawnSync(process.execPath, [helper, ...args], {
  cwd, encoding: 'utf8', windowsHide: true, timeout: 150_000,
});

async function workspace(t) {
  const base = resolve(tmpdir());
  const folder = await mkdtemp(join(base, 'mindmap-test-'));
  t.after(async () => {
    // Restrict recursive cleanup to the exact temporary workspace we created.
    assert.ok(resolve(folder).startsWith(base + sep));
    await rm(folder, { recursive: true, force: true });
  });
  return folder;
}

test('help works and missing/invalid asset choices fail without output', async (t) => {
  const cwd = await workspace(t);
  assert.equal(run(['--help'], cwd).status, 0);
  for (const assets of [[], ['--assets', 'automatic']]) {
    const result = run([fixture, '--output', 'map.html', ...assets], cwd);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /--assets offline\|cdn/);
  }
  assert.deepEqual(await readdir(cwd), []);
});

test('renders from another cwd with spaces, Cyrillic, custom CSS and preserved input', async (t) => {
  const cwd = await workspace(t);
  const input = join(cwd, 'учебная карта.md');
  const output = join(cwd, 'готовая карта.html');
  const source = await readFile(fixture, 'utf8');
  await writeFile(input, source);
  await writeFile(output, 'old map to replace');
  await writeFile(join(cwd, 'theme.css'), 'body { background: #fffaf0; }\n/* $& must stay literal */');
  const result = run([input, '-o', output, '--assets', 'cdn', '--style', 'theme.css'], cwd);
  assert.equal(result.status, 0, result.stderr);
  const html = await readFile(output, 'utf8');
  assert.match(html, /<svg\b/);
  assert.match(html, /<script[^>]+src="https:\/\//);
  const decoded = html.replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(parseInt(hex, 16)));
  assert.match(decoded, /Бюджет: до 2 млн ₽/);
  assert.match(html, /markmap-toolbar/);
  assert.match(html, /background: #fffaf0/);
  assert.ok(html.includes('/* $& must stay literal */'));
  assert.equal(await readFile(input, 'utf8'), source);
  assert.equal((await readdir(cwd)).some((name) => name.startsWith('.markmap-')), false);
});

test('offline mode embeds scripts and styles instead of CDN dependencies', async (t) => {
  const cwd = await workspace(t);
  const result = run([fixture, '-o', 'offline.html', '--assets', 'offline'], cwd);
  assert.equal(result.status, 0, result.stderr);
  const html = await readFile(join(cwd, 'offline.html'), 'utf8');
  assert.doesNotMatch(html, /<script[^>]+src=/i);
  assert.doesNotMatch(html, /<link[^>]+rel="stylesheet"/i);
  assert.match(html, /https:\/\/markmap.js.org\//); // Content links remain usable.
});

test('missing dependencies explain how to install them', async (t) => {
  const cwd = await workspace(t);
  const isolatedHelper = join(cwd, 'render.mjs');
  await copyFile(helper, isolatedHelper);
  const result = spawnSync(process.execPath, [isolatedHelper, fixture, '-o', 'map.html', '--assets', 'cdn'], {
    cwd, encoding: 'utf8', windowsHide: true,
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /npm ci --ignore-scripts/);
});

test('invalid source preserves an existing output and reports useful errors', async (t) => {
  const cwd = await workspace(t);
  await writeFile(join(cwd, 'map.html'), 'previous map');
  await writeFile(join(cwd, 'empty.md'), ' \n');
  for (const input of ['missing.md', 'empty.md']) {
    const result = run([input, '-o', 'map.html', '--assets', 'offline'], cwd);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Cannot read input|non-empty/);
    assert.equal(await readFile(join(cwd, 'map.html'), 'utf8'), 'previous map');
  }
});
