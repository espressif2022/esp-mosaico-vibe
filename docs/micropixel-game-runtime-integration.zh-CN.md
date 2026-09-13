# MicroPixel 游戏运行时本地集成方案

| 项目 | 内容 |
| --- | --- |
| 目标仓库 | ESP-Mosaico Vibe |
| 上游仓库 | MicroPixel (`https://github.com/78/micropixel.git`) |
| 目标硬件 | ESP-Mosaico（ESP32-S31、16 MiB NOR、外部 SPI NAND） |
| 集成方式 | 固定 revision 的 Git submodule + Vibe 构建/设备适配层 |
| 文档性质 | 待实施的本地工程设计，不表示相关功能已经完成 |

## 1. 目标

将 MicroPixel 接入 ESP-Mosaico Vibe，作为 ESP-Mosaico 上的常驻游戏运行时。Vibe
继续作为 Agent 主导的统一开发入口；ESP-Iris 继续独占设备 USB 会话并负责设备身份、
日志、固件恢复和数据传输；游戏通过 MicroPixel SDK 构建为 AOT Bundle，在不重刷整套
固件的情况下安装、启动和调试。

目标工作流如下：

```sh
# 首次或需要升级运行时时安装 MicroPixel Host 固件
python mosaico.py runtime install

# 创建游戏
python mosaico.py game create games/my-game \
    --app-id com.example.my-game \
    --title "My Game"

# 日常迭代：构建 Bundle、安装、启动、跟随日志
python mosaico.py game run games/my-game
```

本方案不把 MicroPixel 复制到 Vibe，不把每个游戏变成 ESP-IDF 固件，也不让 MicroPixel
CLI 与 ESP-Iris Gateway 同时竞争 ESP-Mosaico 的单一高速 USB 接口。

## 2. 设计结论

系统职责固定为：

```text
用户 / Agent
    |
    v
ESP-Mosaico Vibe
  - 工程生成
  - 工具链解析
  - 构建编排
  - 验收与证据
    |
    +---------------- 固件安装 ----------------+
    |                                           |
    v                                           v
ESP-Iris Gateway                         Factory Recovery
  - 唯一 USB owner                         - 唯一固件 writer
  - Device ID / Boot ID                    - 写 MicroPixel Host
  - RPC、日志、操作记录
    |
    +---------------- Bundle 传输 ---------------+
    |
    v
MicroPixel Host
  - WASM/AOT Runtime
  - App Hall 与生命周期
  - 图形、音频、输入、传感器、存储
  - Bundle 校验与 BundleFS 事务
    |
    v
Game Bundle（AOT + metadata + assets）
```

边界约束：

1. Vibe 是编排层，不重新实现 MicroPixel Runtime。
2. ESP-Iris 是传输层，不直接读写或解释 BundleFS。
3. MicroPixel Host 是 Bundle 安装和游戏生命周期的权威。
4. Factory Recovery 是 NOR 固件写入的唯一权威。
5. 游戏只依赖 MicroPixel Guest SDK，不依赖 ESP-IDF、BSP、ESP-Iris 或具体板型。
6. MicroPixel 上游源码只在其子模块内修改并向上游提交；Vibe 不维护复制版本。

## 3. 目标目录

```text
esp-mosaico-vibe/
├── .gitmodules
├── mosaico.py
├── docs/
│   └── micropixel-game-runtime-integration.zh-CN.md
├── games/
│   ├── README.md
│   └── hello-game/
│       ├── app.json
│       ├── CMakeLists.txt
│       ├── src/
│       ├── assets/
│       ├── audio/
│       └── tests/
├── gamekit/
│   ├── include/mosaico/gamekit/
│   └── tests/
├── projects/
│   ├── factory/
│   └── micropixel-host/
│       ├── README.md
│       ├── runtime.lock.json
│       ├── partitions.csv
│       └── sdkconfig.defaults
├── skills/
│   ├── micropixel-game/SKILL.md
│   └── micropixel-runtime/SKILL.md
├── submodule/
│   ├── esp-iris/
│   ├── esp-mosaico-bsp/
│   ├── esp-gsp/
│   └── micropixel/
└── tools/mosaico_cli/
    ├── game.py
    ├── micropixel.py
    └── runtime_install.py
```

