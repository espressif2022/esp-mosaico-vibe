# Game source, simulation, and installation

[简体中文](game-development_CN.md) | [Documentation index](README.md)

This workspace keeps no checked-in games in `projects/`. Its CLI and pinned
submodules provide an application workspace. For the launcher games Sky Hop,
Tower Defense, and Raylib Shooter, gameplay, rendering, assets, and Host
simulation live in `raylib-lite-engine/examples/`. Their directories in
`esp-mosaico-elf-game-sdk/examples/` contain only build metadata and package
the engine source as `MOSGAME` ELF bundles. The SDK's other examples retain
their current layout. BSP native reference applications remain in the BSP
upstream repository; they are separate from this ELF installation path.

For example, with the SDK and engine checked out alongside this workspace:

```sh
cd ../esp-mosaico-elf-game-sdk
cmake -S examples/sky_hop -B build/sky_hop \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/mosaico-riscv32.cmake" \
  -DRAYLIB_LITE_ENGINE_ROOT="$PWD/../raylib-lite-engine" \
  -DMOSAICO_LAUNCHER_ROOT="$PWD/../esp-mosaico-game"
cmake --build build/sky_hop
cd ../esp-mosaico-vibe
python mosaico.py game install \
  ../esp-mosaico-elf-game-sdk/build/sky_hop/game/game.bin --device-id <DEVICE_ID>
```

If the launcher checkout is elsewhere, pass `--project /path/to/esp-mosaico-game`
to `game install` so the managed Gateway uses that firmware project.

Use the engine Host simulator to inspect visuals, interaction, collisions,
scoring, win/loss and restart behavior before packaging. The installed game
runs under `esp-mosaico-game`'s launcher and `game_store`; updating a game
uses the SDK bundle and `game install`, not an application firmware update.
The launcher firmware itself is updated through the managed Iris system-update
flow. On hardware, verify buttons, touch, display, audio, and performance.

`python mosaico.py game create/sim/build` uses the Raylib Lite Engine checkout
named by `dependencies.raylib` in `.mosaico.json` (the sibling
`../raylib-lite-engine`); `RAYLIB_LITE_ENGINE_ROOT` overrides it. New games live
under that engine's `examples/<name>`, with no BSP game template copied into
`projects/`. Templates and buildable games come from the engine's
`tools/game_cli.py list`:

```sh
python mosaico.py game create my_game --template shooter
python mosaico.py game sim --project examples/my_game --headless --frames 300
python mosaico.py game build my_game --target iris
```

`--target iris` wraps the engine game as a managed ESP-Iris application with the
`mosaico-tools/templates/raylib_lite_iris` configuration and partition table;
the generated project and build live under `.codex-runs/mosaico/raylib-iris/`.
Native builds need only the BSP from `dependencies.bsp`; the board platform
ships in the engine's `ports/esp_mosaico/`. Install the result through the
system-update flow, not ESP-IDF flash targets. Launcher ELF games use the SDK
packaging and `game install` flow above.
