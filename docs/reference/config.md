# 配置参考

默认文件：[config/default.toml](../../config/default.toml)。优先级：

```text
显式命令行参数 > GRIPPER_HOST / GRIPPER_PORT > config/default.toml
```

## server

```toml
[server]
host = "0.0.0.0"
port = 5005
serial_port = ""
activate = true
```

`serial_port` 为空表示自动检测唯一的 USB 串口。服务端不会回退到
`/dev/ttyS*`，避免误开硬件串口。`activate=false` 等价于 `--no-activate`。

## client

```toml
[client]
host = "192.168.2.225"
port = 5005
timeout_s = 10.0
speed = 255
force = 0
```

`host` 是运行服务的主机；`timeout_s` 是单次请求超时。运动和力的默认值
只影响未显式传参的 `open`/`close`/`move`。

## motion / watch

```toml
[motion]
open_pos = 0
closed_pos = 255

[watch]
interval_s = 0.2
```

端点不能相同；实际机械闭合位置可能不是 255，使用前先用 `status` 观察。

## 覆盖

```bash
xcore-gripper-2f85 --config config/experiment.toml status
xcore-gripper-2f85-server --config config/experiment.toml --port 5006
```

未知表或字段会在启动前拒绝；端口必须在 1..65535。
