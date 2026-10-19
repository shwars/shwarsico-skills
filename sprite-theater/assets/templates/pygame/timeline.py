"""Deterministic puppet timeline. No pygame, file I/O, or wall-clock timers."""
from __future__ import annotations

import math


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_story(story):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(story.get("version") == 1, "Unsupported script version")
    require(isinstance(story.get("title"), str) and story["title"].strip(), "Missing title")
    stage = story.get("stage", {})
    for key in ("width", "height", "chars_per_second", "curtain_seconds"):
        require(number(stage.get(key)) and stage[key] > 0, "Invalid stage." + key)
    require(stage["width"] >= 320 and stage["height"] >= 180, "Stage too small")
    require(int(stage["width"]) == stage["width"] and int(stage["height"]) == stage["height"], "Stage dimensions must be integers")
    require(isinstance(story.get("characters"), dict), "Missing characters")
    for ident, character in story["characters"].items():
        require(bool(ident) and bool(character.get("name")), "Missing character name")
    require(isinstance(story.get("scenes"), list) and story["scenes"], "Script has no scenes")
    scene_ids, cue_ids = set(), set()
    for scene in story["scenes"]:
        sid = scene.get("id")
        require(isinstance(sid, str) and sid and sid not in scene_ids, "Duplicate/missing scene ID")
        scene_ids.add(sid)
        duration = scene.get("duration")
        require(number(duration) and duration > 0, "Invalid scene duration: " + sid)
        require(bool(scene.get("title")) and bool(scene.get("background")), "Missing scene title/background: " + sid)
        require(isinstance(scene.get("actors"), list) and isinstance(scene.get("cues"), list) and isinstance(scene.get("props", []), list), "Scene actors/cues/props must be arrays")
        actors, props = scene["actors"], scene.get("props", [])
        actor_ids = {a.get("id") for a in actors}
        ids = [a.get("id") for a in actors + props]
        require(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), "Duplicate/missing item ID: " + sid)
        require(actor_ids <= story["characters"].keys(), "Unknown character in " + sid)
        end = 0
        for cue in scene.get("cues", []):
            cid = cue.get("id")
            require(isinstance(cid, str) and cid and cid not in cue_ids, "Duplicate/missing cue ID")
            cue_ids.add(cid)
            require(number(cue.get("at")) and cue["at"] >= end and number(cue.get("duration")) and cue["duration"] > 0, "Invalid/overlapping cue: " + cid)
            end = cue["at"] + cue["duration"]
            require(end <= duration, "Cue exceeds scene: " + cid)
            require(isinstance(cue.get("text"), str) and bool(cue["text"].strip()), "Empty cue: " + cid)
            require(cue.get("speaker") in actor_ids or cue.get("speaker") == "narrator", "Speaker missing from scene: " + cid)
            require(cue.get("speaker") in story["characters"], "Missing speaker metadata: " + cid)
            require(isinstance(cue.get("sources", []), list) and all(isinstance(s, str) and s for s in cue.get("sources", [])), "Invalid sources: " + cid)
            require(bool(cue.get("sources")) or cue.get("original") is True, "Missing source or original flag: " + cid)
            require(isinstance(cue.get("adaptation"), str) and bool(cue["adaptation"].strip()), "Missing adaptation note: " + cid)
        for item in actors + props:
            require(bool(item.get("asset")) and number(item.get("height")) and item["height"] > 0 and number(item.get("z")), "Invalid item: " + str(item.get("id")))
            frames = item.get("keyframes", [])
            require(frames and frames[0].get("at") == 0, "First keyframe must be at 0")
            previous = -1
            for frame in frames:
                require(number(frame.get("at")) and previous < frame["at"] <= duration, "Invalid keyframe time")
                previous = frame["at"]
                for key in ("x", "y", "angle", "scale", "width_scale"):
                    if key in frame:
                        require(number(frame[key]), "Invalid " + key)
                        if key in ("scale", "width_scale"):
                            require(frame[key] > 0, "Nonpositive scale")
                for key in ("visible", "flip", "tween"):
                    if key in frame:
                        require(isinstance(frame[key], bool), "Invalid boolean: " + key)
                if "asset" in frame:
                    require(isinstance(frame["asset"], str) and frame["asset"], "Invalid pose")
            for attach in [item.get("attach")] + [f.get("attach") for f in frames if "attach" in f]:
                require(attach is None or (item in props and attach in actor_ids), "Invalid prop attachment")
            for gesture in item.get("gestures", []):
                require(gesture.get("kind") in ("bow", "recoil", "tangle", "lift"), "Unknown gesture")
                require(number(gesture.get("at")) and gesture["at"] >= 0 and number(gesture.get("duration")) and gesture["duration"] > 0 and gesture["at"] + gesture["duration"] <= duration, "Invalid gesture time")
        caption = scene.get("caption")
        if caption:
            require(number(caption.get("at")) and 0 <= caption["at"] <= duration and isinstance(caption.get("text"), str), "Invalid scene caption")
    return story


