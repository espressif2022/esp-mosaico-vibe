---
name: micropixel-runtime
description: Integrate or upgrade MicroPixel Host firmware, its ESP-Iris transport, partition layout, or Recovery-first lifecycle for ESP-Mosaico. Do not use for ordinary Guest game changes.
---

# MicroPixel Runtime

Read `../../docs/micropixel-game-runtime-integration.zh-CN.md`, the root `AGENTS.md`, and the MicroPixel
submodule's `AGENTS.md` before changing an architectural boundary. Treat
`../../projects/micropixel-host/runtime.lock.json` and both repositories' git status as required inputs.

Keep MicroPixel source changes in `../../submodule/micropixel`; do not copy its Firmware, SDK, or ABI into Vibe.
ESP-Iris must remain the only ESP-Mosaico USB owner. Adapt ESP-Iris RPC to MicroPixel control contracts rather
than letting it write BundleFS directly. Normal Host firmware retains the enter-Recovery RPC and contains no OTA
writer; firmware installation goes through the reviewed Factory Recovery and `mosaico.py`.

For S31 Host changes, run the MicroPixel Host tests, formatting and selected S31 build required by its repository
instructions. For Vibe integration changes, run the CLI tests. A device-side change is complete only after the
same Device ID passes normal -> Recovery -> normal with new Boot IDs, intended firmware identity, preserved
recovery data, and relevant display/input/audio/storage behavior.

