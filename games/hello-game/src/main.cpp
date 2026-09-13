// SPDX-License-Identifier: Apache-2.0
#include "sdk/micropixel.hpp"

int main() {
    micropixel::Application app;
    micropixel::Renderer renderer = app.renderer();
    auto scene = renderer.CreateScene(micropixel::Color::Black()).value();
    (void)scene.CreateLabel({24, 24}, "Hello, ESP-Mosaico!", micropixel::Color::White()).value();
    renderer.Present(scene).value();
    app.log().Info("Hello Game ready");
    app.Run([](const micropixel::Event&) { return micropixel::EventResult::kContinue; });
    return 0;
}

