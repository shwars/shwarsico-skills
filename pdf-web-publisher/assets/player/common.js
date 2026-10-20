/* Shared classic script: deliberately compatible with file:// viewing. */
(() => {
  "use strict";
  const paths = {
    arrow: "M5 12h14m-6-6 6 6-6 6",
    back: "M19 12H5m6-6-6 6 6 6",
    search: "m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
    expand: "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5",
    collapse: "M3 8h5V3m8 0v5h5M8 21v-5H3m18 0h-5v5",
    grid: "M3 3h7v7H3Zm11 0h7v7h-7ZM3 14h7v7H3Zm11 0h7v7h-7Z",
    close: "m6 6 12 12M6 18 18 6",
    retry: "M3 10a9 9 0 1 1 1 7M3 3v7h7",
  };
  function h(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.65");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("icon");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", paths[name]);
    svg.append(path);
    return svg;
  }
  function button(label, glyph, className = "control") {
    const node = h("button", className);
    node.type = "button";
    node.setAttribute("aria-label", label);
    node.title = label;
    if (glyph) node.append(icon(glyph));
    return node;
  }
  function formatDate(value) {
    if (!value) return "";
    const parsed = new Date(`${value}T12:00:00`);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en", {
      day: "numeric", month: "short", year: "numeric",
    });
  }
  function metadata(entry) {
    return [entry.speaker, entry.event, formatDate(entry.date)].filter(Boolean).join(" · ");
  }
  function notice(message) {
    const node = h("p", "notice", message);
    node.setAttribute("role", "alert");
    return node;
  }
  function init() {
    const catalog = window.PDFWebPublisherCatalog;
    const main = document.getElementById("main");
    if (!catalog || catalog.version !== 1 || !Array.isArray(catalog.presentations)) {
      main.replaceChildren(notice("Archive data could not be loaded. Keep the whole presentations folder together, or run rebuild."));
      return null;
    }
    const themes = ["programme", "screening-room", "field-notes"];
    document.documentElement.dataset.theme = themes.includes(catalog.site.theme) ? catalog.site.theme : "programme";
    main.replaceChildren();
    return { catalog, main };
  }
  window.PDFWebPublisher = { h, icon, button, formatDate, metadata, notice, init };
})();
