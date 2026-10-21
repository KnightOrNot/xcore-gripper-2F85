# 故障排查

## 串口不存在

```
could not open port /dev/serial/by-id/...: No such file or directory
```

RS485 适配器未插好、掉线或插在另一台机器上。检查 `lsusb` 和
`/dev/serial/by-id/`；适配器不在位时不要反复重启服务。

## 无法激活

夹爪需要外部供电，且串口波特率与协议正确。先 `status`，再 `activate`。
激活会驱动夹爪动作，确认开口范围内没有障碍物。

## TCP 连接失败

客户端默认连接 `192.168.2.225:5005`。检查远端服务状态、防火墙和
`[client].host`。用 `./scripts/start_gripper.sh --status` 做只读检查。

## 目标流超时

`Gripper target stream timed out` 是连续跟随的保护状态。先结束跟随，再用
`set_target`/`stop` 清理空闲锁定；不要通过重启服务掩盖。

## 位置端点不符合实际

`open_pos`/`closed_pos` 是归一化端点，不是机械极限。先观察
`position_raw` 和 `position_mm`，再调整配置。

## 服务无限重启

查看 `journalctl --user -u xcore-gripper-follow.service`。若根因是串口缺失，
先停止 unit，等硬件恢复后再启动。
