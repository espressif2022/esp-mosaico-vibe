# 游戏源码、仿真与安装

[English](game-development.md) | [返回索引](README_CN.md)

本工作区的 `projects/` 不提交游戏。启动器游戏 Sky Hop、Tower Defense、
Raylib Shooter 的玩法、绘制、资源和 Host 仿真源码集中在
`raylib-lite-engine/examples/`。`esp-mosaico-elf-game-sdk/examples/` 中的
对应目录只保留构建元数据，将引擎源码打成 `MOSGAME` ELF 包。SDK 其他示例
维持现状。BSP 上游的 native 参考工程也维持现状；它们不走这条 ELF 安装链路。

SDK 和引擎与本工作区并列检出时，以 Sky Hop 为例：

```sh
cd ../esp-mosaico-elf-game-sdk
cmake -S examples/sky_hop -B build/sky_hop \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/mosaico-riscv32.cmake" \
  -DRAYLIB_LITE_ENGINE_ROOT="$PWD/../raylib-lite-engine"
cmake --build build/sky_hop
cd ../esp-mosaico-vibe
python mosaico.py game install \
  ../esp-mosaico-elf-game-sdk/build/sky_hop/game/game.bin --device-id <DEVICE_ID>
```

启动器工程不在工作区同级目录时，给 `game install` 增加
`--project /path/to/esp-mosaico-game`，让受管 Gateway 选中该固件工程。

先用引擎 Host 仿真验证画面、操作、碰撞、计分、胜负与重开，再打包。
设备由 `esp-mosaico-game` 启动器从 `game_store` 加载游戏；更新游戏使用
SDK 包和 `game install`，不更新应用固件。启动器固件本身仍通过受管的
Iris system-update 更新。真机还需验证按键、触摸、屏幕、音频和性能。

`python mosaico.py game create/sim/build` 仍支持从 BSP 模板创建 native
应用；生成的 `projects/<name>` 属于用户工作内容，不提交到本工作区。
