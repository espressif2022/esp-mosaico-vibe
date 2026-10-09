---
name: mosaico-game-development
description: Develop Mosaico games with Raylib Lite Engine, validate shared behavior in Host, then build a Recovery-compatible native Iris application.
---

# Mosaico games

Read the [workspace entry](../../../docs/game-development_CN.md).
Use the Engine checkout selected by `dependencies.raylib` in `.mosaico.json`
(default: `submodule/raylib-lite-engine`). Keep the Engine and utils submodule
revisions compatible. Create a blank game with `python mosaico.py game create <name>`
or use `--template sky-hop|tower-defense|shooter`. Generated user games go in
`projects/`; an independent game repository can also be supplied by path.
Maintained reference games and reusable runtime code remain in the Engine.
BSP's old game copies are not used by these commands.

Use `python mosaico.py game sim --project <game-path>` and headless replay for
shared C game behavior and RGB565 output. Inspect visuals and complete gameplay
flows interactively when changing gameplay; a successful headless launch alone
is not visual or interaction acceptance. Never implement a separate Python or
browser game renderer.

Use `python mosaico.py game build <game-path-or-example-name> --target iris`
to generate a native ESP-Iris installation bundle. Use the generated project
path with `python mosaico.py iris system-update --project <generated-project>`
only when installation is authorized. Keep the OTA writer in retained Recovery
and mark healthy after the first accepted frame. Current Engine integration
does not build or load ELF games. Native builds without `--target iris` use the
game's own IDF project.

Run affected Engine tests and native builds. Keep assets and provenance with
the game. Follow the [device workflow](../../../docs/mosaico-cli.md) for authorized
installation and acceptance. Validate physical controls, display, audio and
performance on the target board; do not infer hardware behavior from Host results.
