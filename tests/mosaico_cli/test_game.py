from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from mosaico_cli.cli import build_parser, _normalize_globals
from mosaico_cli.errors import BuildError, SelectionError
from mosaico_cli.game import _scenario, build_game, create_game


REVISION = "3c632dfb4f41834e2bdb187812d61859c6f9a754"


def prepare_repository(root: Path) -> None:
    lock = {
        "schema_version": 1,
        "revision": REVISION,
        "target": "esp32s31",
        "aot_arch": "riscv32-ilp32f",
        "aot_format": 6,
        "bundle_format": 1,
    }
    lock_path = root / "projects/micropixel-host/runtime.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    tool = root / "submodule/micropixel/tools/micropixel"
    tool.parent.mkdir(parents=True)
    tool.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (root / "games").mkdir()


def prepare_game(root: Path, name: str = "demo") -> Path:
    game = root / "games" / name
    game.mkdir()
    (game / "app.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "app_id": f"com.example.{name}",
                "version": "0.1.0",
                "title": name,
                "threading": "none",
                "sources": ["src/main.cpp"],
            }
        ),
        encoding="utf-8",
    )
    return game


class GameParserTests(unittest.TestCase):
    def parse(self, *argv: str):
        return build_parser().parse_args(_normalize_globals(argv))

    def test_game_build_defaults_to_release(self) -> None:
        value = self.parse("game", "build", "games/demo")
        self.assertEqual(value.command, "game")
        self.assertEqual(value.game_command, "build")
        self.assertEqual(value.profile, "release")
        self.assertEqual(value.timeout, 300)
        self.assertFalse(value.force)

    def test_game_create_requires_identity(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            self.parse("game", "create", "games/demo")
        self.assertEqual(caught.exception.code, 2)

    def test_game_sim_headless_options(self) -> None:
        value = self.parse("game", "sim", "games/mosaic-runner", "--headless", "--frames", "900", "--reset-storage")
        self.assertEqual(value.game_command, "sim")
        self.assertTrue(value.headless)
        self.assertEqual(value.frames, 900)
        self.assertTrue(value.reset_storage)


class GameCommandTests(unittest.TestCase):
    def test_scenario_is_versioned_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps({"schema_version": 1, "fixed_step_us": 16667,
                "events": [{"frame": 3, "action": "right", "state": "down"}],
                "expect": {"required_logs": ["level_complete"]}}), encoding="utf-8")
            encoded, logs, _ = _scenario(path)
            self.assertEqual(encoded, "3:right:down")
            self.assertEqual(logs, ["level_complete"])

    def test_game_must_stay_below_games_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_repository(root)
            context = mock.Mock()
            arguments = SimpleNamespace(path="projects/not-a-game")
            with self.assertRaises(SelectionError):
                build_game(root, arguments, context, cwd=root)

    def test_revision_mismatch_stops_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_repository(root)
            game = prepare_game(root)
            context = mock.Mock()
            context.run.return_value = subprocess.CompletedProcess(
                [], 0, "0" * 40 + "\n", None
            )
            arguments = SimpleNamespace(
                path=str(game), profile="release", force=False, timeout=300.0
            )
            with self.assertRaises(BuildError) as caught:
                build_game(root, arguments, context, cwd=root)
            self.assertIn("revision", str(caught.exception).lower())
            self.assertEqual(context.run.call_count, 1)

    def test_build_uses_locked_s31_target_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_repository(root)
            game = prepare_game(root)
            bundle = game / "build/demo.bundle.bin"
            bundle.parent.mkdir()
            bundle.write_bytes(b"bundle fixture")
            tool_result = {
                "schema_version": 1,
                "ok": True,
                "result": {
                    "sdk_version": "0.17.0",
                    "toolchain_id": "fixture-toolchain",
                    "artifacts": [
                        {
                            "path": str(bundle),
                            "kind": "bundle",
                            "target": "riscv32-ilp32f",
                        }
                    ],
                },
            }
            context = mock.Mock()
            context.run.side_effect = [
                subprocess.CompletedProcess([], 0, REVISION + "\n", None),
                subprocess.CompletedProcess([], 0, json.dumps(tool_result) + "\n", None),
            ]
            arguments = SimpleNamespace(
                path=str(game), profile="release", force=False, timeout=300.0
            )

            result = build_game(root, arguments, context, cwd=root)

            build_command = context.run.call_args_list[1].args[0]
            self.assertIn("--aot-target", build_command)
            target_index = build_command.index("--aot-target")
            self.assertEqual(build_command[target_index + 1], "riscv32-ilp32f")
            manifest = json.loads((game / "build/build-manifest.json").read_text())
            self.assertEqual(manifest["runtime_revision"], REVISION)
            self.assertEqual(manifest["target"], "esp32s31")
            self.assertEqual(manifest["sdk_version"], "0.17.0")
            self.assertEqual(
                manifest["sha256"], hashlib.sha256(b"bundle fixture").hexdigest()
            )
            self.assertEqual(result["bundle"], str(bundle))

    def test_create_delegates_to_pinned_micropixel_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_repository(root)
            project = root / "games/new-game"
            context = mock.Mock()
            context.run.side_effect = [
                subprocess.CompletedProcess([], 0, REVISION + "\n", None),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "schema_version": 1,
                            "ok": True,
                            "result": {"project": str(project)},
                        }
                    )
                    + "\n",
                    None,
                ),
            ]
            arguments = SimpleNamespace(
                path="games/new-game",
                app_id="com.example.new-game",
                title="New Game",
            )

            result = create_game(root, arguments, context, cwd=root)

            command = context.run.call_args_list[1].args[0]
            self.assertIn("init", command)
            self.assertIn("com.example.new-game", command)
            self.assertEqual(result["project"], str(project))


if __name__ == "__main__":
    unittest.main()
