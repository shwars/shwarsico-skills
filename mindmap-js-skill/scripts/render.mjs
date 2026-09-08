#!/usr/bin/env node
import { execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, stat, unlink, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, extname, join, resolve } from 'node:path';
import { parseArgs, promisify } from 'node:util';

const usage = `Render Markmap Markdown to interactive HTML.

Usage: node scripts/render.mjs <input.md> --output <output.html> --assets <offline|cdn> [--style <style.css>]

Requires Node.js 20+ and dependencies installed with npm ci in the skill directory.
Paths are relative to the current working directory. Output directories are created.
Offline embeds rendering libraries; external content resources may still require internet.
The output is replaced only after successful generation. No browser is opened.`;

const defaultStyle = `
html, body { margin: 0; width: 100%; height: 100%; }
html { background: #ffffff; }
body { background: inherit; }
svg#mindmap { display: block; width: 100vw; height: 100vh; }
#mindmap.markmap { --markmap-font: 400 16px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
`;

async function main() {
  const { values, positionals } = parseArgs({
    options: {
      output: { type: 'string', short: 'o' },
      assets: { type: 'string' },
      style: { type: 'string' },
      help: { type: 'boolean', short: 'h' },
    },
    allowPositionals: true,
    strict: true,
  });
  if (values.help) {
    console.log(usage);
    return;
  }
  if (positionals.length !== 1 || !values.output || !['offline', 'cdn'].includes(values.assets)) {
    throw new Error(`Specify one input, --output, and --assets offline|cdn.\n\n${usage}`);
  }
  const input = resolve(positionals[0]);
  const output = resolve(values.output);
  if (!['.html', '.htm'].includes(extname(output).toLowerCase())) {
    throw new Error('Output must have an .html or .htm extension.');
  }
  if (input === output) throw new Error('Input and output must be different files.');
  const inputStat = await stat(input).catch(() => {
    throw new Error(`Cannot read input: ${input}. Check that the file exists and is accessible.`);
  });
  if (!inputStat.isFile() || !(await readFile(input, 'utf8')).trim()) {
    throw new Error('Input must be a non-empty text/Markdown file.');
  }

  let css = defaultStyle;
  if (values.style) {
    const stylePath = resolve(values.style);
    if (stylePath === output) throw new Error('Stylesheet and output must be different files.');
    css += `\n${await readFile(stylePath, 'utf8')}`;
  }
  if (/<\/style\b/i.test(css)) {
    throw new Error('Stylesheet must contain CSS only, without closing </style> tags.');
  }

  const require = createRequire(import.meta.url);
  let cli;
  try {
    const packagePath = require.resolve('markmap-cli/package.json');
    const pkg = JSON.parse(await readFile(packagePath, 'utf8'));
    cli = join(dirname(packagePath), pkg.bin.markmap);
    await stat(cli);
  } catch {
    throw new Error('Markmap CLI is missing or incomplete. Run npm ci --ignore-scripts --no-audit --no-fund in the mindmap-js-skill directory.');
  }

  await mkdir(dirname(output), { recursive: true });
  const temporary = join(dirname(output), `.markmap-${randomUUID()}.html`);
  try {
    const args = [cli, input, '--no-open', '--output', temporary];
    if (values.assets === 'offline') args.push('--offline');
    try {
      await promisify(execFile)(process.execPath, args, {
        windowsHide: true,
        timeout: 120_000,
        maxBuffer: 4 * 1024 * 1024,
        env: { ...process.env, NO_UPDATE_NOTIFIER: '1' },
      });
    } catch (error) {
      const detail = error.stderr?.trim() || error.message;
      throw new Error(`Markmap rendering failed (${values.assets} mode). Check the Markdown/frontmatter and network access for assets. No asset-mode fallback was attempted.\n${detail}`);
    }
    let html = await readFile(temporary, 'utf8');
    if (!/<\/head>/i.test(html) || !/<svg\b/i.test(html)) {
      throw new Error('Markmap returned unexpected HTML without a head or SVG canvas.');
    }
    // A replacer function preserves literal dollar signs in user-provided CSS.
    html = html.replace(/<\/head>/i, () => `<style id="mindmap-skill-style">${css}</style>\n</head>`);
    // The user's selected theme should not change with the viewer's OS theme.
    html = html.replace(/<\/body>/i, '<script>document.documentElement.classList.remove("markmap-dark");</script>\n</body>');
    await writeFile(temporary, html, 'utf8');
    await rename(temporary, output);
  } finally {
    await unlink(temporary).catch((error) => {
      if (error.code !== 'ENOENT') throw error;
    });
  }
  console.log(`Rendered ${values.assets} HTML: ${output}`);
}

main().catch((error) => {
  console.error(`mindmap: ${error.message}`);
  process.exitCode = 1;
});
