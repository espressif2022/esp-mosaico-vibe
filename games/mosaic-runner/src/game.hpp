// SPDX-License-Identifier: Apache-2.0
#ifndef MOSAIC_RUNNER_GAME_HPP
#define MOSAIC_RUNNER_GAME_HPP

#include <stdint.h>

namespace mosaic_runner {

struct Game {
    float x{48}, y{356}, vx{}, vy{};
    int lives{3}, coins{};
    bool left{}, right{}, grounded{}, complete{};
    bool coin_a{}, coin_b{}, enemy_alive{true};

    void Restart() { *this = Game{}; }
    void Jump() {
        if (grounded) { vy = -12.5F; grounded = false; }
    }
    bool Solid(float px, float py) const {
        if (py >= 416 && !((px > 630 && px < 665) || (px > 1150 && px < 1185))) return true;
        return (px > 330 && px < 510 && py >= 340 && py < 365) ||
               (px > 760 && px < 970 && py >= 310 && py < 335) ||
               (px > 1260 && px < 1450 && py >= 350 && py < 375);
    }
    // Returns: 1 coin, 2 hurt, 3 complete, 0 ordinary frame.
    int Step() {
        vx = right == left ? 0.0F : (right ? 5.0F : -5.0F);
        x += vx;
        if (x < 0) x = 0;
        vy += 0.72F;
        const float old_bottom = y + 36;
        y += vy;
        if (y > 500) { --lives; x = 48; y = 356; vy = 0; return 2; }
        grounded = false;
        for (int probe = 0; probe != 3; ++probe) {
            const float px = x + 4 + probe * 12;
            if (vy >= 0 && Solid(px, y + 38) && !Solid(px, old_bottom)) {
                while (Solid(px, y + 38)) y -= 1;
                vy = 0; grounded = true;
            }
        }
        if (!coin_a && x > 365 && x < 425 && y < 390) { coin_a = true; ++coins; return 1; }
        if (!coin_b && x > 810 && x < 890 && y < 370) { coin_b = true; ++coins; return 1; }
        const float enemy_x = 1010.0F;
        if (enemy_alive && x + 30 > enemy_x && x < enemy_x + 34 && y + 38 > 380) {
            if (y < 370) { enemy_alive = false; vy = -7; }
            else { enemy_alive = false; --lives; x = 900; y = 350; vy = -4; return 2; }
        }
        if (x >= 1580) { complete = true; return 3; }
        return 0;
    }
};

}  // namespace mosaic_runner
#endif
