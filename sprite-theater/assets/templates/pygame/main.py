"""Offline paper-puppet player. Story and visuals live in JSON, not this module."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
from functools import lru_cache

from timeline import Playback, stage_state

ROOT = Path(__file__).resolve().parent


def fit_rect(size, container):
    import pygame
    factor = min(container.w / size[0], container.h / size[1])
    rect = pygame.Rect(0, 0, max(1, round(size[0] * factor)), max(1, round(size[1] * factor)))
    rect.center = container.center
    return rect


class Renderer:
    def __init__(self, story):
        import pygame
        self.pg, self.story = pygame, story
        self.manifest = json.loads((ROOT / "assets/manifest.json").read_text(encoding="utf-8"))
        self.size = tuple(story.get("presentation", {}).get("logical_size", [1600, 900]))
        self.canvas = pygame.Surface(self.size)
        self.stage_size = (story["stage"]["width"], story["stage"]["height"])
        self.stage = pygame.Surface(self.stage_size)
        self.stage_rect = fit_rect(self.stage_size, pygame.Rect(32, 90, self.size[0] - 64, self.size[1] - 324))
        theme = story.get("presentation", {}).get("theme", {})
        self.paper = pygame.Color(theme.get("paper", "#f4e8d0"))
        self.ink = pygame.Color(theme.get("ink", "#392a20"))
        self.gold = pygame.Color(theme.get("gold", "#bf9652"))
        self.velvet = pygame.Color(theme.get("curtain", "#6e2433"))
        self.images, self.backgrounds = {}, {}
        for ident, asset in self.manifest["assets"].items():
            image = pygame.image.load(str(ROOT / asset["file"]))
            if asset["kind"] == "background":
                image = image.convert()
                scale = max(self.stage_size[0] / image.get_width(), self.stage_size[1] / image.get_height())
                image = pygame.transform.smoothscale(image, (math.ceil(image.get_width() * scale), math.ceil(image.get_height() * scale)))
                crop = pygame.Rect((image.get_width() - self.stage_size[0]) // 2, image.get_height() - self.stage_size[1], *self.stage_size)
                self.backgrounds[ident] = image.subsurface(crop).copy()
            else:
                left, top, right, bottom = asset["bounds"]
                image = image.convert_alpha().subsurface((left, top, right - left, bottom - top)).copy()
                if image.get_height() > 600:
                    image = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * 600 / image.get_height())), 600))
                self.images[ident] = image
        self.buttons = []
        self.timeline_rect = pygame.Rect(32, self.size[1] - 186, self.size[0] - 64, 20)
        self.last_bubble_rect = None
        self.curtain = pygame.Surface((math.ceil(self.stage_size[0] / 2), self.stage_size[1]))
        for x in range(self.curtain.get_width()):
            fold = .7 + .3 * (.5 + .5 * math.cos(x / 31)) ** .6
            color = tuple(round(c * fold) for c in self.velvet[:3])
            pygame.draw.line(self.curtain, color, (x, 0), (x, self.stage_size[1]))
        pygame.draw.line(self.curtain, self.gold, (0, self.stage_size[1] - 10), (self.curtain.get_width(), self.stage_size[1] - 10), 3)

    @lru_cache(maxsize=48)
    def font(self, size, bold=False):
        return self.pg.font.Font(str(ROOT / self.manifest["fonts"]["bold" if bold else "regular"]), max(12, int(size)))

    def text(self, surface, text, pos, size=24, bold=False, color=None, width=None):
        font = self.font(size, bold)
        if width:
            while text and font.size(text)[0] > width:
                text = text[:-2] + "…" if len(text) > 1 else ""
        image = font.render(text, True, color or self.ink)
        surface.blit(image, pos)

    def wrap(self, text, font, width):
        lines, line = [], ""
        # Character-level overflow also handles long words and non-space scripts.
        for word in text.split(" "):
            trial = (line + " " + word).strip()
            if line and font.size(trial)[0] > width:
                lines.append(line)
                line = ""
            for char in ((" " if line else "") + word):
                if line and font.size(line + char)[0] > width:
                    lines.append(line)
                    line = ""
                line += char
        if line:
            lines.append(line)
        return lines or [""]

    @lru_cache(maxsize=256)
    def transformed(self, ident, height, width_scale, flip, angle):
        source = self.images[ident]
        width = max(1, round(height * source.get_width() / source.get_height() * width_scale))
        image = self.pg.transform.smoothscale(source, (width, height))
        if flip:
            image = self.pg.transform.flip(image, True, False)
        return self.pg.transform.rotate(image, angle), width, height

    def cutout(self, record):
        state, item = record["state"], record["item"]
        if not state["visible"]:
            return None
        asset = self.manifest["assets"][state["asset"]]
        angle = round(record["angle"] + state["angle"])
        height = max(2, round(item["height"] * state["scale"]))
        image, width, height = self.transformed(state["asset"], height, round(state["width_scale"], 2), state["flip"], angle)
        ax, ay = asset["anchor"]
        ax = 1 - ax if state["flip"] else ax
        pivot = self.pg.Vector2((ax - .5) * width, (ay - .5) * height).rotate(-angle)
        self.stage.blit(image, image.get_rect(center=(round(record["x"] - pivot.x), round(record["y"] - pivot.y))))
        hx, hy = asset.get("head_anchor", [.5, .1])
        hx = 1 - hx if state["flip"] else hx
        head = self.pg.Vector2((hx - ax) * width, (hy - ay) * height).rotate(-angle)
        return record["x"] + head.x, record["y"] + head.y

    def bubble(self, playback, cue, heads):
        width, height = self.stage_size
        head = heads.get(cue["speaker"], (width / 2, height * .45))
        ceiling = min([h[1] for h in heads.values() if 0 < h[0] < width] or [height * .7])
        bw = min(width - 32, max(260, width * .35))
        size = max(18, round(height * .047))
        while True:
            font = self.font(size)
            lines = self.wrap(cue["text"], font, bw - 40)
            line_height = font.get_linesize()
            bh = 52 + len(lines) * line_height
            if bh < height - 32 or size <= 14:
                break
            size -= 2
        if bh > height - 32:
            raise ValueError("Shorten cue to fit stage: " + cue["id"])
        x = max(16, min(width - bw - 16, head[0] - bw / 2))
        y = max(16, min(ceiling, head[1]) - bh - 24)
        rect = self.pg.Rect(round(x), round(y), round(bw), bh)
        self.pg.draw.rect(self.stage, (255, 247, 230), rect, border_radius=14)
        self.pg.draw.rect(self.stage, self.ink, rect, 2, border_radius=14)
        if cue["speaker"] != "narrator" and head[1] > rect.bottom:
            px = max(rect.left + 20, min(rect.right - 20, int(head[0])))
            self.pg.draw.polygon(self.stage, (255, 247, 230), [(px - 10, rect.bottom - 2), (px + 10, rect.bottom - 2), (int(head[0]), int(head[1] - 8))])
        character = self.story["characters"][cue["speaker"]]
        self.text(self.stage, character["name"], (rect.x + 20, rect.y + 10), size=22, bold=True, color=self.pg.Color(character.get("color", "#392a20")))
        shown = playback.visible_chars(cue)
        for i, line in enumerate(lines):
            self.text(self.stage, line[:max(0, shown)], (rect.x + 20, rect.y + 42 + i * line_height), size=size)
            shown -= len(line) + 1
        self.last_bubble_rect = rect

    def render(self, playback):
        frame = stage_state(playback)
        self.last_bubble_rect = None
        self.canvas.fill(self.paper)
        self.stage.blit(self.backgrounds[frame["scene"]["background"]], (0, 0))
        heads = {}
        for record in frame["items"]:
            head = self.cutout(record)
            if head and record["item"]["id"] in frame["actors"]:
                heads[record["item"]["id"]] = head
        if frame["cue"]:
            self.bubble(playback, frame["cue"], heads)
        caption = frame["scene"].get("caption")
        if caption and frame["local"] >= caption["at"]:
            self.text(self.stage, caption["text"], (20, self.stage_size[1] - 42), size=25, bold=True, width=self.stage_size[0] - 40)
        half = self.stage_size[0] / 2
        travel = round(half * frame["curtain"])
        self.stage.blit(self.curtain, (-travel, 0))
        self.stage.blit(self.pg.transform.flip(self.curtain, True, False), (round(half) + travel, 0))
        self.pg.draw.rect(self.canvas, self.gold, self.stage_rect.inflate(10, 10), width=3)
        self.canvas.blit(self.pg.transform.smoothscale(self.stage, self.stage_rect.size), self.stage_rect)
        self.text(self.canvas, self.story["title"], (32, 14), size=34, bold=True, width=self.size[0] - 64)
        self.text(self.canvas, self.story.get("subtitle", ""), (32, 54), size=22, width=self.size[0] - 64)
        index = frame["index"]
        label = self.story.get("end_title", "Занавес") if playback.ended else f"{index + 1}/{len(playback.starts)} · {frame['scene']['title']}"
        self.text(self.canvas, label, (32, self.size[1] - 222), size=24, bold=True, width=self.size[0] - 260)
        self.text(self.canvas, f"{int(playback.time)//60}:{int(playback.time)%60:02} / {int(playback.total)//60}:{int(playback.total)%60:02}", (self.size[0] - 215, self.size[1] - 222), size=24)
        self.pg.draw.rect(self.canvas, self.gold, self.timeline_rect, border_radius=5)
        progress = self.timeline_rect.copy()
        progress.w = max(1, round(progress.w * playback.time / playback.total))
        self.pg.draw.rect(self.canvas, self.ink, progress, border_radius=5)
        play_label = "Ещё раз" if playback.ended else "Начать" if not playback.started else "Продолжить" if playback.paused else "Пауза"
        controls = [("play", play_label), ("next", "Реплика >"), ("restart", "Сначала"), ("previous_scene", "< Сцена"), ("next_scene", "Сцена >")]
        self.buttons = []
        gap, n = 10, len(controls)
        bw = (self.size[0] - 64 - gap * (n - 1)) / n
        for i, (action, text) in enumerate(controls):
            self.buttons.append((action, self.pg.Rect(32 + i * (bw + gap), self.size[1] - 151, bw, 45), text))
        start = index // 9 * 9
        n = min(9, len(playback.starts) - start)
        bw = (self.size[0] - 64 - gap * (n - 1)) / n
        for slot, scene_index in enumerate(range(start, start + n)):
            self.buttons.append((str(scene_index), self.pg.Rect(32 + slot * (bw + gap), self.size[1] - 94, bw, 42), f"{scene_index + 1}. {self.story['scenes'][scene_index]['title']}"))
        for action, rect, text in self.buttons:
            selected = action == str(index)
            self.pg.draw.rect(self.canvas, self.ink if selected else self.gold, rect, border_radius=7)
            self.text(self.canvas, text, (rect.x + 10, rect.y + 8), size=24, color=self.paper if selected else self.ink, width=rect.w - 20)
        self.text(self.canvas, "Пробел — пауза · Вправо — реплика · 1–9 — сцены · R — повтор · Esc — выход", (32, self.size[1] - 33), size=18, width=self.size[0] - 64)
        return self.canvas

    def present(self, window):
        rect = fit_rect(self.size, window.get_rect())
        window.fill(self.ink)
        window.blit(self.pg.transform.smoothscale(self.canvas, rect.size), rect)

    def point(self, event_pos, window):
        rect = fit_rect(self.size, window.get_rect())
        if not rect.collidepoint(event_pos):
            return None
        return ((event_pos[0] - rect.x) * self.size[0] / rect.w, (event_pos[1] - rect.y) * self.size[1] / rect.h)

    def click(self, point, playback):
        if point is None:
            return
        if self.timeline_rect.collidepoint(point):
            playback.started = True
            playback.seek((point[0] - self.timeline_rect.x) / self.timeline_rect.w * playback.total)
            return
        index = playback.locate()[0]
        for action, rect, _ in self.buttons:
            if not rect.collidepoint(point):
                continue
            if action == "play": playback.toggle()
            elif action == "next": playback.started = True; playback.next_cue()
            elif action == "restart": playback.restart()
            elif action == "previous_scene": playback.select_scene(max(0, index - 1))
            elif action == "next_scene": playback.select_scene(min(len(playback.starts) - 1, index + 1))
            else: playback.select_scene(int(action))
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--seek", type=float, default=0)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--run-for", type=float)
    args = parser.parse_args()
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    import pygame
    try:
        width, height = map(int, args.size.lower().split("x"))
        if width < 320 or height < 180:
            raise ValueError("Minimum window size: 320x180")
        pygame.display.init()
        pygame.font.init()
        window = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        story = json.loads((ROOT / "script.json").read_text(encoding="utf-8"))
        playback = Playback(story)
        pygame.display.set_caption(story["title"])
        renderer = Renderer(story)
        playback.seek(args.seek)
        if args.smoke_test:
            observed, frames = set(), 0
            while playback.time < playback.total:
                renderer.render(playback)
                index = playback.locate()[0]
                if index not in observed and playback.active_cue() and playback.locate()[2] >= playback.active_cue()["at"] + .7 and args.capture_dir:
                    args.capture_dir.mkdir(parents=True, exist_ok=True)
                    renderer.present(window)
                    pygame.image.save(window, str(args.capture_dir / f"scene-{index+1}.png"))
                    observed.add(index)
                playback.seek(playback.time + .5)
                frames += 1
            renderer.render(playback)
            print(json.dumps({"frames": frames + 1, "finished": playback.ended, "scenes": len(story["scenes"])}))
            return 0
        if args.screenshot:
            renderer.render(playback)
            renderer.present(window)
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(window, str(args.screenshot))
            return 0
        clock, started, running = pygame.time.Clock(), time.perf_counter(), True
        while running:
            dt = clock.tick_busy_loop(60) / 1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    window = pygame.display.set_mode((max(320, event.w), max(180, event.h)), pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: running = False
                    elif event.key == pygame.K_SPACE: playback.toggle()
                    elif event.key == pygame.K_RIGHT: playback.started = True; playback.next_cue()
                    elif event.key in (pygame.K_r, 1082): playback.restart()
                    elif pygame.K_1 <= event.key <= pygame.K_9: playback.select_scene(event.key - pygame.K_1)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    renderer.click(renderer.point(event.pos, window), playback)
            playback.advance(dt)
            renderer.render(playback)
            renderer.present(window)
            pygame.display.flip()
            if args.run_for and time.perf_counter() - started >= args.run_for:
                running = False
        return 0
    except (ValueError, KeyError, OSError, pygame.error) as error:
        print("Не удалось открыть спектакль: " + str(error) + ". Проверьте файлы и выполните prepare.", file=sys.stderr)
        return 1
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
