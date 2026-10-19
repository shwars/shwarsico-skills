(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const dom = Object.fromEntries(['player','stage','stage-frame','canvas','dialogue','speaker','speech','bubble-tail',
    'spoken-line','stage-overlay','overlay-title','load-status','load-progress','start','curtain-cover',
    'appointment','timeline','time-label','scene-title','scene-counter','play','next','restart','speed',
    'fullscreen','player-status','scene-marks'].map(id => [id, $(id)]));
  const controls = document.querySelectorAll('.playback-panel button, .playback-panel input, .playback-panel select');
  let sceneButtons = [];
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = matchMedia('(max-width: 767px)');
  let playback, renderer, ready = false, frameId = 0, previousTime = 0;
  let lastCueId = null, lastVisible = -1, lastStatus = '', lastOverlay = '';
  let dragging = false, resumeAfterDrag = false, pausedByVisibility = false;
  let dialogueHeight = 0, dialogueWidth = 0, lastLayoutWidth = 0, expanded = false;
  let loadAttempt = 0;

  function configure(story) {
    document.title = story.title;
    document.querySelector('h1').textContent = story.title;
    document.querySelector('.page-heading div p').textContent = story.subtitle || '';
    const total = story.scenes.reduce((n, s) => n + s.duration, 0);
    document.querySelector('.running-time').textContent = `${story.scenes.length} сцен · ${SpriteEngine.formatTime(total)}`;
    dom.timeline.max = total;
    dom.canvas.setAttribute('aria-label', `${story.title}. ${story.subtitle || 'Кукольный спектакль.'}`);
    dom.stage.style.setProperty('--stage-ratio', `${story.stage.width}/${story.stage.height}`);
    document.documentElement.style.setProperty('--stage-aspect', story.stage.width / story.stage.height);
    const tokens = { paper: '--paper', ink: '--ink', gold: '--brass', curtain: '--velvet' };
    Object.entries(story.presentation?.theme || {}).forEach(([key, value]) => {
      if (tokens[key]) document.documentElement.style.setProperty(tokens[key], value);
    });
    const nav = document.querySelector('.scene-nav');
    nav.replaceChildren();
    sceneButtons = story.scenes.map((scene, index) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'scene-button'; button.dataset.scene = index;
      const number = document.createElement('span'); number.className = 'scene-number'; number.textContent = index + 1;
      const title = document.createElement('span'); title.textContent = scene.title;
      button.append(number, title); button.disabled = true;
      button.addEventListener('click', () => action(() => playback.selectScene(index)));
      nav.append(button); return button;
    });
    const notes = document.getElementById('adaptation-notes');
    notes.replaceChildren();
    (story.adaptation_notes || []).forEach(note => {
      const p = document.createElement('p'); p.textContent = note; notes.append(p);
    });
  }

  function status(text) {
    if (lastStatus !== text) { dom['player-status'].textContent = text; lastStatus = text; }
  }
  function invalidate() { if (ready && !frameId) frameId = requestAnimationFrame(tick); }
  function action(callback) {
    if (!ready) return;
    pausedByVisibility = false;
    callback(); previousTime = 0; invalidate();
  }

  async function loadFonts() {
    const link = document.querySelector('link[href="assets/fonts/fonts.css"]');
    if (!link) throw new Error('Не найдена таблица шрифтов. Проверьте assets/fonts.');
    if (!link.sheet) await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Не загрузилась таблица шрифтов. Проверьте assets/fonts/fonts.css.')), 10000);
      link.addEventListener('load', () => { clearTimeout(timer); resolve(); }, {once:true});
      link.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Не загрузилась таблица шрифтов.')); }, {once:true});
    });
    await document.fonts.ready;
    const faces = await Promise.all([document.fonts.load('20px "PT Sans"'), document.fonts.load('700 20px "PT Sans"')]);
    if (faces.some(a => !a.length)) throw new Error('Не загрузился шрифт. Проверьте папку assets/fonts.');
  }

  async function load() {
    const attempt = ++loadAttempt;
    let failed = false;
    document.documentElement.dataset.ready = 'loading';
    ready = false; dom.start.disabled = true; dom['load-progress'].hidden = false;
    dom['load-progress'].value = 0;
    dom.start.querySelector('span').textContent = 'Начать спектакль';
    dom['overlay-title'].textContent = 'Занавес скоро откроется';
    dom['load-status'].textContent = 'Готовим сцену…';
    try {
      if (!globalThis.SpriteTheaterData || !globalThis.SpriteEngine || !globalThis.SpriteRenderer) {
        throw new Error('Не удалось прочитать файлы приложения. Скопируйте папку целиком и откройте index.html снова.');
      }
      const { story, manifest } = SpriteTheaterData;
      configure(story);
      playback = new SpriteEngine.Playback(story);
      const images = {}, total = Object.keys(manifest.assets).length + 1;
      let loaded = 0;
      dom['load-progress'].max = total;
      const progress = () => {
        if (failed || attempt !== loadAttempt) return;
        loaded++; dom['load-progress'].value = loaded;
        dom['load-status'].textContent = `Готовим сцену: ${loaded} из ${total}`;
      };
      const imageLoads = Object.entries(manifest.assets).map(([id, asset]) => new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => { images[id] = image; progress(); resolve(); };
        image.onerror = () => reject(new Error(`Не загрузилось изображение «${id}». Проверьте, что папка assets находится рядом с index.html.`));
        image.src = asset.file;
      }));
      const fontLoad = loadFonts().then(progress);
      await Promise.all([...imageLoads, fontLoad]);
      if (attempt !== loadAttempt) return;
      renderer = new SpriteRenderer(dom.canvas, manifest, images, story);
      renderer.resize(dom.stage.clientWidth);
      dom['scene-marks'].replaceChildren();
      playback.starts.slice(1).forEach(start => {
        const marker = document.createElement('i'); marker.style.left = `${start / playback.total * 100}%`;
        dom['scene-marks'].append(marker);
      });
      controls.forEach(c => { c.disabled = false; }); sceneButtons.forEach(c => { c.disabled = false; });
      dom['curtain-cover'].hidden = true;
      dom['load-progress'].hidden = true;
      dom['load-status'].textContent = `${story.scenes.length} сцен. Без звука. Занимайте места.`;
      dom.start.disabled = false;
      ready = true; lastCueId = null; lastOverlay = ''; resize(); draw();
      document.documentElement.dataset.ready = 'true';
    } catch (error) {
      if (attempt !== loadAttempt) return;
      failed = true;
      dom['overlay-title'].textContent = 'Сцену не удалось подготовить';
      dom['load-status'].textContent = error.message;
      dom['load-progress'].hidden = true;
      dom.start.querySelector('span').textContent = 'Попробовать снова';
      dom.start.querySelector('use').setAttribute('href', '#icon-restart');
      dom.start.disabled = false;
      controls.forEach(c => { c.disabled = true; }); sceneButtons.forEach(c => { c.disabled = true; });
      document.documentElement.dataset.ready = 'error';
    }
  }

  function updateOverlay() {
    const mode = playback.ended ? 'ended' : !playback.started ? 'start' : 'none';
    if (mode === lastOverlay) return;
    lastOverlay = mode;
    dom['stage-overlay'].hidden = mode === 'none';
    dom['stage-overlay'].classList.toggle('is-finished', mode === 'ended');
    if (mode === 'ended') {
      dom['overlay-title'].textContent = playback.story.end_title || 'Занавес';
      dom['load-status'].textContent = 'Занавес';
      dom.start.querySelector('span').textContent = 'Посмотреть ещё раз';
      dom.start.querySelector('use').setAttribute('href', '#icon-restart');
    } else if (mode === 'start') {
      dom['overlay-title'].textContent = 'Занавес скоро откроется';
      dom.start.querySelector('span').textContent = 'Начать спектакль';
      dom.start.querySelector('use').setAttribute('href', '#icon-play');
    }
  }

  function updateDialogue(frame, heads) {
    const cue = frame.cue, stageWidth = dom.stage.clientWidth;
    // The curtain covers dialogue at the opening and close, just as in pygame.
    const show = cue && frame.curtain > .9 && !playback.ended;
    dom.dialogue.hidden = !show;
    if (!show) {
      if (lastCueId !== null) { dom['spoken-line'].textContent = ''; lastCueId = null; }
      return;
    }
    const changed = cue.id !== lastCueId || stageWidth !== lastLayoutWidth;
    if (changed) {
      const character = playback.story.characters[cue.speaker];
      dom.speaker.textContent = character.name;
      dom.dialogue.style.setProperty('--speaker-color', character.color);
      dom.dialogue.classList.toggle('is-narration', cue.speaker === 'narrator');
      dom.speech.textContent = cue.text;
      dom.speech.style.minHeight = '';
      if (!dom.player.classList.contains('has-caption')) {
        const scale = stageWidth / playback.story.stage.width;
        dom.dialogue.style.width = `${Math.min(stageWidth - 32, Math.max(255, 528 * scale))}px`;
        dom.speech.style.fontSize = `${Math.max(16, Math.min(28, 32 * scale))}px`;
        dom.speaker.style.fontSize = `${Math.max(12, Math.min(18, 24 * scale))}px`;
      } else {
        dom.speech.style.fontSize = ''; dom.speaker.style.fontSize = '';
      }
      const speechHeight = dom.speech.getBoundingClientRect().height;
      dom.speech.style.minHeight = `${speechHeight}px`;
      dialogueHeight = dom.dialogue.offsetHeight;
      dialogueWidth = dom.dialogue.offsetWidth;
      if (cue.id !== lastCueId) dom['spoken-line'].textContent = `${character.name}: ${cue.text}`;
      lastCueId = cue.id; lastLayoutWidth = stageWidth; lastVisible = -1;
    }
    const visible = playback.visibleChars(cue, reduceMotion.matches);
    if (visible !== lastVisible) { dom.speech.textContent = Array.from(cue.text).slice(0, visible).join(''); lastVisible = visible; }
    if (!dom.player.classList.contains('has-caption')) {
      const playerBox = dom.player.getBoundingClientRect(), stageBox = dom.stage.getBoundingClientRect();
      const scale = stageWidth / playback.story.stage.width;
      const head = heads.get(cue.speaker);
      const visibleHeads = [...heads.values()].filter(h => h.x > 0 && h.x < playback.story.stage.width);
      const ceiling = Math.min(...visibleHeads.map(h => h.y), playback.story.stage.height);
      const targetX = cue.speaker === 'narrator' ? stageWidth / 2 : (head?.x || playback.story.stage.width / 2) * scale;
      const x = Math.max(12, Math.min(stageWidth - dialogueWidth - 12, targetX - dialogueWidth / 2));
      const y = cue.speaker === 'narrator' ? 24 : Math.max(18, Math.min(head?.y || ceiling, ceiling) * scale - dialogueHeight - 23);
      dom.dialogue.style.left = `${stageBox.left - playerBox.left + x}px`;
      dom.dialogue.style.top = `${stageBox.top - playerBox.top + y}px`;
      dom['bubble-tail'].style.left = `${Math.max(20, Math.min(dialogueWidth - 36, targetX - x - 9))}px`;
    }
  }

  function draw() {
    if (!ready) return;
    const frame = SpriteEngine.stageState(playback, reduceMotion.matches);
    const heads = renderer.draw(frame);
    updateOverlay(); updateDialogue(frame, heads);
    dom['scene-title'].textContent = frame.scene.title;
    dom['scene-counter'].textContent = `Сцена ${frame.index + 1} из ${playback.story.scenes.length}`;
    dom['time-label'].textContent = `${SpriteEngine.formatTime(playback.time)} / ${SpriteEngine.formatTime(playback.total)}`;
    if (!dragging) dom.timeline.value = playback.time;
    dom.timeline.style.setProperty('--progress', `${playback.time / playback.total * 100}%`);
    dom.timeline.setAttribute('aria-valuetext', `${Math.floor(playback.time / 60)} минут ${Math.floor(playback.time % 60)} секунд. ${frame.scene.title}`);
    const label = playback.ended ? 'Ещё раз' : !playback.started ? 'Начать' : playback.paused ? 'Продолжить' : 'Пауза';
    dom.play.querySelector('span').textContent = label;
    dom.play.querySelector('use').setAttribute('href', playback.paused ? '#icon-play' : '#icon-pause');
    sceneButtons.forEach((button, i) => {
      if (i === frame.index) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    const appointment = frame.scene.caption;
    dom.appointment.hidden = !appointment || frame.local < appointment.at || frame.curtain < .9;
    if (!dom.appointment.hidden) dom.appointment.textContent = appointment.text;
    status(pausedByVisibility ? 'Показ приостановлен, пока вы были в другой вкладке. Нажмите «Продолжить».' :
      playback.paused && playback.started && !playback.ended ? 'Пауза. Можно листать реплики и выбирать время.' : '');
  }

  function tick(now) {
    frameId = 0;
    if (!ready) return;
    if (previousTime && !document.hidden) playback.advance(Math.max(0, (now - previousTime) / 1000));
    previousTime = now;
    draw();
    if (!playback.paused && !playback.ended && !document.hidden) invalidate();
  }

  function resize() {
    if (!ready) return;
    dom.player.classList.toggle('has-caption', dom.stage.clientWidth < 840);
    renderer.resize(dom.stage.clientWidth); lastLayoutWidth = 0; previousTime = 0; invalidate();
  }

  function setExpanded(value) {
    expanded = value;
    dom.player.classList.toggle('is-expanded', value);
    document.body.classList.toggle('has-expanded', value);
    dom.fullscreen.setAttribute('aria-pressed', String(value));
    dom.fullscreen.setAttribute('aria-label', value ? 'Выйти из полного экрана' : 'На весь экран');
    dom.fullscreen.querySelector('span').textContent = value ? 'Свернуть' : 'На весь экран';
    dom.fullscreen.querySelector('use').setAttribute('href', value ? '#icon-close' : '#icon-expand');
    requestAnimationFrame(resize);
  }
  async function fullscreen() {
    if (expanded || document.fullscreenElement) {
      if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen().catch(() => {});
      setExpanded(false);
    } else {
      setExpanded(true);
      if (dom.player.requestFullscreen) {
        try { await dom.player.requestFullscreen(); } catch (_) { /* Use the same full-page layout. */ }
      }
    }
  }

  dom.start.addEventListener('click', () => {
    if (!ready) { load(); return; }
    action(() => playback.ended ? playback.restart() : playback.play());
  });
  dom.play.addEventListener('click', () => action(() => playback.toggle()));
  dom.next.addEventListener('click', () => action(() => { playback.started = true; playback.nextCue(reduceMotion.matches); }));
  dom.restart.addEventListener('click', () => action(() => playback.restart()));
  dom.speed.addEventListener('change', () => action(() => playback.setSpeed(Number(dom.speed.value))));
  dom.fullscreen.addEventListener('click', fullscreen);
  sceneButtons.forEach(button => button.addEventListener('click', () => action(() => playback.selectScene(Number(button.dataset.scene)))));

  function startDrag() {
    if (!ready || dragging) return;
    dragging = true; resumeAfterDrag = !playback.paused; playback.pause(); playback.started = true;
    pausedByVisibility = false;
  }
  function endDrag() {
    if (!dragging) return;
    dragging = false;
    if (resumeAfterDrag && !document.hidden && !playback.ended) playback.play();
    resumeAfterDrag = false; previousTime = 0; invalidate();
  }
  dom.timeline.addEventListener('pointerdown', startDrag);
  dom.timeline.addEventListener('input', () => {
    if (!ready) return;
    if (!dragging) startDrag();
    playback.seek(Number(dom.timeline.value)); invalidate();
  });
  dom.timeline.addEventListener('change', endDrag);
  document.addEventListener('pointerup', endDrag);
  document.addEventListener('pointercancel', endDrag);
  dom.timeline.addEventListener('blur', endDrag);

  document.addEventListener('keydown', event => {
    if (!ready || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'Escape') {
      if (expanded) { fullscreen(); event.preventDefault(); }
      return;
    }
    if (event.target.closest('input,select,textarea,[contenteditable=true]')) return;
    if (event.target.closest('button,summary,a') && (event.code === 'Space' || event.key === 'Enter')) return;
    const key = event.key.toLowerCase();
    if (event.code === 'Space') { event.preventDefault(); action(() => playback.toggle()); }
    else if (key === 'arrowright') { event.preventDefault(); action(() => { playback.started = true; playback.nextCue(reduceMotion.matches); }); }
    else if (key === 'r' || key === 'к') action(() => playback.restart());
    else if (/^[1-9]$/.test(key)) action(() => playback.selectScene(Number(key) - 1));
  });
  document.addEventListener('visibilitychange', () => {
    if (!ready) return;
    if (document.hidden) {
      if (!playback.paused || (dragging && resumeAfterDrag)) pausedByVisibility = true;
      playback.pause(); resumeAfterDrag = false;
      if (frameId) cancelAnimationFrame(frameId);
      frameId = 0;
    }
    previousTime = 0;
    if (!document.hidden) invalidate();
  });
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) setExpanded(false);
  });
  new ResizeObserver(resize).observe(dom.stage);
  mobile.addEventListener('change', resize);
  reduceMotion.addEventListener('change', resize);
  // A deterministic rehearsal interface: no persistence, network or pixel readback.
  globalThis.SpriteTheater = {
    get ready() { return ready; },
    get playback() { return playback; },
    seek(seconds, reveal = true) {
      if (!ready) return;
      pausedByVisibility = false;
      playback.started = true; playback.pause(); playback.seek(seconds);
      if (reveal && playback.activeCue()) playback.revealed = playback.activeCue().id;
      previousTime = 0; draw();
    },
    inspect() {
      if (!ready) return { ready: false };
      const frame = SpriteEngine.stageState(playback, reduceMotion.matches);
      return { ready, time: playback.time, paused: playback.paused, speed: playback.speed, ended: playback.ended,
        scene: frame.scene.id, cue: frame.cue?.id || null, mobile: mobile.matches,
        caption: dom.player.classList.contains('has-caption'), reducedMotion: reduceMotion.matches,
        items: frame.items.map(v => ({ id: v.item.id, asset: v.state.asset, visible: v.state.visible, x: v.x, y: v.y })) };
    }
  };
  load();
})();
