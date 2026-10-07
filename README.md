# xcore-gripper-2F85

通过 TCP JSON 协议控制 Robotiq 2F-85 夹爪。夹爪本体挂在**一台**机器的 USB/RS485 上，
那台机器跑 `gripper_server.py`；任意同网段的控制电脑用 `uv run xcore-gripper-2f85` CLI 或 Python API 远程操作。

```
控制电脑  ──TCP:5005──▶  gripper_server.py  ──ModbusRTU/RS485──▶  2F-85
(gripper CLI / SDK)        (USB 所在机器)
```

本项目默认连接 `192.168.2.225:5005`（`GRIPPER_HOST` / `GRIPPER_PORT` 可改）。
原始 Robotiq Modbus 实现在 `src/xcore_gripper_2f85/robtiq_gripper_mdbsrtu.py`（厂商 demo，未改动语义）。

## 安装

```bash
cd xcore/xcore-gripper-2F85
uv sync                      # 安装 pyserial + 两个命令行入口
```

安装后在本目录用 `uv run xcore-gripper-2f85 ...`（或 `uv run xcore-gripper-2f85-server ...`）即可。
也可以不安装，直接用源码树：

```bash
PYTHONPATH=src python3 -m xcore_gripper_2f85 status
```

## 服务端（夹爪 USB 所在机器）

```bash
./run_gripper.sh                                  # 默认 0.0.0.0:5005，自动找 USB 串口
./run_gripper.sh --serial-port /dev/ttyUSB0        # 显式指定串口
GRIPPER_SERIAL_PORT=/dev/ttyUSB0 ./run_gripper.sh
```

`run_gripper.sh` 会依次尝试 `.venv/bin/xcore-gripper-2f85-server`、`PATH` 里的
`xcore-gripper-2f85-server`，最后回退到 `PYTHONPATH=src python3 -m xcore_gripper_2f85.gripper_server`。
找不到 USB 串口时会直接报错并列出探测到的端口，不会误开 `/dev/ttyS*`。

等价的手工启动：

```bash
uv run xcore-gripper-2f85-server --host 0.0.0.0 --port 5005 --serial-port /dev/ttyUSB0
```

> 服务端只应有一个实例占用串口。同一时刻多个客户端可交替发送命令（服务端用锁串行化）。

## 客户端 CLI

在本项目目录执行 `uv run xcore-gripper-2f85 COMMAND [options]`：

```bash
uv run xcore-gripper-2f85 status                     # 读一次状态
uv run xcore-gripper-2f85 activate                   # 激活（reset + enable）
uv run xcore-gripper-2f85 open  --speed 150          # 全开 (pos=0)
uv run xcore-gripper-2f85 close --force 80           # 全闭 (pos=255)，80 为中等夹持力
uv run xcore-gripper-2f85 move  --pos 100            # 原始位置 0..255
uv run xcore-gripper-2f85 move  --closure 0.4        # 归一化：0.0=全开，1.0=全闭
uv run xcore-gripper-2f85 move  --openness 0.6       # 归一化：1.0=全开，0.0=全闭
uv run xcore-gripper-2f85 move  --closure 1 --open-pos 2 --closed-pos 230   # 用实测机械行程
uv run xcore-gripper-2f85 watch  --interval 0.2      # 实时观测，Ctrl-C 停止
uv run xcore-gripper-2f85 watch  --duration 5 --format csv
uv run xcore-gripper-2f85 watch  --samples 20 --format jsonl | tee gripper.jsonl
```

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--host` / `--port` | 服务端地址；也可用位置参数 `uv run xcore-gripper-2f85 192.168.2.225 status`（兼容旧写法） | `192.168.2.225` / `5005` |
| `--speed` | 运动速度 0–255 | `255` |
| `--force` | 夹持力 0–255，`0` 最轻 | `0` |
| `--timeout` | 单条命令超时（秒） | `10` |
| `--json` | 输出服务端原始 JSON | 关 |
| `--open-pos` / `--closed-pos` | 仅 `move`：使用 `--closure`/`--openness` 时把哪两个 raw 值当作全开/全闭，用于按实测机械行程标定 | `0` / `255` |

**位置约定**（全文统一）：

* `pos`：Robotiq 原始值，`0` = 全开，`255` = 全闭。
* `closure`：归一化，`0.0` = 全开，`1.0` = 全闭。**与 GELLO 主手夹爪轴方向一致**
  （`gripper_config` 决定的 `(raw - 全开角) / (全闭角 - 全开角)`），可直接对接。
* `openness`：`1.0` = 全开，`0.0` = 全闭，只为方便阅读。

**实测机械行程**（本机 + `192.168.2.225` 上的这台 2F-85，空夹）：

| 动作 | 指令 | 实测 `position_raw` | 实测 `position_mm` |
| --- | --- | --- | --- |
| 全开 | `open` | ≈2–3 | 49.4–49.6 |
| 全闭 | `close --force 80/150/255` | ≈230 | 4.9 |
| 全闭 | `close --force 30` | 226 | 5.69 |
| 中间位 | `move --pos 100` | 100 | 30.0 |

所以协议端点 `0/255` 与真实机械端点不完全重合：行程两端各有约 1%–10% 的死区，
且 `--force` 过小（如 30）会因夹持力不足提前停下。遥操作时建议
`move_closure(g, open_pos=2, closed_pos=230, force=80)`，把主手全行程映射到真实行程。

`status` 输出示例：

```
status_code=249 (到位(无物体)) position_raw=3 position_mm=49.41 moving=False
closure=0.012 (0=全开, 1=全闭) openness=0.988
```

状态码：`0x31` 已激活/待命、`0x39` 运动中、`0x79` 外撑到位、`0xB9` 夹取到位、`0xF9` 到位（无物体）。

`watch` 三种输出格式：`table`（默认，人类可读）、`csv`（表头 + 样本，便于落盘）、
`jsonl`（每行一个 JSON，含 `wall_time`、`monotonic_ns`、`position_raw`、`position_mm`、`closure`）。
每行都可通过 `tee` 直接存成数据集原始文件。

## Python API

```python
from xcore_gripper_2f85 import Robotiq2F85, closure_to_pos, pos_to_closure