`projects/micropixel-host` 是 Vibe 侧的产品配置与锁定信息，不复制 MicroPixel Firmware
源码。实际 Host 工程仍位于：

```text
submodule/micropixel/firmware/espressif
```

游戏放在 `games/`，不放入 `projects/`。现有 `mosaico.py install --project` 会把
`projects/` 下的目录视为 ESP-IDF 工程；分开目录可以防止固件与 Bundle 的发现逻辑混淆。

## 4. Git submodule 落地

### 4.1 添加子模块

在 Vibe 仓库根目录执行：

```sh
git submodule add https://github.com/78/micropixel.git submodule/micropixel
git -C submodule/micropixel checkout <reviewed-commit>
git add .gitmodules submodule/micropixel
```

`.gitmodules` 的目标内容为：

```ini
[submodule "submodule/micropixel"]
    path = submodule/micropixel
    url = https://github.com/78/micropixel.git
```

不配置浮动 `branch`。Vibe 提交中记录 gitlink，升级必须通过独立变更完成。

### 4.2 初始化规则

仅游戏或 Runtime 任务初始化 MicroPixel：

```sh
git submodule update --init submodule/micropixel
git -C submodule/micropixel submodule update --init \
    firmware/espressif/components/wasm-micro-runtime \
    firmware/espressif/components/esp-iot-solution
```

不要默认递归初始化 Vibe 和 MicroPixel 的全部子模块。构建 Host 时才初始化 WAMR 和
MicroPixel 固定的 `esp-iot-solution`；仅构建 Guest 游戏时无需初始化固件子模块。

### 4.3 上游修改规则

ESP-Iris transport、S31 分区 profile 和板级组合等通用修改应进入 MicroPixel 上游仓库。
Vibe 只保存：

- MicroPixel revision；
- ESP-Mosaico 产品配置；
- 构建和安装适配器；
- Vibe 专用 Skills 与验收规则。

禁止在 Vibe 中通过长期 patch 文件或复制目录维护 MicroPixel fork。若改动尚未合并上游，
可临时把 gitlink 固定到可审查的集成分支 commit，但 `runtime.lock.json` 必须记录完整 commit。

## 5. Runtime 锁定契约

新增 `projects/micropixel-host/runtime.lock.json`：

```json
{
  "schema_version": 1,
  "runtime": "micropixel",
  "repository": "https://github.com/78/micropixel.git",
  "revision": "<40-character-git-commit>",
  "board_profile": "esp-mosaico",
  "target": "esp32s31",
  "aot_arch": "riscv32",
  "aot_format": 6,
  "bundle_format": 1,
  "guest_abi": {
    "major": 2,
    "minimum_minor": 0
  },
  "partition_layout": "mosaico-micropixel-v1",
  "transport": "esp-iris",
  "recovery_required": true
}
```

构建前检查：

1. 子模块 HEAD 必须等于 `revision`。
2. ESP-IDF 必须满足 MicroPixel 和 Vibe 的共同约束，当前基线为 6.1。
3. WAMRC 必须来自该 MicroPixel revision 锁定的 WAMR fork。
4. WAMRC 必须产生 AOT v6 RISC-V 目标，不能只比较版本字符串。
5. ESP-Iris revision 必须与 Vibe `.gitmodules` gitlink 一致。
6. 分区表必须使用 `mosaico-micropixel-v1`，不得退回 MicroPixel 默认 S31 分区表。

设备安装 Bundle 前至少返回以下身份：

```json
{
  "firmware": "micropixel",
  "firmware_version": "...",
  "runtime_revision": "...",
  "device_id": "...",
  "boot_id": "...",
  "target": "esp32s31",
  "aot_arch": "riscv32",
  "aot_format": 6,
  "bundle_format": 1,
  "guest_abi": {"major": 2, "minor": 0},
  "capabilities": ["micropixel.apps.v1"]
}
```

Vibe 在上传前做兼容性预检；MicroPixel Host 在提交 Bundle 时仍独立校验目标、格式、
ABI、长度、hash 和签名。PC 侧预检不能替代设备侧安全检查。

## 6. 固件与分区集成

### 6.1 推荐分区表

使用 Vibe 的 Recovery-first 模型，MicroPixel Host 不保留自己的双 OTA writer。16 MiB NOR
建议布局如下：

