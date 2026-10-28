# 第一次回放失败与纯时钟修复

首次冻结提交 `86f91742c763cf1f98cb84cb0f14299b5d140fe7`；请求SHA256为 `076be09b09bf5943edfd1f685eecd19d1cf201b55d4e2ac2c53df4c8c79a41ea`。20/golden_cross在2025最后一天触发Qlib TradeCalendarManager.get_step_time的exclusive右端点越界。没有完整指标、CSV或可晋级收益结果。保留V1输入、请求及原生失败terminal，不覆盖或冒充成功。

检查本地Qlib源码确认：future=True的日期表需要下一实际session作为末日区间右端点。复用项目已验证的 `clock_calendar`，将原始日期表里的2026-01-05写入**仅日历元数据**day_future.txt。正常day.txt仍截止2025-12-31；24个行情二进制文件、原股票身份和全部实际模拟session逐字节相同，不增加2026报价、订单或模拟session。

原始三套skill、信号模块、订单适配器、基础运行器、成本、开发门槛和原来源全部保持原字节。V2入口只额外校验修复后的元数据并绑定这次修复脚本和回归；单独请求、提交后重跑全部六个账户。不是根据收益优化策略，V1未产生完整收益结果。

复现入口为 `PYTHONPATH=src:. python -m scripts.run_published_strategies_clock`；模式freeze/preflight/run与基础运行器相同。数据准备入口为 `PYTHONPATH=src:. python -m scripts.prepare_published_strategy_clock`。V1已保留，不允许原地覆盖。
