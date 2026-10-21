# Amihud22 归档源情景：实际构建与独立审计

源工程这一步完成；账户回放尚未开始，三个收益条件均未由本次运行证明。

方法在提交 `d12fdced077d6bf8ec2f812c9aa2b32c4ed2e85c` push 后才应用到真实行。
请求 SHA 为 `c917b4c4cde4a6ce13d626e0ccc8f1f80f6875c08b417e07d98b29c6ba4a191c`。
运行正常退出，2512 个固定输入连同请求自身共 2513 项前后哈希全部不变。

| 项目 | 实际结果 |
|---|---:|
| 固定活跃日期 | 2276，全量保留并通过情景构建 |
| 非执行源区间 | 18，原样保留 |
| 原 TDX 路由 | 2247，仍按原 240 标签、5 根一组 |
| 独立归档路由 | 29，每日 241 根，48 个窗口 |
| 归档原记录 | 6989，全部审计留存 |
| 窗口内部记录 | 5568，用于容量和条件化买卖价格 |
| 保留排除记录 | 1421，不计执行容量 |

29 日各四个解码后全日 OHLC 及全日股数成交量均与原股日源相等。每个归档
窗口只使用在起点/终点标签两种解释下都完整位于窗口内的四根记录，量不重复。
逐日保留的成交量约占原全日量的 63.45%–84.39%；原始记录没有删除或移时。

独立 stdlib 审计不导入项目方法，重新推导了 2276 个活跃键、18 个非执行区间、
2247 个旧路由窗口、29 份完整投影的全部字段、binary32 位型与唯一整分原像、
全日 OHLCV、时钟、容量、价格和 evidence ID。2513 个输入、34 个输出前后哈希
一致。缺标签、非唯一价格原像、投影篡改、源哈希篡改四项合成负例均被拒绝。
主代理从已保存的独立脚本再次运行，报告逐字节一致。

原 240 标签准入仍为 false。新情景依赖整分网格、binary32 精确提升与两种标签
解释的明确假设；不能认证供应商、历史到达、其他时间约定、排队或冲击。
深交所历史正式价格网格条文尚未取到。此次只消费已筛选的 2024–2025 JSON，
对完整跨年 Parquet 只核哈希，不解码其值，不声称获得 OS 未来数据隔离。

源构建代码的中断与篡改回归已覆盖请求自身后验绑定、部分结果、首错、逐项
输入复核和落盘失败诊断。冻结提交的 GitHub Actions 三项任务全部成功：
[运行记录](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39635794544)。

下一步另行冻结完整 60 场景原股账户计划。保留原 ST、税务权益、登记股数、
退市退出守卫，不因源覆盖完整而跳过。2026 不参与本次方法或路由选择。

账户侧的 `ScenarioTapeBank` 已写出并通过六项合成回归和独立代码审查。每次
缓存命中仍检查原包、投影、选中原记录 SHA 及窗口摘要，拒绝范围外与 2026
日期。它只接受上游已认证的来源上下文，本次没有真实账户调用；加载器与账户
计划尚待冻结。当前完整本地回归为 900 项通过。

机器证据：

- `experiments/qlib/illiquidity-archive-scenario-source-results.json`
- `experiments/qlib/illiquidity-archive-scenario-source-run-verification.json`
- `experiments/qlib/illiquidity-archive-scenario-independent-source-audit.json`
- `experiments/qlib/audit_sources/2026-10-22-illiquidity-archive-scenario-independent-source-audit.py`