```csv
# Name,       Type, SubType, Offset,   Size,     Flags
nvs,          data, nvs,     0x009000, 0x006000,
otadata,      data, ota,     0x00f000, 0x002000,
phy_init,     data, phy,     0x011000, 0x001000,
factory_nvs,  data, nvs,     0x012000, 0x00e000,
factory,      app,  factory, 0x020000, 0x200000,
ota_0,        app,  ota_0,   0x220000, 0x500000,
coredump,     data, coredump,0x720000, 0x0d0000,
sysmeta,      data, 0x40,    0x7f0000, 0x010000,
app_store,    data, 0x40,    0x800000, 0x800000,
```

布局说明：

- `factory`：Vibe 审核过的 ESP-Iris Recovery，2 MiB。
- `ota_0`：MicroPixel Host，5 MiB。
- `coredump`：保留故障证据。
- `sysmeta`：Recovery 和正常固件共享的受控元数据。
- `app_store`：8 MiB 内部 BundleFS，用于系统 Bundle 或出厂游戏。
- 外部 SPI NAND：MicroPixel 扩展 BundleFS，用于开发和下载的用户游戏。

实施前必须用真实 release 配置构建并检查 MicroPixel Host 大小。验收目标建议为
`ota_0` 至少保留 15% 空间；如果不满足，应先缩小内部 `app_store` 或裁剪 Host 功能，不能
静默改变分区偏移。任何分区迁移都必须定义老版本数据保留与失败恢复策略。

### 6.2 固件 profile

在 MicroPixel 中新增或调整 ESP-Mosaico 的 Vibe 产品 profile：

```text
esp-mosaico-vibe
  board: ESP-Mosaico
  target: esp32s31
  partition table: projects/micropixel-host/partitions.csv
  local transport: ESP-Iris
  firmware OTA writer: disabled
  enter-recovery RPC: enabled
  screen mirror: ESP-Iris backend
  app storage: internal NOR + external SPI NAND
```

正常 Host 必须满足：

```text
CONFIG_ESP_IRIS_OTA_DEFAULT_VIA_RECOVERY=y
# CONFIG_ESP_IRIS_OTA is not set
```

并调用 `iris_ota_support_start()` 暴露进入 Recovery 的 RPC。实际 Kconfig 名称和启动 API
必须以固定 ESP-Iris 源码为准，不在适配器中发明替代接口。

### 6.3 Recovery 兼容

Runtime 安装继续遵守 Vibe 现有链路：

```text
normal MicroPixel Host
    -> 请求进入 factory Recovery
    -> Gateway 等待相同 Device ID、新 Boot ID
    -> Recovery 写 ota_0
    -> 重启进入 MicroPixel Host
    -> 验证 firmware identity、partition layout、runtime ABI
```

第一次使用的空白或未验证设备仍先执行：

```sh
python mosaico.py recover
```

不允许 `runtime install` 绕过 Recovery 直接调用 `idf.py flash` 或 `esptool`。

## 7. ESP-Iris 与 MicroPixel 控制面集成

### 7.1 USB 所有权

ESP-Mosaico 产品 profile 中，ESP-Iris 是唯一 TinyUSB owner。MicroPixel 当前的
TinyUSB CDC Local Control 不在该 profile 中启动；否则会造成描述符、端点、日志和会话所有权冲突。

MicroPixel 的 `ControlDispatcher` 和 `AppStore` 保持不变，在它们前面新增 ESP-Iris adapter：

```text
ESP-Iris RPC handler
    -> 参数与权限校验
    -> MicroPixel ControlDispatcher
    -> AppStore transaction
    -> 结构化 result / progress / error
```

其他 MicroPixel 板型可以继续保留原有 USB Local Control。禁止在 Runtime 核心中根据
`ESP-Mosaico` 板名分支；通过 transport interface 和 composition root 注入。

### 7.2 `micropixel.apps.v1` RPC

第一版能力建议包含：

