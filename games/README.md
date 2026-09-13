# MicroPixel games

Each child directory is an independent MicroPixel Guest project with an
`app.json` manifest. Games use the SDK and build tools pinned by
`projects/micropixel-host/runtime.lock.json`.

Create and build games through the Vibe entry point:

```sh
python mosaico.py game create games/my-game \
    --app-id com.example.my-game --title "My Game"
python mosaico.py game build games/my-game
python mosaico.py game sim games/mosaic-runner --headless \
    --scenario games/mosaic-runner/scenarios/complete.json --frames 800
```

Simulator reports, PCM, framebuffer dumps, and private KV state stay in the ignored game `build/` directory.
Build outputs are ignored by Git. Device installation will be added after the
ESP-Iris MicroPixel App service is available; do not bypass ESP-Iris by opening
the ESP-Mosaico USB interface with the upstream MicroPixel CLI.
