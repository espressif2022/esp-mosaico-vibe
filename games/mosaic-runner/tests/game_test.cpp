// SPDX-License-Identifier: Apache-2.0
#include "../src/game.hpp"
#include <cassert>
int main() {
    mosaic_runner::Game g;
    for (int i=0;i<10;++i) g.Step();
    assert(g.y > 356);
    g.right=true; g.grounded=true; g.Jump(); assert(g.vy < 0);
    g.x=1581; assert(g.Step()==3 && g.complete);
    g.x=20; g.y=501; g.vy=0; g.complete=false; assert(g.Step()==2 && g.lives==2);
}