gripper = Robotiq2F85("192.168.2.225")     # 省略参数则用 GRIPPER_HOST/GRIPPER_PORT
gripper.activate()
gripper.open()
gripper.move(pos=100, speed=150, force=0)
gripper.move_closure(0.4)                  # GELLO 归一化值直接传入
gripper.move_closure(0.4, open_pos=2, closed_pos=230, force=80)   # 实测行程 + 夹持力
gripper.move_openness(0.6)
print(gripper.status())                    # {'status_code': 249, 'position_raw': 102, ...}
print(gripper.closure())                   # 0.4
```

GELLO 主手 → 夹爪的最小接线（由使用方自行放入跟随循环）：

```python
gello_gripper = leader_state[6]            # 0=全开, 1=全闭
gripper.move_closure(gello_gripper, speed=150, force=80,
                     open_pos=2, closed_pos=230)
```

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `GRIPPER_HOST` / `GRIPPER_PORT` | 客户端默认地址与端口 |
| `GRIPPER_BIND_HOST` / `GRIPPER_BIND_PORT` | `run_gripper.sh` 监听地址与端口 |
| `GRIPPER_SERIAL_PORT` | `run_gripper.sh` 传给服务端的串口 |

## 协议

一行一个 JSON。

请求：

```json
{"cmd": "move", "pos": 100, "speed": 255, "force": 0, "timeout": 10.0}
```

`cmd` ∈ `activate` | `status` | `open` | `close` | `move`。

响应：

```json
{"ok": true, "result": {"status_code": 249, "position_raw": 100, "position_mm": 30.39, "moving": false}}
{"ok": false, "error": "..."}
```

## 测试

不需要硬件，用本地假服务端覆盖 CLI、归一化映射与错误路径：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t tests -v
```

## 已知注意事项

1. **反馈语义已实测确认为实际位置**：`position_raw` 不是指令回显。
   证据：`move --pos 100`（空夹、能到位）返回 `100`；而 `close --force 30` 请求 `255`
   只返回 `226`，`close --force 255` 返回 `230`。因此它可以作为观测值写入数据集。
   但它读的是 `robtiq_gripper_mdbsrtu.py` 里 `ReadGripperStatus` 的 `response[7]`，
   与厂商寄存器文档的对应关系没有逐字节核对；若后续需要电流 `gCU`、物体检测 `gOBJ`
   等字段，应重新核对该寄存器映射。
2. `src/xcore_gripper_2f85/demo.py` 是厂商顶层的死循环脚本，只能用 `PYTHONPATH=src` 手动运行，
   正常运行请用 `uv run xcore-gripper-2f85` CLI。
3. 夹爪运动前请确认夹口内无手、无线缆；首次试夹建议 `--force 30` 左右，确认方向正确后再加大。
4. `close` 不会真正到达协议端点 `255`（实测 ≈230），这是机械限位而非故障；
   需要判断"是否夹紧"时请用 `closure >= 0.85` 之类的阈值，不要判断 `== 255`。
