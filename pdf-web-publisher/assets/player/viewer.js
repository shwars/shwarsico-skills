(() => {
  "use strict";
  const { h, icon, button, metadata, notice, init } = window.PDFWebPublisher;
  const state = init();
  if (!state) return;
  const { main, catalog } = state;
  const deck = window.PDFWebPublisherDeck;
  const entry = deck && catalog.presentations.find((item) => item.slug === deck.slug);
  if (!entry || deck.version !== 1 || !Array.isArray(deck.slides) || !deck.slides.length) {
    main.append(notice("Presentation data could not be loaded. Keep this deck with its shared player and catalog, or run rebuild."));
    return;
  }
  document.title = `${entry.title} · ${catalog.site.title}`;
  const header = h("header", "viewer-header");
  const back = h("a", "back-link");
  back.href = "../index.html";
  back.append(icon("back"), h("span", "", catalog.site.title));
  const heading = h("div", "viewer-heading");
  heading.append(h("h1", "viewer-title", entry.title));
  const meta = metadata(entry);
  if (meta) heading.append(h("p", "viewer-meta", meta));
  header.append(back, heading);
  main.append(header);

  const player = h("section", "player");
  player.setAttribute("aria-label", "Slide viewer");
  const stage = h("div", "slide-stage");
  stage.tabIndex = 0;
  stage.setAttribute("aria-label", "Slide. Use left and right arrow keys to navigate.");
  const canvas = h("canvas", "slide-canvas");
  canvas.setAttribute("role", "img");
  const loading = h("p", "slide-loading", "Loading slide…");
  loading.setAttribute("role", "status");
  const error = h("div", "slide-error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const errorText = h("p");
  const retry = button("Retry loading slide", "retry", "control text-control");
  retry.append(h("span", "", "Retry"));
  error.append(errorText, retry);
  stage.append(canvas, loading, error);
  stage.addEventListener("contextmenu", (event) => event.preventDefault());
  stage.addEventListener("dragstart", (event) => event.preventDefault());

  const controls = h("div", "viewer-controls");
  const navigation = h("div", "slide-navigation");
  const previous = button("Previous slide (Left arrow)", "back");
  previous.id = "previous-slide";
  const counter = h("span", "slide-counter");
  counter.setAttribute("role", "status");
  counter.setAttribute("aria-live", "polite");
  const next = button("Next slide (Right arrow)", "arrow");
  next.id = "next-slide";
  navigation.append(previous, counter, next);
  const tools = h("div", "viewer-tools");
  const thumbnailsButton = button("Show thumbnails (T)", "grid", "control text-control");
  thumbnailsButton.append(h("span", "control-label", "Slides"));
  thumbnailsButton.setAttribute("aria-expanded", "false");
  thumbnailsButton.setAttribute("aria-controls", "thumbnails");
  const fullscreen = button("Enter fullscreen (F)", "expand", "control text-control");
  fullscreen.append(h("span", "control-label", "Fullscreen"));
  fullscreen.setAttribute("aria-pressed", "false");
  tools.append(thumbnailsButton, fullscreen);
  controls.append(navigation, tools);
  const progress = h("div", "slide-progress");
  progress.setAttribute("aria-hidden", "true");
  const progressFill = h("div", "slide-progress-fill");
  progress.append(progressFill);
  const thumbnails = h("div", "thumbnail-panel");
  thumbnails.id = "thumbnails";
  thumbnails.hidden = true;
  const thumbHeader = h("div", "thumbnail-header");
  thumbHeader.append(h("h2", "", "All slides"));
  const closeThumbnails = button("Close thumbnails", "close");
  thumbHeader.append(closeThumbnails);
  const thumbList = h("ol", "thumbnail-list");
  thumbnails.append(thumbHeader, thumbList);
  player.append(stage, progress, controls, thumbnails);
  main.append(player);
  const hint = h("p", "viewer-hint", "Arrow keys to navigate · T for thumbnails · F for fullscreen");
  main.append(hint);
  const printNotice = h("p", "print-notice", "This presentation is available for on-screen viewing.");
  main.append(printNotice);

  let current = 0;
  let requestId = 0;
  const cache = new Map();
  let thumbButtons = [];
  let touchStart = null;
  let previousFocus = null;
  let inertSiblings = [];
  const context = canvas.getContext("2d");
  if (!context) {
    stage.replaceChildren(notice("This browser cannot display canvas slides. Open the archive in a current browser."));
    return;
  }

  function slideFromHash() {
    const match = /^#slide=(\d+)$/.exec(location.hash);
    return match ? Math.max(0, Math.min(deck.slides.length - 1, Number(match[1]) - 1)) : 0;
  }
  function updateHash() {
    const hash = `#slide=${current + 1}`;
    if (location.hash === hash) return;
    try { history.replaceState(null, "", hash); }
    catch (_) { location.hash = hash; }
  }
  function load(index) {
    if (cache.has(index)) return cache.get(index);
    const promise = new Promise((resolve, reject) => {
      const image = new Image();
      // No crossOrigin attribute: local file images may be drawn but not read back.
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("image unavailable"));
      image.src = deck.slides[index].src;
    });
    cache.set(index, promise);
    promise.catch(() => { if (cache.get(index) === promise) cache.delete(index); });
    return promise;
  }
  async function show(index, force = false) {
    index = Math.max(0, Math.min(deck.slides.length - 1, index));
    if (!force && index === current && requestId) return;
    current = index;
    const token = ++requestId;
    const slide = deck.slides[index];
    updateHash();
    counter.textContent = `${index + 1} / ${deck.slides.length}`;
    previous.disabled = index === 0;
    next.disabled = index === deck.slides.length - 1;
    progressFill.style.transform = `scaleX(${(index + 1) / deck.slides.length})`;
    canvas.hidden = true;
    canvas.setAttribute("aria-label", `Slide ${index + 1} of ${deck.slides.length}`);
    loading.hidden = false;
    error.hidden = true;
    stage.setAttribute("aria-busy", "true");
    for (let number = 0; number < thumbButtons.length; number++) {
      thumbButtons[number].setAttribute("aria-current", number === current ? "true" : "false");
    }
    try {
      const image = await load(index);
      if (token !== requestId) return;
      canvas.width = slide.width;
      canvas.height = slide.height;
      context.drawImage(image, 0, 0, slide.width, slide.height);
      canvas.hidden = false;
      loading.hidden = true;
      error.hidden = true;
      stage.setAttribute("aria-busy", "false");
      for (const neighbor of [index - 1, index + 1]) {
        if (neighbor >= 0 && neighbor < deck.slides.length) load(neighbor).catch(() => {});
      }
      for (const key of cache.keys()) if (Math.abs(key - current) > 2) cache.delete(key);
    } catch (_) {
      if (token !== requestId) return;
      loading.hidden = true;
      error.hidden = false;
      stage.setAttribute("aria-busy", "false");
      errorText.textContent = `Slide ${index + 1} could not be loaded. Keep the slides folder with this presentation, then retry.`;
    }
  }
  function toggleThumbnails(force) {
    const open = force === undefined ? thumbnails.hidden : force;
    if (open && !thumbButtons.length) {
      thumbButtons = deck.slides.map((slide, index) => {
        const row = h("li");
        const thumb = button(`Go to slide ${index + 1}`, null, "thumbnail-button");
        const image = h("img");
        image.src = slide.thumbnail;
        image.alt = "";
        image.loading = "lazy";
        image.draggable = false;
        image.addEventListener("contextmenu", (event) => event.preventDefault());
        image.addEventListener("error", () => {
          image.hidden = true;
          thumb.classList.add("thumbnail-missing");
        });
        thumb.append(image, h("span", "", String(index + 1)));
        thumb.addEventListener("click", () => {
          show(index);
          toggleThumbnails(false);
          stage.focus({ preventScroll: true });
        });
        row.append(thumb);
        thumbList.append(row);
        return thumb;
      });
    }
    thumbnails.hidden = !open;
    thumbnailsButton.setAttribute("aria-expanded", String(open));
    thumbButtons.forEach((item, index) => item.setAttribute("aria-current", index === current ? "true" : "false"));
    if (open) thumbButtons[current].focus({ preventScroll: true });
    else if (thumbnails.contains(document.activeElement)) thumbnailsButton.focus({ preventScroll: true });
  }
  function syncFullscreen() {
    const expanded = Boolean(document.fullscreenElement) || player.classList.contains("is-expanded");
    fullscreen.setAttribute("aria-pressed", String(expanded));
    fullscreen.setAttribute("aria-label", expanded ? "Exit fullscreen (F)" : "Enter fullscreen (F)");
    fullscreen.title = fullscreen.getAttribute("aria-label");
    fullscreen.replaceChildren(icon(expanded ? "collapse" : "expand"), h("span", "control-label", expanded ? "Exit fullscreen" : "Fullscreen"));
    document.body.classList.toggle("expanded-view", expanded);
  }
  function enterExpandedView() {
    previousFocus = document.activeElement;
    // Inert every sibling branch on the route from player to body. This removes
    // the obscured header/skip link from both keyboard and accessibility trees.
    for (let branch = player; branch !== document.body; branch = branch.parentElement) {
      for (const sibling of branch.parentElement.children) {
        if (sibling === branch) continue;
        inertSiblings.push([sibling, sibling.getAttribute("inert")]);
        sibling.setAttribute("inert", "");
      }
    }
    player.classList.add("is-expanded");
    player.setAttribute("role", "dialog");
    player.setAttribute("aria-modal", "true");
    stage.focus({ preventScroll: true });
  }
  function leaveExpandedView() {
    player.classList.remove("is-expanded");
    player.removeAttribute("role");
    player.removeAttribute("aria-modal");
    for (const [sibling, previous] of inertSiblings) {
      if (previous === null) sibling.removeAttribute("inert");
      else sibling.setAttribute("inert", previous);
    }
    inertSiblings = [];
    if (previousFocus && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    previousFocus = null;
  }
  function containTab(event) {
    const stops = [...player.querySelectorAll("a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex='-1'])")]
      .filter((node) => node.getClientRects().length && !node.closest("[hidden], [inert]"));
    const first = stops[0];
    const last = stops[stops.length - 1];
    if (!first) return;
    if (!player.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  async function toggleFullscreen() {
    if (document.fullscreenElement) {
      try { await document.exitFullscreen(); } catch (_) { /* Native fullscreen may have ended already. */ }
    } else if (player.classList.contains("is-expanded")) {
      leaveExpandedView();
    } else {
      try {
        if (!player.requestFullscreen) throw new Error("No fullscreen API");
        await player.requestFullscreen();
      } catch (_) {
        enterExpandedView();
      }
    }
    syncFullscreen();
  }
  previous.addEventListener("click", () => show(current - 1));
  next.addEventListener("click", () => show(current + 1));
  retry.addEventListener("click", () => { cache.delete(current); show(current, true); });
  thumbnailsButton.addEventListener("click", () => toggleThumbnails());
  closeThumbnails.addEventListener("click", () => toggleThumbnails(false));
  fullscreen.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", syncFullscreen);
  window.addEventListener("hashchange", () => show(slideFromHash()));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Tab" && player.classList.contains("is-expanded")) containTab(event);
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest("input, textarea, select, [contenteditable='true']")) return;
    const key = event.key.toLowerCase();
    if (["arrowright", "pagedown", "arrowleft", "pageup", "home", "end", "f", "t"].includes(key)) event.preventDefault();
    if (key === "arrowright" || key === "pagedown") show(current + 1);
    else if (key === "arrowleft" || key === "pageup") show(current - 1);
    else if (key === "home") show(0);
    else if (key === "end") show(deck.slides.length - 1);
    else if (key === "f") toggleFullscreen();
    else if (key === "t") toggleThumbnails();
    else if (key === "escape") {
      if (!thumbnails.hidden) toggleThumbnails(false);
      if (player.classList.contains("is-expanded")) {
        leaveExpandedView();
        syncFullscreen();
      }
    }
  });
  stage.addEventListener("touchstart", (event) => {
    touchStart = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null;
  }, { passive: true });
  stage.addEventListener("touchend", (event) => {
    if (!touchStart || !event.changedTouches.length) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.4) show(current + (dx < 0 ? 1 : -1));
    touchStart = null;
  }, { passive: true });
  stage.addEventListener("touchcancel", () => { touchStart = null; }, { passive: true });
  show(slideFromHash(), true);
})();