class Playback:
    def __init__(self, story):
        self.story = validate_story(story)
        self.starts = []
        self.total = 0
        for scene in story["scenes"]:
            self.starts.append(self.total)
            self.total += scene["duration"]
        self.time, self.speed = 0.0, 1.0
        self.paused, self.started, self.revealed = True, False, None

    @property
    def ended(self):
        return self.time >= self.total

    def locate(self):
        for index, start in enumerate(self.starts):
            if self.time < start + self.story["scenes"][index]["duration"]:
                return index, self.story["scenes"][index], self.time - start
        return len(self.starts) - 1, self.story["scenes"][-1], self.story["scenes"][-1]["duration"]

    def active_cue(self):
        _, scene, local = self.locate()
        return next((c for c in scene.get("cues", []) if c["at"] <= local < c["at"] + c["duration"]), None)

    def visible_chars(self, cue, reduced=False):
        if reduced or self.revealed == cue["id"]:
            return len(cue["text"])
        return max(0, min(len(cue["text"]), int((self.locate()[2] - cue["at"]) * self.story["stage"]["chars_per_second"])))

    def seek(self, seconds):
        self.time = max(0.0, min(self.total, seconds if number(seconds) else 0.0))
        self.revealed = None
        if self.ended:
            self.paused = True

    def advance(self, dt):
        if not self.paused and number(dt):
            self.time = max(0.0, min(self.total, self.time + max(0, dt) * self.speed))
            if self.ended:
                self.paused = True

    def play(self):
        if self.ended:
            self.seek(0)
        self.started, self.paused = True, False

    def pause(self):
        self.paused = True

    def toggle(self):
        self.play() if self.paused else self.pause()

    def restart(self):
        self.seek(0)
        self.play()

    def select_scene(self, index):
        if 0 <= index < len(self.starts):
            self.seek(self.starts[index])
            self.play()

    def next_cue(self, reduced=False):
        if self.ended:
            self.restart()
            return
        cue = self.active_cue()
        if cue and self.visible_chars(cue, reduced) < len(cue["text"]):
            self.revealed = cue["id"]
            return
        index, scene, local = self.locate()
        upcoming = next((c for c in scene.get("cues", []) if c["at"] > local + 1e-6), None)
        self.seek(self.starts[index] + upcoming["at"] if upcoming else self.starts[index + 1] if index + 1 < len(self.starts) else self.total)


def item_state(item, local):
    state = dict(asset=item["asset"], x=0, y=.94, scale=1, width_scale=1,
                 angle=0, visible=True, flip=False, attach=item.get("attach"))
    frames, index = item["keyframes"], 0
    for i, frame in enumerate(frames):
        if frame["at"] > local:
            break
        state.update({k: v for k, v in frame.items() if k not in ("at", "tween")})
        index = i
    state["moving"] = False
    if index + 1 < len(frames):
        start, end = frames[index:index + 2]
        u = smooth((local - start["at"]) / (end["at"] - start["at"])) if end.get("tween", True) else 0
        for key in ("x", "y", "angle", "scale", "width_scale"):
            if key in end:
                if key == "x" and abs(end[key] - state[key]) > .025:
                    state["moving"] = 0 < u < 1
                state[key] += (end[key] - state[key]) * u
    return state


def gesture_offset(item, local):
    dx = dy = angle = 0.0
    for gesture in item.get("gestures", []):
        u = (local - gesture["at"]) / gesture["duration"]
        if not 0 <= u <= 1:
            continue
        pulse = math.sin(math.pi * u)
        if gesture["kind"] in ("bow", "lift"):
            angle -= (12 if gesture["kind"] == "bow" else 24) * pulse
            dy += 6 * pulse
        elif gesture["kind"] == "recoil":
            dx += 14 * pulse
            angle += 9 * pulse
        elif gesture["kind"] == "tangle":
            angle += 22 * math.sin(u * math.pi * 6) * pulse
            dx += 20 * math.sin(u * math.pi * 4) * pulse
            dy -= 8 * pulse
    return dx, dy, angle


def stage_state(playback, reduced=False):
    index, scene, local = playback.locate()
    cue, stage = playback.active_cue(), playback.story["stage"]
    width, height = stage["width"], stage["height"]
    actors = {}
    for item in scene.get("actors", []):
        state = item_state(item, local)
        dx, dy, angle = gesture_offset(item, local)
        x, y = state["x"] * width + dx * height / 680, state["y"] * height + dy * height / 680
        if not reduced:
            if state["moving"]:
                y -= abs(math.sin(local * 9)) * 6 * height / 680
                angle += math.sin(local * 9) * 1.2
            else:
                angle += math.sin(local * 1.8 + item["z"]) * .4
            if cue and cue["speaker"] == item["id"]:
                angle += math.sin(local * 5) * .9
        actors[item["id"]] = dict(item=item, state=state, x=x, y=y, angle=angle)
    items = list(actors.values())
    for item in scene.get("props", []):
        state = item_state(item, local)
        parent = actors.get(state["attach"], {})
        items.append(dict(item=item, state=state, x=state["x"] * width + parent.get("x", 0), y=state["y"] * height + parent.get("y", 0), angle=0))
    items.sort(key=lambda value: value["item"]["z"])
    transition = stage["curtain_seconds"]
    curtain = min(smooth(local / transition), smooth((scene["duration"] - local) / transition))
    return dict(index=index, scene=scene, local=local, cue=cue, actors=actors, items=items, curtain=curtain)
