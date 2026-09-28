---
name: mosaico-game-development
description: Develop Mosaico games with Raylib Lite Engine as the preferred engine, validate visuals and gameplay in the simulator first, then follow the recovery-safe device workflow.
---

# Mosaico games

Read the [workspace entry](../../../docs/game-development_CN.md).
Use the Raylib Lite Engine named by `dependencies.raylib` (`../raylib-lite-engine`);
`RAYLIB_LITE_ENGINE_ROOT` overrides it. Create with
`python mosaico.py game create <name> --template sky-hop|tower-defense|shooter`.
New game source goes under the selected engine's `examples/`, not `projects/`.
Sky Hop, Tower Defense, and Raylib Shooter ELF gameplay source and Host simulation
are owned by Raylib Lite Engine examples; the ELF SDK only packages them.
BSP's old native game templates are not used by the workspace game commands.

Use `python mosaico.py game sim --project <engine>/examples/<name>` and headless replay
for the shared C model and RGB565 view before device installation. Inspect
visuals, animation, input feedback and complete gameplay flows interactively;
use recorded input and headless replay for repeatable checks of relevant
collisions, scoring, win/loss and restart behavior. Fix and re-run affected
flows in the simulator before device validation. A successful headless launch
alone does not establish that the game looks or plays correctly.
Never implement a separate Python or browser renderer.
Build launcher games through the ELF SDK, then install its MOSGAME bundle with
`python mosaico.py game install <game.bin>`; preserve the launcher and Recovery contract.
Use `game build <game> --target iris` for an engine game as a managed Iris application.
Keep OTA writer only in Recovery and mark healthy after the first successful frame.

Run the affected engine tests and native or ELF builds.
Keep sprites, audio sources and license information with the game. Follow the
[CLI device workflow](../../../docs/mosaico-cli.md) for installation, diagnostics
and acceptance. Validate physical controls, display,
audio and device performance on hardware; do not claim hardware behavior from Host evidence.