| 方法 | 用途 | 幂等要求 |
| --- | --- | --- |
| `runtime.status` | 查询 Host、ABI、AOT、存储状态 | 只读 |
| `apps.list` | 列举已安装游戏 | 只读 |
| `apps.install.begin` | 创建有界上传 session | 相同 operation ID 返回原 session |
| `apps.install.chunk` | 顺序上传 Bundle 数据 | offset 重复必须可识别 |
| `apps.install.commit` | hash 校验并提交 BundleFS | 同一 operation ID 不得重复安装 |
| `apps.install.abort` | 释放未提交 session | 可重复 |
| `apps.launch` | 启动指定 App ID | 返回实际状态 |
| `apps.stop` | 停止当前游戏 | 已停止视为成功 |
| `apps.remove` | 卸载指定 App ID | 已不存在视为成功 |
| `apps.current` | 查询运行中游戏、Trap 和生命周期 | 只读 |

上传约束：

- 一个设备同时最多一个 Bundle 安装 session。
- session 有明确超时和最大 Bundle 大小。
- chunk 必须携带 `operation_id`、offset 和长度。
- `begin` 声明总长度、App ID、SHA-256 和 Bundle 元数据摘要。
- `commit` 只有在完整接收并验证后才调用 MicroPixel `AppStore::Install`。
- 超时、断线或 `abort` 只释放暂存数据，不改变旧 App。
- Gateway 无法确认 `commit` 结果时返回 `outcome_unknown`，不自动重放写操作；随后通过
  operation ID 和 `apps.list` 对账。
- 进度、错误和最终 catalog generation 写入 Gateway 操作记录。

### 7.3 日志与画面

MicroPixel Host 日志通过 ESP-Iris 进入现有 `mosaico.py monitor`。日志记录至少包含：

- Device ID、Boot ID；
- Runtime version/revision；
- App ID、Bundle hash；
- Session 创建、启动、停止和 Trap；
- Bundle 安装 operation ID 和进度；
- BundleFS / 外部 NAND 错误。

屏幕镜像复用 ESP-Iris 的 screen mirror contract。MicroPixel 的显示实现提供稳定的 RGB565
截图或已合成帧，不让 ESP-Iris 直接访问 LVGL 或游戏内部对象。

## 8. Vibe CLI 设计

### 8.1 命令边界

保留：

```sh
python mosaico.py install --project projects/<idf-project>
```

它只安装普通 ESP-IDF 固件。新增：

```sh
python mosaico.py runtime status
python mosaico.py runtime build
python mosaico.py runtime install

python mosaico.py game create <path> --app-id <id> --title <title>
python mosaico.py game build <path>
python mosaico.py game install <path-or-bundle>
python mosaico.py game run <path>
python mosaico.py game list
python mosaico.py game launch <app-id>
python mosaico.py game stop
python mosaico.py game remove <app-id>
```

不让 `install` 根据扩展名隐式判断固件或游戏。两条安装链路的风险、权限和验收不同，CLI
必须保持显式。

### 8.2 `runtime build`

流程：

1. 校验 `runtime.lock.json` 和子模块 revision。
2. 解析 ESP-IDF 6.1 环境。
3. 初始化所需 MicroPixel firmware 子模块。
4. 校验 Vibe 固定的 ESP-Iris 和 BSP 路径。
5. 调用 MicroPixel 原生 S31 Host 构建入口及 Vibe profile。
6. 收集 BIN、ELF、MAP、project description、partition table 和 build manifest。
7. 校验固件尺寸、目标、分区 hash 和固件身份。

构建输出放在 Vibe 忽略的目录，例如：

```text
build/micropixel-host/
```

不得把构建产物写入子模块或提交到 Git。

### 8.3 `runtime install`

流程：

1. 默认先运行 `runtime build`，除非显式 `--skip-build`。
2. 连接 Gateway 并按 Device ID 选择设备。
3. 验证已配置且审核过的 Factory Recovery。
4. 通过 Recovery 写入 MicroPixel Host。
5. 等待同一 Device ID、新 Boot ID。
6. 调用 `runtime.status` 验证 revision、ABI、target 和 partition layout。
7. 保存 BIN/ELF/MAP 对应关系和操作日志。

### 8.4 `game build`

流程：

1. 校验游戏 manifest 和 App ID。
2. 根据 `runtime.lock.json` 选择 SDK、WASI SDK 和匹配的 WAMRC。
3. 编译 C++23 Guest WASM。
4. 检查 imports 是否位于 MicroPixel allowlist。
5. 编译 RISC-V AOT v6。
6. 生成资源、音频和本地化数据。
7. 打包 Bundle v1。
8. 生成机器可读 build manifest 和 SHA-256。

