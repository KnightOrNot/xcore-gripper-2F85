# 安装与部署

## 控制电脑 / 开发环境

```bash
uv sync --project xcore-gripper-2F85 --python 3.11
uv run --project xcore-gripper-2F85 xcore-gripper-2f85 --help
```

运行依赖为 `pyserial`；Python 3.9/3.10 还会自动安装 `tomli` 读取 TOML，
Python 3.11+ 使用标准库 `tomllib`。CLI 不打开串口，只连接 TCP 服务。

## 夹爪所在机器

1. 把 RS485 适配器插到该机器，确认出现 `/dev/serial/by-id/`。
2. 用户加入 `dialout`，重新登录。
3. 修改 `config/default.toml` 的 `[server].serial_port`（空值表示自动检测）。
4. 启动服务：

```bash
xcore-gripper-2f85-server --config config/default.toml
# 或仅本机调试
xcore-gripper-2f85-server --host 127.0.0.1
```

5. 在控制电脑验证：

```bash
xcore-gripper-2f85 --config config/default.toml status
```

## 用户 unit

现场使用 `xcore-gripper-follow.service`，默认 `disabled`，由顶层
`./scripts/start_gripper.sh` 按需 SSH 启动。unit 的 `WorkingDirectory` 和
`PYTHONPATH` 应指向当前部署目录；不要在跟随运行期间重启。

## 故障

适配器不在位时服务会因串口不存在退出并 `auto-restart`。先停止服务、检查
`lsusb` 和 `/dev/serial/by-id/`，不要反复重启或改用其他串口。
