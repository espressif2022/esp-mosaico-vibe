// SPDX-License-Identifier: Apache-2.0
#include "sdk/micropixel.hpp"
#include "game.hpp"
#include "generated_atlas.hpp"

using namespace micropixel;
using mosaic_runner::Game;

namespace {
constexpr int W = 480, H = 480;
uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) { return uint16_t(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)); }
void rect(uint16_t* p, int x, int y, int w, int h, uint16_t c) {
    if (x < 0) { w += x; x = 0; } if (y < 0) { h += y; y = 0; }
    if (x + w > W) w = W - x; if (y + h > H) h = H - y;
    for (int yy = y; yy < y + h; ++yy) for (int xx = x; xx < x + w; ++xx) p[yy * W + xx] = c;
}
void draw(uint16_t* p, const Game& g) {
    const uint16_t sky = rgb(91, 188, 255), cloud = rgb(244, 250, 255), earth = rgb(73, 55, 45);
    for (int i = 0; i < W * H; ++i) p[i] = sky;
    rect(p, 55, 65, 100, 24, cloud); rect(p, 300, 105, 125, 22, cloud);
    int camera = int(g.x) - 150; if (camera < 0) camera = 0; if (camera > 1320) camera = 1320;
    for (int wx = 0; wx < 1800; wx += 32) if (!((wx > 630 && wx < 665) || (wx > 1150 && wx < 1185))) {
        rect(p, wx - camera, 416, 34, 64, earth); rect(p, wx - camera, 416, 34, 8, rgb(75, 205, 96));
    }
    rect(p, 330-camera, 340, 180, 25, earth); rect(p, 760-camera, 310, 210, 25, earth);
    rect(p, 1260-camera, 350, 190, 25, earth);
    if (!g.coin_a) { rect(p, 382-camera, 294, 16, 25, rgb(255, 218, 45)); rect(p, 386-camera, 298, 4, 17, cloud); }
    if (!g.coin_b) { rect(p, 838-camera, 264, 16, 25, rgb(255, 218, 45)); rect(p, 842-camera, 268, 4, 17, cloud); }
    if (g.enemy_alive) { rect(p, 1010-camera, 386, 34, 30, rgb(120, 55, 65)); rect(p, 1016-camera, 393, 5, 5, cloud); }
    rect(p, 1600-camera, 215, 7, 201, cloud); rect(p, 1607-camera, 225, 60, 40, rgb(255, 91, 95));
    const int px = int(g.x)-camera, py = int(g.y);
    const uint16_t atlas_colors[] = {0, rgb(33,45,82), rgb(255,130,77), cloud};
    for (int ay=0; ay<8; ++ay) for (int ax=0; ax<8; ++ax) {
        const uint8_t index = kPlayerAtlas[ay*8+ax]; if (index) rect(p, px+ax*4, py+ay*4, 4, 4, atlas_colors[index]);
    }
    for (int i=0; i<g.lives; ++i) rect(p, 18+i*22, 18, 15, 15, rgb(255, 91, 95));
}
void tone(const Application& app, uint32_t hz, uint32_t ms) {
    Tone value; value.waveform = Waveform::kSquare; value.frequency_hz = hz;
    value.duration = Duration::Milliseconds(ms); value.volume_per_mille = 90;
    (void)app.audio().Play(value);
}
}

int main() {
    Application app;
    Game game;
    auto surface_result = app.renderer().CreateGuestSurface(2);
    if (!surface_result) { app.log().Error("sim_error:surface_create"); return 2; }
    auto surface = static_cast<GuestSurface&&>(surface_result.value());
    app.log().Info("level_started");
    app.Run([&](const Event& event) {
        if (const auto* key = event.key()) {
            const bool down = key->phase() != KeyPhase::kUp && key->phase() != KeyPhase::kCancel;
            if (key->code() == KeyCode::kLeft) game.left = down;
            if (key->code() == KeyCode::kRight) game.right = down;
            if (down && (key->code() == KeyCode::kConfirm || key->code() == KeyCode::kUp)) { game.Jump(); tone(app, 620, 90); app.log().Info("audio:jump"); }
            if (down && key->code() == KeyCode::kMenu) game.Restart();
        }
        if (const auto* touch = event.touch()) {
            const bool down = touch->phase() != TouchPhase::kUp && touch->phase() != TouchPhase::kCancel;
            if (touch->y() > 330 && touch->x() < 170) game.left = down;
            else if (touch->y() > 330 && touch->x() < 330) game.right = down;
            else if (down && touch->x() >= 330) { game.Jump(); tone(app, 620, 90); app.log().Info("audio:jump"); }
        }
        if (event.type() == EventType::kTimer) {
            const int change = game.Step();
            if (change == 1) { tone(app, 980, 80); app.log().Info("coin_collected audio:coin"); }
            if (change == 2) { tone(app, 150, 180); app.log().Info("player_hurt audio:hurt"); }
            if (game.lives <= 0) { game.Restart(); app.log().Info("level_restarted"); }
            uint32_t index{};
            if (surface.AcquireFree(index)) { draw(surface.Buffer(index), game); (void)surface.Present(index); }
            if (change == 3) {
                uint32_t count = 0; auto old = app.storage().GetU32("completions"); if (old) count = old.value();
                (void)app.storage().SetU32("completions", count + 1);
                tone(app, 880, 350);
                app.log().Info("level_complete audio:complete");
                return EventResult::kExit;
            }
        }
        return EventResult::kContinue;
    });
    return 0;
}