产物建议为：

```text
games/<name>/build/
├── <name>.wasm
├── <name>.aot
├── <name>.bundle.bin
└── build-manifest.json
```

以上均加入 `.gitignore`。

### 8.5 `game run`

`game run` 是开发期组合命令：

```text
build
  -> runtime capability preflight
  -> Bundle upload/install
  -> launch App ID
  -> wait for running state
  -> follow logs
```

Ctrl-C 只停止日志跟随，不默认结束设备上的游戏，行为与 MicroPixel 原 CLI 保持一致。若需要
停止游戏，显式执行 `python mosaico.py game stop`。

## 9. 游戏工程与 GameKit

### 9.1 游戏工程

游戏 manifest 沿用 MicroPixel `app.json`，不定义 Vibe 私有的第二套 manifest。Vibe 可以增加
外部 build manifest，但不能改变 Bundle 内 MicroPixel 元数据含义。

游戏代码只能包含：

- MicroPixel Guest SDK；
- `gamekit/include`；
- 游戏自身源码和生成资源。

禁止包含：

- ESP-IDF headers；
- ESP-Mosaico BSP；
- ESP-Iris；
- Host LVGL；
- 具体板型判断。

### 9.2 GameKit 第一版范围

GameKit 是 Guest 侧轻量公共库，不是第二套 Runtime。第一版只纳入多个游戏明确复用的能力：

- fixed-step update loop；
- 状态机与场景切换；
- sprite animation；
- AABB / circle 2D collision；
- touch gesture 和 action mapping；
- 固定容量对象池；
- pause/resume 辅助；
- 存档 schema/version migration；
- deterministic random/input replay；
- 可关闭的 debug overlay。

暂不引入 ECS、通用物理引擎、Guest 多线程、脚本虚拟机或第二套渲染 API。MicroPixel
现有游戏中的局部 `gamekit` 代码只能作为候选来源；至少两个游戏采用并验证后再升级为公共契约。

## 10. Agent Skills

新增两个按需加载的 Skill：

### `skills/micropixel-game/SKILL.md`

触发条件：创建、修改、构建、安装或调试 MicroPixel 游戏。

应规定：

- 游戏必须位于 `games/<name>`；
- 使用锁定 Guest SDK 和 WAMRC；
- 先运行逻辑单元测试，再构建 release Bundle；
- 设备操作只通过 `mosaico.py game ...`；
- 验收包含启动状态、输入、画面、音频和无 Trap 日志；
- 不直接运行 MicroPixel USB CLI 操作 ESP-Mosaico。

### `skills/micropixel-runtime/SKILL.md`

触发条件：升级 MicroPixel revision、修改 Host、分区、ESP-Iris adapter 或恢复链路。

应规定：

- 检查两个仓库工作树并保护用户改动；
- 固件构建使用 S31 profile；
- 更新 ABI 或分区前先更新设计和测试；
- 固件写入只走 `mosaico.py runtime install`；
- 必须验证 normal -> Recovery -> normal；
- 必须记录 Device ID、Boot ID、固件身份、ELF/MAP 和真机结果。

## 11. 分阶段实施清单

### Phase 0：基线冻结

- [ ] 选定 MicroPixel reviewed commit。
- [ ] 记录 MicroPixel、WAMR、ESP-IDF、ESP-Iris 和 BSP revision。
- [ ] 记录当前 MicroPixel S31 Host 的 release 大小和 RAM/PSRAM 水位。
- [ ] 记录现有 Factory Recovery 安装成功的基线证据。
- [ ] 确认外部 NAND 上 BundleFS 的掉电和格式化行为。

完成条件：所有 revision 和基线结果可复现。

### Phase 1：源码与 Guest 构建接入

- [ ] 添加 `submodule/micropixel`。
- [ ] 添加 `runtime.lock.json`。
- [ ] 新增 `games/hello-game`。
- [ ] 实现 `game create` 和 `game build`。
- [ ] 校验 imports、AOT format、target 和 Bundle hash。
- [ ] 添加 CLI 单元测试，覆盖缺少工具链、revision 不匹配和坏 manifest。

完成条件：无设备情况下可以从 Vibe 稳定生成可验证的 S31 Bundle。

