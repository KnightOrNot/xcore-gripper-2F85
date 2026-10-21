# 更新记录

## 2026-10-21

- 配置加载保留 Python 3.9/3.10 兼容（条件依赖 tomli），在设备操作前拒绝非法类型与非有限数值。

- 新增 `config/default.toml`、`configuration.py` 和 `--config`：
  服务端与客户端的 host、port、串口、运动默认值统一来自 TOML。
- 环境变量 `GRIPPER_HOST` / `GRIPPER_PORT` 仍优先于文件。
- 新增 `docs/`、`CONTRIBUTING.md` 和本文件。

## 2026-10-08

- 连续目标跟随、看门狗和断流保护。
- TCP JSON 服务与客户端 CLI。

## 早期版本

- Robotiq 2F-85 的 Modbus RTU 驱动与基础命令。
