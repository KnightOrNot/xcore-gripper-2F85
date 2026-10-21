# CLI 参考

```bash
xcore-gripper-2f85 [--config FILE] COMMAND [OPTIONS]
xcore-gripper-2f85-server [--config FILE] [--host H] [--port N] [--serial-port P]
```

`--config` 是 TOML 默认值文件；位置兼容旧形式 `xcore-gripper-2f85 HOST status`。

## 客户端命令

| 命令 | 行为 |
| --- | --- |
| `status` | 读取一次状态 |
| `activate` | 复位并启用夹爪 |
| `open` / `close` | 全开 / 全闭 |
| `move --pos N` | 原始位置 0..255 |
| `move --closure C` | 0.0 全开，1.0 全闭 |
| `move --openness O` | 1.0 全开，0.0 全闭 |
| `watch` | 按周期观察，支持 table/csv/jsonl |

连接参数：`--host`、`--port`、`--timeout`、`--json`。
运动参数：`--speed`（0..255）、`--force`（0..255，0 最轻）。
`move` 还支持 `--open-pos` / `--closed-pos` 调整归一化端点。

## 服务端命令

`xcore-gripper-2f85-server` 的唯一职责是监听 TCP 并控制串口。

```bash
xcore-gripper-2f85-server --config config/default.toml \
  --serial-port /dev/serial/by-id/usb-FTDI_USB_TO_RS-485_...-if00-port0
```

`--no-activate` 启动时不激活；默认行为由 `[server].activate` 决定。

## TCP 协议

请求为一行 JSON：

```json
{"cmd": "move", "pos": 128, "speed": 150, "force": 0}
```

支持 `activate`、`status`、`open`、`close`、`move`、`follow_status`、
`set_target` 和 `stop`。响应为 `{"ok": true, "result": ...}` 或
`{"ok": false, "error": ...}`。

## 退出码

成功 0，连接/协议/夹爪错误 1，参数错误由 argparse 返回 2。