### Phase 2：Recovery-first Runtime

- [ ] 固化 `mosaico-micropixel-v1` 分区表。
- [ ] MicroPixel Host 集成固定 ESP-Iris component。
- [ ] 正常 Host 关闭 OTA writer，仅保留 enter-recovery RPC。
- [ ] ESP-Iris 成为 ESP-Mosaico 唯一 TinyUSB owner。
- [ ] 接入 ESP-Iris 日志和屏幕镜像。
- [ ] 实现 `runtime build/status/install`。
- [ ] 添加固件身份和 runtime capability 上报。

完成条件：相同 Device ID 完成 normal -> Recovery -> MicroPixel normal，Boot ID 正确变化，
Runtime 身份和分区布局验证通过。

### Phase 3：Bundle 设备链路

- [ ] 实现 `micropixel.apps.v1` adapter。
- [ ] 实现有界、可超时、带 SHA-256 的 Bundle 上传。
- [ ] 实现 operation ID、进度和未知结果对账。
- [ ] 实现 `game install/run/list/launch/stop/remove`。
- [ ] Gateway 保存结构化安装证据和原始日志。
- [ ] 增加安装中断、重复提交、坏 hash、坏 AOT 和存储不足测试。

完成条件：修改一个游戏后只上传 Bundle 即可运行，不重刷 Host；断电或传输失败不损坏旧
catalog，设备重启后可确定最终结果。

### Phase 4：GameKit 与体验闭环

- [ ] 选择至少两个游戏验证公共抽象。
- [ ] 抽取 GameKit 最小 API。
- [ ] 添加逻辑单元测试和输入回放。
- [ ] 增加帧率、内存、启动时延和 Bundle 安装时延指标。
- [ ] 建立截图/屏幕镜像验收流程。
- [ ] 完成中英文游戏开发入口文档。

完成条件：Agent 能从自然语言目标创建游戏，完成本机测试、Bundle 安装、真机启动和日志验收。

## 12. 验收矩阵

| 范围 | 必须验证 |
| --- | --- |
| Submodule | gitlink 与 lock revision 一致；干净克隆可按需初始化 |
| Guest build | C++23 编译、imports allowlist、RISC-V AOT v6、Bundle hash |
| Runtime build | ESP32-S31、固件尺寸、分区 hash、ESP-Iris revision |
| Recovery | 相同 Device ID，Recovery ready，Boot ID 变化，凭据和 sysmeta 保留 |
| Runtime boot | 固件身份、ABI、显示、触摸、音频、外部 NAND、无启动错误 |
| Bundle install | 进度、hash、事务提交、catalog generation、断线结果可对账 |
| Game lifecycle | launch、pause/resume、stop、remove、Trap 后返回 Hall |
| Observability | Gateway CLI/Web 显示相同 Device ID、Boot ID、操作记录和日志 |
| Stability | 连续安装/启动循环，内存无持续下降，旧 App 不因失败安装损坏 |

建议首个端到端验收场景：

1. `recover` 初始化设备。
2. `runtime install` 安装 MicroPixel Host。
3. 验证 Runtime、屏幕、触摸、音频和 NAND。
4. `game run games/hello-game`。
5. 修改颜色或移动速度，再次 `game run`。
6. 人为中断一次 Bundle 上传，确认旧游戏仍能启动。
7. 完成一次正常更新，确认 catalog generation 和 Bundle hash 更新。
8. 让游戏产生受控 Trap，确认日志可见且设备返回 App Hall。
9. 执行 Runtime 升级，确认 Recovery 路径和已安装游戏的数据保留策略符合设计。

## 13. 风险与决策点

### 必须优先解决

1. **USB ownership**：ESP-Iris 和 MicroPixel Local Control 不能同时拥有 TinyUSB。
2. **分区迁移**：现有 Vibe 与 MicroPixel S31 分区不兼容，首次切换需要明确迁移流程。
3. **Host 尺寸**：5 MiB 只是设计预算，必须以 release 构建结果确认。
4. **WAMRC 配对**：错误 WAMRC 可能生成无法由固定 Host 加载的 AOT。
5. **未知提交结果**：Bundle commit 超时后不能自动重试写入，必须按 operation ID 对账。

