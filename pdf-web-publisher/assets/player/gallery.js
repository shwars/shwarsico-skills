(() => {
  "use strict";
  const { h, icon, metadata, notice, init } = window.PDFWebPublisher;
  const state = init();
  if (!state) return;
  const { catalog, main } = state;
  document.title = catalog.site.title;

  const header = h("header", "archive-header");
  const titleBlock = h("div", "archive-title-block");
  titleBlock.append(h("h1", "archive-title", catalog.site.title));
  const total = catalog.presentations.length;
  titleBlock.append(h("p", "archive-summary", `${total} ${total === 1 ? "presentation" : "presentations"} · Open a talk to explore its slides.`));
  header.append(titleBlock);
  const searchGroup = h("div", "search-group");
  const label = h("label", "search-label", "Find a presentation");
  label.htmlFor = "archive-search";
  const searchBox = h("div", "search-box");
  const search = h("input");
  search.type = "search";
  search.id = "archive-search";
  search.placeholder = "Title, speaker, event or tag";
  search.autocomplete = "off";
  searchBox.append(icon("search"), search);
  searchGroup.append(label, searchBox);
  header.append(searchGroup);
  main.append(header);

  const resultStatus = h("p", "result-status");
  resultStatus.setAttribute("role", "status");
  const list = h("ol", "deck-list");
  list.setAttribute("aria-label", "Presentations");
  const empty = h("div", "empty-state");
  empty.hidden = true;
  main.append(resultStatus, list, empty);

  const entries = catalog.presentations.map((entry, index) => {
    const row = h("li", "deck-entry");
    const link = h("a", "deck-link");
    link.href = entry.href;
    const ordinal = h("span", "deck-ordinal", String(index + 1).padStart(2, "0"));
    ordinal.setAttribute("aria-hidden", "true");
    const cover = h("div", "deck-cover");
    const image = h("img");
    image.src = new URL(entry.cover, link.href).href;
    image.alt = "";
    image.loading = index < 3 ? "eager" : "lazy";
    image.draggable = false;
    image.addEventListener("contextmenu", (event) => event.preventDefault());
    image.addEventListener("error", () => {
      cover.replaceChildren(h("span", "cover-missing", "Cover unavailable"));
    }, { once: true });
    cover.append(image);
    const details = h("div", "deck-details");
    details.append(h("h2", "deck-title", entry.title));
    const meta = metadata(entry);
    if (meta) details.append(h("p", "deck-meta", meta));
    if (entry.description) details.append(h("p", "deck-description", entry.description));
    const footer = h("div", "deck-footer");
    footer.append(h("span", "slide-total", `${entry.slide_count} ${entry.slide_count === 1 ? "slide" : "slides"}`));
    for (const tag of entry.tags || []) footer.append(h("span", "tag", tag));
    details.append(footer);
    const open = h("span", "deck-open");
    open.append(h("span", "open-label", "View slides"), icon("arrow"));
    link.append(ordinal, cover, details, open);
    row.append(link);
    list.append(row);
    const terms = [entry.title, entry.speaker, entry.event, entry.date, entry.description, ...(entry.tags || [])]
      .filter(Boolean).join(" ").normalize("NFKC").toLocaleLowerCase();
    return { row, terms };
  });

  search.addEventListener("input", () => {
    const words = search.value.normalize("NFKC").toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const { row, terms } of entries) {
      row.hidden = !words.every((word) => terms.includes(word));
      if (!row.hidden) visible++;
    }
    resultStatus.textContent = words.length ? `${visible} ${visible === 1 ? "presentation" : "presentations"} found` : "";
    empty.hidden = visible > 0;
    empty.replaceChildren(h("h2", "empty-title", total ? "No matching presentations" : "Your archive is ready"),
      h("p", "muted", total ? "Try a title, a speaker, or a different tag." : "Publish a PDF to add the first presentation."));
  });
  search.dispatchEvent(new Event("input"));
  if (!total) searchGroup.hidden = true;
  const footer = h("footer", "archive-footer");
  footer.append(h("span", "footer-title", catalog.site.title), h("span", "muted", "An archive of ideas, one slide at a time."));
  main.append(footer);
})();
