"""Behavioral checks for project tools and Python/JavaScript timeline parity."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import theater_project as project


class TheaterTests(unittest.TestCase):
    def setUp(self):
        base = (project.SKILL / ".local/test-tmp").resolve()
        if not base.is_relative_to(project.SKILL):
            raise ValueError("Test workspace must remain inside skill directory")
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="sprite-theater-test-", dir=base)
        self.root = Path(self.temp.name) / "play"
        project.init_project(self.root, "both", demo=True)
        self.story = project.read_json(self.root / "script.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_portable_project_and_no_overwrite(self):
        self.assertTrue(project.validate_project(self.root)["valid"])
        old = (self.root / "script.json").read_bytes()
        with self.assertRaises(ValueError):
            project.init_project(self.root, "web")
        project.init_project(self.root, "both", overwrite=True)
        self.assertEqual(old, (self.root / "script.json").read_bytes())

    def test_backend_selection_and_empty_scaffold(self):
        for backend in ("pygame", "web"):
            root = Path(self.temp.name) / backend
            project.init_project(root, backend)
            self.assertEqual((root / "main.py").exists(), backend == "pygame")
            self.assertEqual((root / "index.html").exists(), backend == "web")
            with self.assertRaisesRegex(ValueError, "no scenes"):
                project.prepare_project(root)

    def test_pause_reveal_skip_restart(self):
        playback = project.timeline.Playback(self.story)
        playback.play()
        playback.seek(3.1)
        before = project.timeline.stage_state(playback)
        playback.pause()
        playback.advance(99)
        self.assertEqual(before, project.timeline.stage_state(playback))
        playback.next_cue()
        self.assertEqual(playback.visible_chars(playback.active_cue()), len(playback.active_cue()["text"]))
        playback.next_cue()
        self.assertEqual(playback.active_cue()["id"], "wait")
        playback.select_scene(1)
        self.assertEqual(playback.time, 14)
        playback.advance(100)
        self.assertTrue(playback.ended)
        self.assertTrue(playback.paused)
        playback.restart()
        self.assertEqual(playback.time, 0)
        self.assertFalse(playback.paused)

    def test_seek_restores_pose_and_attachment(self):
        playback = project.timeline.Playback(self.story)
        def inspect(time):
            playback.seek(time)
            return {r["item"]["id"]: r for r in project.timeline.stage_state(playback)["items"]}
        seated = inspect(6)
        self.assertEqual(seated["mira"]["state"]["asset"], "mira-sit")
        carried = inspect(9)
        self.assertEqual(carried["letter"]["state"]["attach"], "mira")
        self.assertAlmostEqual(carried["letter"]["x"] - carried["mira"]["x"], .025 * self.story["stage"]["width"])
        self.assertIsNone(inspect(12)["letter"]["state"]["attach"])
        self.assertEqual(seated, inspect(6))
        self.assertEqual(carried, inspect(9))

    def test_dynamic_dimensions_and_many_scenes(self):
        self.story["stage"].update(width=1000, height=600, curtain_seconds=1, chars_per_second=10)
        template = self.story["scenes"][1]
        self.story["scenes"] = []
        for index in range(11):
            scene = copy.deepcopy(template)
            scene["id"] = "scene-" + str(index)
            scene["cues"][0]["id"] = "cue-" + str(index)
            self.story["scenes"].append(scene)
        playback = project.timeline.Playback(self.story)
        playback.select_scene(10)
        self.assertEqual(playback.locate()[0], 10)
        playback.seek(103.2)
        frame = project.timeline.stage_state(playback, reduced=True)
        self.assertAlmostEqual(frame["actors"]["mira"]["x"], 350)
        self.assertAlmostEqual(frame["curtain"], 1)
        self.assertEqual(playback.total, 110)

    def test_unmarked_invention_invalid_times_and_missing_pose(self):
        bad = copy.deepcopy(self.story)
        bad["scenes"][0]["cues"][0]["sources"] = []
        with self.assertRaises(ValueError):
            project.timeline.validate_story(bad)
        bad["scenes"][0]["cues"][0]["original"] = True
        project.timeline.validate_story(bad)
        bad["scenes"][0]["duration"] = float("nan")
        with self.assertRaises(ValueError):
            project.timeline.validate_story(bad)
        self.story["scenes"][0]["actors"][0]["keyframes"][1]["asset"] = "absent"
        project.write_json(self.root / "script.json", self.story)
        with self.assertRaisesRegex(ValueError, "pose"):
            project.prepare_project(self.root)

    def test_alpha_and_sheet_identity(self):
        from PIL import Image
        manifest = project.read_json(self.root / "assets/manifest.json")
        path = self.root / manifest["assets"]["mira-stand"]["file"]
        Image.open(path).convert("RGB").save(path)
        with self.assertRaisesRegex(ValueError, "transparent"):
            project.validate_project(self.root)
        project.make_demo(self.root)
        manifest = project.read_json(self.root / "assets/manifest.json")
        manifest["assets"]["mira-stand"]["sheet_origin"]["entity_id"] = "lev"
        project.write_json(self.root / "assets/manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "lineage"):
            project.validate_project(self.root)

    def test_prepare_detects_stale_data_and_preserves_images(self):
        image = self.root / "assets/mira-stand.png"
        before = image.read_bytes()
        self.story["title"] = "Другая постановка"
        project.write_json(self.root / "script.json", self.story)
        with self.assertRaisesRegex(ValueError, "stale"):
            project.validate_project(self.root)
        project.prepare_project(self.root)
        self.assertTrue(project.validate_project(self.root)["valid"])
        self.assertEqual(before, image.read_bytes())

    def test_external_paths_and_missing_resources(self):
        with self.assertRaises(ValueError):
            project.local_file(self.root, "../outside.png")
        with self.assertRaises(ValueError):
            project.local_file(self.root, "https://example.com/a.png")
        (self.root / "assets/letter.png").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            project.validate_project(self.root)

    def test_pygame_detects_stale_asset_metadata(self):
        from PIL import Image, ImageDraw
        root = Path(self.temp.name) / "pygame-stale"
        project.init_project(root, "pygame", demo=True)
        path = root / "assets/mira-stand.png"
        with Image.open(path) as source:
            image = source.copy()
        ImageDraw.Draw(image).point((50, 50), fill="white")
        image.save(path)
        with self.assertRaisesRegex(ValueError, "stale"):
            project.validate_project(root)
        project.prepare_project(root)
        self.assertTrue(project.validate_project(root)["valid"])

    @unittest.skipUnless(shutil.which("node"), "Node unavailable; JavaScript parity not checked")
    def test_python_javascript_parity(self):
        engine = project.TEMPLATES / "web/engine.js"
        code = r"""
const fs = require('fs'), E = require(process.argv[1]);
const story = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const p = new E.Playback(story), result = [];
for (let t = 0; t <= p.total; t += .25) {
  p.seek(t); const f = E.stageState(p);
  result.push({time:t, curtain:f.curtain, items:f.items.map(v => ({id:v.item.id, state:v.state, x:v.x, y:v.y, angle:v.angle}))});
}
console.log(JSON.stringify(result));
"""
        raw = subprocess.check_output(["node", "-e", code, str(engine), str(self.root / "script.json")], encoding="utf-8")
        playback = project.timeline.Playback(self.story)
        for sample in json.loads(raw):
            playback.seek(sample["time"])
            frame = project.timeline.stage_state(playback)
            self.assertAlmostEqual(sample["curtain"], frame["curtain"], places=10)
            for js, py in zip(sample["items"], frame["items"]):
                self.assertEqual(js["id"], py["item"]["id"])
                self.assertEqual(js["state"], py["state"])
                for key in ("x", "y", "angle"):
                    self.assertAlmostEqual(js[key], py[key], places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
