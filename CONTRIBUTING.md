# 贡献与开发检查

## 规则

- 默认值放入 `config/default.toml`，CLI 参数优先。
- 不把夹爪初始化、激活或运动命令放进导入路径或 `--help`。
- 串口、协议和 TCP 服务保持分离；服务端不依赖控制电脑环境。
- 不提交现场串口日志、`.venv` 或设备序列号以外的私密信息。

## 检查

```bash
uv run --project xcore-gripper-2F85 --with pytest --with ruff pytest -q
uv run --project xcore-gripper-2F85 --with ruff ruff check src
```

测试使用假串口和本地假服务，不连接真实夹爪，也不会激活设备。
