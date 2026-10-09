# Game development and installation

[简体中文](game-development_CN.md) | [Documentation index](README.md)

Raylib Lite Engine games use a shared native/Host module. Configure the Engine,
BSP and utils source checkouts in `.mosaico.json`; the workspace launcher selects
those dependencies. Iris and Recovery use the same utils checkout.
`dependencies.raylib` defaults to `submodule/raylib-lite-engine`; a different
checkout can be selected for local development. When committing Vibe, update
the Engine and utils submodule revisions together; the new CLI cannot use an
old Engine snapshot.

## Create and preview your own game

```sh
python mosaico.py game create my_game
python mosaico.py game sim --project projects/my_game --headless --frames 120
python mosaico.py game build --project projects/my_game --target iris
```

The blank template uses the Engine shared launcher and ESP-Mosaico Board for
physical display/input, Iris startup and first-frame health. It starts with a
black canvas and no game assets. Modify `main/game.c` and `main/game_module.c`.
`--template sky-hop`, `shooter` and `tower-defense` copy maintained Engine games,
including their shared launcher/Board. The old BSP game copies are not used.

## Build existing and independent games

```sh
python mosaico.py game build last_zone_extraction --target iris
python mosaico.py game build /path/to/my_game --target iris
```

Independent games need a top-level IDF project, `main/CMakeLists.txt` and the
Engine native module contract/shared launcher. Their `components/`, resource
paths and SDK defaults remain in the game repository. Iris wrappers and build
output are isolated under `.codex-runs/mosaico/raylib-iris/`; explicit paths have
a source-path hash to prevent equal-name games sharing a build cache.

Iris builds use the product shared partition layout and generate a
`build/<game>-system-update.irisfw` bundle. Install using the printed generated
project path:

```sh
python mosaico.py iris system-update --project <generated-project>
```

Provision retained Recovery with `python mosaico.py recover` when needed.
Building does not flash a device. Game images are installed into `ota_0` through
Recovery; do not provision a board with a normal game's generic IDF flash command.
Keep Iris enabled for application health reporting and subsequent USB management.

Native builds without `--target iris` use the project's own top-level CMake.
Published Engine examples carry `shared/` helpers and use Registry dependencies;
Host tooling currently requires an Engine source checkout. This integration does
not build or load ELF games.
