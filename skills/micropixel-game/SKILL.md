---
name: micropixel-game
description: Create, build, test, or debug MicroPixel Guest games in ESP-Mosaico Vibe. Use for game code and Bundles; do not use for MicroPixel Host firmware or Recovery changes.
---

# MicroPixel Game

Build games as isolated MicroPixel Guests under `games/<name>`. Read
`../../projects/micropixel-host/runtime.lock.json` before choosing SDK, ABI, or target behavior, and use the
MicroPixel source and tools pinned at `../../submodule/micropixel`.

Use `python mosaico.py game create` for a new project and `python mosaico.py game build` for a Bundle. Use
`python mosaico.py game sim games/<name>` for interactive SDL validation, or add `--headless --scenario PATH
--frames N --dump-ppm PATH --report PATH` for deterministic acceptance. Simulator output and isolated KV state
belong under the game's ignored `build/` directory. `--skip-build` is valid only when the source digest and locked
Runtime revision match; use `--reset-storage` when a scenario requires clean state. Do not
copy SDK or ABI files into a game, introduce ESP-IDF/BSP/ESP-Iris dependencies, or select behavior by board name.
Keep gameplay logic independently testable where practical.

PC simulation is independent of GSP simulation: MicroPixel Wasm runs in the pinned WAMR interpreter and uses the
same MicroPixel ABI; it never passes through GSP. Device installation is unavailable until the ESP-Iris MicroPixel
App service is implemented. Do not work around
that boundary by opening ESP-Mosaico USB with the upstream MicroPixel CLI. When device commands are added, use
only `mosaico.py game ...` and verify App ID, Bundle hash, lifecycle state, visible output, input, audio, and Trap
logs as applicable.
