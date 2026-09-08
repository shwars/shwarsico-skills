# Mapping, appearance, and exports

## Text into a hierarchy

Use one meaningful root heading, topic headings for major branches, and nested lists for finer detail. Nested lists also avoid Markdown's six-heading-level limit. Group by the source's conceptual relationships; do not imply causality, priority, or chronology unless the source supports it.

- **Concise:** retain central ideas and qualifications; merge repetition and omit secondary examples where meaning survives.
- **Detailed:** retain supporting facts, distinctions, exceptions, and useful examples, but still shorten prose into readable labels.

Keep names, numbers, units, negation, and uncertainty accurate. Preserve supplied links on the relevant nodes. Escape Markdown punctuation when it is literal content. Do not copy source HTML/scripts into labels merely because the source contains them. If the source is incomplete or contradictory, preserve the uncertainty rather than filling gaps.

For large documents, first identify major topics, then map their details. Split maps only when requested or when readability requires it, explaining the split and retaining links between outputs. Do not silently truncate content to meet an arbitrary node limit.

For example, “Пилот стартует в октябре, если завершится аудит. Бюджет — до 2 млн ₽; решение о масштабировании ещё не принято” can become:

```markdown
# Пилот
## Запуск
- Октябрь, если завершится аудит
## Бюджет
- До 2 млн ₽
## Масштабирование
- Решение ещё не принято
```

If a later request changes only the start month, change that node and preserve the audit condition, budget, and undecided status. Reuse the map's detail, asset mode, and appearance choices.

## Appearance

When the user selects readable defaults, prepend:

```yaml
---
markmap:
  colorFreezeLevel: 2
  maxWidth: 300
  initialExpandLevel: -1
---
```

This uses Markmap's colored branches, wraps long labels, and starts expanded. The helper supplies a white background, dark text, a system sans-serif font, a full-window canvas, and the standard toolbar. Fit and zoom make large maps navigable; keep labels concise rather than relying on tiny text.

For custom appearance, use supported frontmatter options such as `color`, `maxWidth`, `spacingHorizontal`, `spacingVertical`, and `initialExpandLevel`. Preserve existing options when editing. Put document-level CSS in a small local file and pass `--style` to embed it after the defaults. For example:

```css
body { background: #fffaf0; }
#mindmap.markmap {
  --markmap-font: 400 18px/1.4 Georgia, serif;
  --markmap-text-color: #262626;
}
```

Markmap injects its own styles into the SVG at runtime. Use the `#mindmap.markmap` selector and its CSS variables so custom typography takes precedence. CSS URLs are resolved relative to the generated HTML, not the original CSS file. Prefer system fonts and inline assets for offline output. Match text and toolbar contrast if using a dark background; custom themes should also account for the toolbar's optional dark-mode toggle. The helper starts in the selected appearance regardless of OS theme. Do not introduce remote font dependencies without considering the chosen asset mode.

## HTML and dependencies

The helper invokes the installed, pinned Markmap CLI with `--no-open`, and adds `--offline` only for offline mode. Rendering uses the CLI's selected CDN in CDN mode. Initial offline generation may fetch assets for embedding; report network failures rather than silently switching modes. `npm ci` restores the locked dependency tree.

Offline verification must load a fresh page with networking disabled. A warm cache is not proof that the file is self-contained. External links can remain links; external resources required to display the map must be embedded or reported as limitations.

## Optional PNG/SVG exports

Use the coding agent's available browser automation or export tools; do not install a browser merely to generate ordinary HTML.

1. Open the HTML, wait for rendering, fonts, and any images, then expand every branch intended for export. Disable transitions or wait for them to finish before measuring.
2. Fit the complete map and check its bounds. A viewport screenshot may omit nodes, or make a large map unreadably small. Resize the canvas/export bounds to include the complete map with padding and a useful text size.
3. **PNG:** capture the map at suitable resolution; verify no labels or branches are clipped. Include the chosen background and omit interactive controls from the image.
4. **SVG:** use a supported SVG export if available, otherwise serialize the rendered SVG with its namespaces, dimensions/viewBox, required styles, and resources. Markmap labels use HTML `foreignObject`; such SVGs may not display correctly in slide or vector applications. Verify in the intended viewer and offer PNG when compatibility fails. Do not call the SVG universally portable or convert labels to paths without a suitable tool.
5. Inspect the exported artifact and deliver it alongside the Markdown/HTML. If the environment cannot export the requested format, explain the missing capability and deliver the working source/HTML without pretending export succeeded.

## Upstream documentation

- [Markmap CLI](https://markmap.js.org/docs/packages--markmap-cli): rendering and offline mode.
- [JSON options](https://markmap.js.org/docs/json-options): frontmatter styling and layout.
- [Markmap FAQ](https://markmap.js.org/docs/faq): headings and nested lists.
