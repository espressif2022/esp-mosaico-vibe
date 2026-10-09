# 游戏开发与安装

[English](game-development.md) | [文档索引](README_CN.md)

在 `.mosaico.json` 配置 Engine、BSP 和 utils checkout。Vibe 使用这些路径，
Iris 和 Recovery 来自同一个 utils 版本。`dependencies.raylib` 默认指向
`submodule/raylib-lite-engine`；本地联调可改为其他 checkout。Vibe 提交时需一起
更新 Engine 和 utils 的 submodule revision，不能只更新 CLI 而保留旧引擎快照。

## 创建自己的游戏

```sh
python mosaico.py game create my_game
python mosaico.py game sim --project projects/my_game --headless --frames 120
python mosaico.py game build --project projects/my_game --target iris
```

空白游戏使用共享 native/Host 模块和 ESP-Mosaico Board，接入显示、输入、
Iris 启动与第一帧健康确认。初始画面为黑色，没有额外游戏素材。
修改 `main/game.c` 与 `main/game_module.c` 即可开发。
`--template sky-hop`、`shooter`、`tower-defense` 从 Engine 的维护例程创建，
附带共享启动器和 Board；不再使用 BSP 中的旧游戏副本。

## 内部例程和独立游戏

```sh
python mosaico.py game build last_zone_extraction --target iris
python mosaico.py game build /path/to/my_game --target iris
```

独立游戏需有顶层 IDF 工程和 `main/CMakeLists.txt`，并遵循 Engine native
模块与共享启动器契约。自己的组件、资源路径和配置留在游戏仓库。
生成工程和输出位于 `.codex-runs/mosaico/raylib-iris/`，外部路径有独立哈希，
避免同名游戏共用构建缓存。可通过 `version.txt` 指定安装包版本。

Iris 构建使用产品共享分区表，生成 `build/<game>-system-update.irisfw`。
使用命令输出的生成工程路径安装：

```sh
python mosaico.py iris system-update --project <generated-project>
```

需要首次部署 Recovery 时使用 `python mosaico.py recover`。构建不会烧录；
游戏通过 Recovery 安装到 `ota_0`，不要用普通游戏的 IDF flash 命令部署整板。
保持 Iris 开启，以提供应用健康事件和后续 USB 管理。

不加 `--target iris` 的 native 构建使用游戏自己的顶层 CMake。发布例程自带
`shared/`，通过 Registry 消费 Engine；Host 工具仍需 Engine 源码 checkout。
当前这条接入路径不构建或加载 ELF 游戏。
