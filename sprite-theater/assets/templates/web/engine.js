(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SpriteEngine = api;
})(globalThis, function () {
  'use strict';
  const WIDTH = 1516, HEIGHT = 680, CPS = 32;
  const clamp = (n, low, high) => Math.max(low, Math.min(high, n));
  const smooth = n => { const t = clamp(n, 0, 1); return t * t * (3 - 2 * t); };
  const formatTime = n => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}`;

  function validateStory(story) {
    if (!story || !Array.isArray(story.scenes) || !story.scenes.length) throw new Error('Сценарий пуст.');
    if (story.version !== 1 || !story.stage || !['width','height','chars_per_second','curtain_seconds'].every(k => Number.isFinite(story.stage[k]) && story.stage[k] > 0)) throw new Error('Неверный формат сцены. Выполните prepare.');
    const scenes = new Set(), cues = new Set();
    for (const scene of story.scenes) {
      if (scenes.has(scene.id) || !(scene.duration > 0)) throw new Error('Неверная сцена.');
      scenes.add(scene.id);
      const actors = new Set(scene.actors.map(a => a.id));
      if (actors.size !== scene.actors.length) throw new Error('Повтор персонажа.');
      let end = 0;
      for (const cue of scene.cues) {
        if (cues.has(cue.id) || cue.at < end || !(cue.duration > 0)) throw new Error(`Неверная реплика ${cue.id}.`);
        if (cue.speaker !== 'narrator' && !actors.has(cue.speaker)) throw new Error('Отсутствует говорящий.');
        if ((!cue.sources?.length && cue.original !== true) || !cue.adaptation) throw new Error('Отсутствует источник или отметка авторской вставки.');
        cues.add(cue.id);
        end = cue.at + cue.duration;
        if (end > scene.duration) throw new Error('Реплика выходит за сцену.');
      }
      for (const item of [...scene.actors, ...(scene.props || [])]) {
        let previous = -1;
        for (const frame of item.keyframes) {
          if (frame.at <= previous || (previous === -1 && frame.at !== 0)) throw new Error('Неверные ключевые кадры.');
          previous = frame.at;
        }
        if (!item.keyframes.length || (item.attach && !actors.has(item.attach))) throw new Error('Неверный реквизит.');
      }
    }
    return story;
  }

  class Playback {
    constructor(story) {
      this.story = validateStory(story);
      this.total = story.scenes.reduce((n, s) => n + s.duration, 0);
      this.starts = story.scenes.map((_, i) => story.scenes.slice(0, i).reduce((n, s) => n + s.duration, 0));
      this.time = 0;
      this.paused = true;
      this.started = false;
      this.speed = 1;
      this.revealed = null;
    }
    get ended() { return this.time >= this.total; }
    locate() {
      const index = this.starts.findIndex((start, i) => this.time < start + this.story.scenes[i].duration);
      const i = index < 0 ? this.story.scenes.length - 1 : index;
      return { index: i, scene: this.story.scenes[i], local: this.time - this.starts[i] };
    }
    activeCue() {
      const { scene, local } = this.locate();
      return scene.cues.find(c => c.at <= local && local < c.at + c.duration) || null;
    }
    visibleChars(cue, reduced = false) {
      if (reduced || this.revealed === cue.id) return Array.from(cue.text).length;
      return clamp(Math.floor((this.locate().local - cue.at) * this.story.stage.chars_per_second), 0, Array.from(cue.text).length);
    }
    seek(time) {
      this.time = clamp(Number.isFinite(time) ? time : 0, 0, this.total);
      this.revealed = null;
      if (this.ended) this.paused = true;
    }
    advance(dt) {
      if (!this.paused && !this.ended && Number.isFinite(dt)) this.seekAdvance(Math.max(0, dt) * this.speed);
    }
    seekAdvance(dt) {
      this.time = clamp(this.time + dt, 0, this.total);
      if (this.ended) this.paused = true;
    }
    play() {
      if (this.ended) this.seek(0);
      this.started = true;
      this.paused = false;
    }
    pause() { this.paused = true; }
    toggle() { this.paused && !this.ended ? this.play() : this.ended ? this.restart() : this.pause(); }
    restart() { this.seek(0); this.play(); }
    selectScene(index) {
      if (this.starts[index] !== undefined) { this.seek(this.starts[index]); this.play(); }
    }
    setSpeed(speed) {
      if (![.75, 1, 1.25, 1.5, 2].includes(speed)) throw new Error('Неверная скорость.');
      this.speed = speed;
    }
    nextCue(reduced = false) {
      if (this.ended) { this.restart(); return; }
      const current = this.activeCue();
      if (current && this.visibleChars(current, reduced) < Array.from(current.text).length) { this.revealed = current.id; return; }
      const { index, scene, local } = this.locate();
      const upcoming = scene.cues.find(c => c.at > local + 1e-6);
      this.seek(upcoming ? this.starts[index] + upcoming.at : (this.starts[index + 1] ?? this.total));
    }
  }

  function itemState(item, local) {
    const state = { asset: item.asset, x: 0, y: .94, scale: 1, width_scale: 1, angle: 0, visible: true, flip: false, attach: item.attach || null };
    let index = 0;
    item.keyframes.forEach((frame, i) => {
      if (frame.at <= local) { const { at, tween, ...values } = frame; Object.assign(state, values); index = i; }
    });
    state.moving = false;
    if (index + 1 < item.keyframes.length) {
      const start = item.keyframes[index], end = item.keyframes[index + 1];
      const u = end.tween === false ? 0 : smooth((local - start.at) / (end.at - start.at));
      for (const key of ['x', 'y', 'angle', 'scale', 'width_scale']) {
        if (key in end) {
          if (key === 'x' && Math.abs(end[key] - state[key]) > .025) state.moving = u > 0 && u < 1;
          state[key] += (end[key] - state[key]) * u;
        }
      }
    }
    return state;
  }

  function gestureOffset(item, local) {
    let dx = 0, dy = 0, angle = 0;
    for (const g of item.gestures || []) {
      const u = (local - g.at) / g.duration;
      if (u < 0 || u > 1) continue;
      const pulse = Math.sin(Math.PI * u);
      if (g.kind === 'bow') { angle -= 12 * pulse; dy += 6 * pulse; }
      else if (g.kind === 'lift') { angle -= 24 * pulse; dy += 6 * pulse; }
      else if (g.kind === 'recoil') { dx += 14 * pulse; angle += 9 * pulse; }
      else if (g.kind === 'tangle') {
        angle += 22 * Math.sin(u * Math.PI * 6) * pulse;
        dx += 20 * Math.sin(u * Math.PI * 4) * pulse;
        dy -= 8 * pulse;
      }
    }
    return { dx, dy, angle };
  }

  function stageState(playback, reduced = false) {
    const { index, scene, local } = playback.locate(), cue = playback.activeCue();
    const { width: WIDTH, height: HEIGHT, curtain_seconds } = playback.story.stage;
    const actors = new Map();
    for (const item of scene.actors) {
      const state = itemState(item, local), gesture = gestureOffset(item, local);
      let x = state.x * WIDTH + gesture.dx * HEIGHT / 680, y = state.y * HEIGHT + gesture.dy * HEIGHT / 680, angle = gesture.angle;
      if (!reduced) {
        if (state.moving) { y -= Math.abs(Math.sin(local * 9)) * 6 * HEIGHT / 680; angle += Math.sin(local * 9) * 1.2; }
        else angle += Math.sin(local * 1.8 + item.z) * .4;
        if (cue?.speaker === item.id) angle += Math.sin(local * 5) * .9;
      }
      actors.set(item.id, { item, state, x, y, angle });
    }
    const items = [...actors.values()];
    for (const item of scene.props || []) {
      const state = itemState(item, local), parent = actors.get(state.attach);
      items.push({ item, state, x: state.x * WIDTH + (parent?.x || 0),
                   y: state.y * HEIGHT + (parent?.y || 0), angle: 0 });
    }
    items.sort((a, b) => a.item.z - b.item.z);
    const curtain = Math.min(smooth(local / curtain_seconds), smooth((scene.duration - local) / curtain_seconds));
    return { index, scene, local, cue, actors, items, curtain };
  }
  return { Playback, validateStory, itemState, gestureOffset, stageState, smooth, clamp, formatTime, WIDTH, HEIGHT, CPS };
});