### 实施前需要冻结的产品决策

- 内部 8 MiB `app_store` 是否必须保留全部容量，还是仅保留出厂游戏。
- Runtime 升级时外部 NAND 游戏是否承诺原地兼容。
- 开发 Bundle 是否允许未签名，发布 Bundle 是否强制签名。
- `game run` 是否默认自动停止当前游戏后安装；建议第一版明确提示并由 Host 执行受控 stop。
- GameKit 放在 Vibe 还是 MicroPixel 上游。建议第一版留在 Vibe，API 稳定并跨板复用后再上移。

## 14. 明确禁止项

- 不复制 MicroPixel SDK、ABI 或 Firmware 源码到 Vibe。
- 不把 MicroPixel 整仓库声明成一个 ESP-IDF Component。
- 不直接修改已发布的 ABI ID 或 Bundle 字段语义。
- 不让游戏依赖 ESP-IDF、LVGL Host、ESP-Iris 或板型类型。
- 不让 ESP-Iris 绕过 MicroPixel `AppStore` 直接写 BundleFS。
- 不在正常 MicroPixel Host 中保留独立固件 OTA writer。
- 不用 `idf.py flash`、`esptool` 或 MicroPixel USB CLI 绕过 `mosaico.py` 操作 ESP-Mosaico。
- 不在安装结果未知时自动重复写入。
- 不在未经授权时擦除整片 Flash、身份、凭据、Recovery、sysmeta 或 App Store。

## 15. 首个可合并版本范围

为控制风险，第一个合并版本建议只完成：

1. MicroPixel submodule 和 revision lock；
2. `games/hello-game`；
3. `mosaico.py game build`；
4. Vibe 调用锁定 MicroPixel SDK/WAMRC 生成 S31 Bundle；
5. 完整的本机单元测试和构建 manifest；
6. 两个新 Skill 的最小版本。

这一版本不接触设备和分区。第二个合并版本再完成 ESP-Iris Runtime 集成和 Recovery-first
固件；第三个合并版本完成 Bundle 上传与 `game run`。这样每一步都有独立、可回滚的验收边界。

## 16. PC Simulator 垂直闭环

Linux x86_64 开发机使用 `submodule/micropixel/simulator` 中的固定 WAMR interpreter 和系统 SDL2。
Vibe 把 CMake 输出集中到 `build/micropixel-sim/`，Guest 由固定的 WASI SDK 33 编译为 Wasm，不生成
RISC-V AOT。交互与 headless 前端共享 RGB565 framebuffer、MicroPixel Event/Input/Storage/Audio ABI 和
surface 背压状态；headless 时钟固定为每帧 16667 微秒。

```bash
export WASI_SDK_PATH=/path/to/wasi-sdk-33
python mosaico.py game sim games/mosaic-runner --headless \
  --scenario games/mosaic-runner/scenarios/complete.json --frames 800 \
  --reset-storage --dump-ppm games/mosaic-runner/build/final.ppm \
  --report games/mosaic-runner/build/report.json

# 人工验收（A/D 或方向键、Space/上、R；鼠标模拟触摸）
python mosaico.py game sim games/mosaic-runner
```

场景、报告均使用 `schema_version: 1`。Trap、达到帧上限、没有提交画面、PCM sink 为空、缺少必需日志、
期望退出原因不一致均返回非零。存档只位于 `games/<name>/build/sim-state/`，只有显式
`--reset-storage` 会清空。PC sim 与 GSP sim 并列，MicroPixel 游戏不经过 GSP。

本轮 Host 实现 Graphics GuestSurface、Input、Audio synth 和 Storage；未实现的方法明确返回
`UNSUPPORTED`。平台关卡直接写 MicroPixel DirectSurface RGB565，后续 HostSurface/Raster 扩展必须复用
MicroPixel 已有 raster kernel，不另建图形语义。

## 17. 相关资料

- [Vibe 仓库规格](repository-specification.zh-CN.md)
- [Vibe 中文入口](../README_CN.md)
- [MicroPixel 中文入口](../submodule/micropixel/README.zh-CN.md)
- [MicroPixel 架构](../submodule/micropixel/docs/design/architecture.zh-CN.md)
- [MicroPixel Guest SDK](../submodule/micropixel/guest/sdk/README.zh-CN.md)
