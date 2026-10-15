# 多项目代码审计与取舍

以下来自此前clone后的源码审计；固定到commit，可回查具体实现。新项目只借鉴接口与验证思想，未复制这些项目源码。

| 组成部分 | 来源与固定代码位置 | 本项目取舍 |
| --- | --- | --- |
| 模块契约与组合 | [ModularRSI](https://github.com/IQuestLab/ModularRSI/blob/b5c72c36b0d08ff93f00ee202a8fbdebe849dfb9/src/harbor/agents/terminus_2_modular/protocols.py#L355) | 借接口和设计，金融模块重新定义；运行内核、评分器与策略进程隔离 |
| 定向反思与修改 | [GEPA](https://github.com/gepa-ai/gepa/blob/462e437a09be67d2acb59564cc0ea59132f5777c/src/gepa/core/adapter.py#L83) | 作为可替换 proposer 接口；不能将默认 minibatch 分数提升视为金融晋级证据 |
| 候选验收与成本控制 | [RRSI](https://github.com/google-research/rrsi/blob/be50316e1db05914068a973f322770ef08ed7ba1/rrsi/selection.py#L97) | 保留非补偿闸门；加完整性、有限数值、时间序列配对与多轮检验预算 |
| 分支、合并和回滚 | [ModularRSI](https://github.com/IQuestLab/ModularRSI/blob/b5c72c36b0d08ff93f00ee202a8fbdebe849dfb9/src/harbor/agents/terminus_2_modular/self_evo/promotion.py#L77) | 晋级前补真实金融 OOS 验收；不能直接搬 binary reward>=1 的确认统计 |
| 历史环境与回测适配 | [Qlib + TraderHarness](https://github.com/HephaestLab/TraderHarness/blob/3e18369da5a2060f9c65b27c2a63f99edd93e167/traderharness/core/engine.py#L694) | 只作为 evaluator 后端组件；重写隔离与 CN/US 规则贯通，不暴露原始对象 |
| 轨迹与回归回放 | [TraderHarness](https://github.com/HephaestLab/TraderHarness/blob/3e18369da5a2060f9c65b27c2a63f99edd93e167/traderharness/trajectory/replay.py#L23) | 加入源码、数据、规则、模型及输出摘要；固定响应回归和历史环境重跑分开 |
| 研究实验协议 | [RD-Agent](https://github.com/microsoft/RD-Agent/blob/484776c211e4fbbeef03e0ec00d6bbee7362a4f4/rdagent/core/experiment.py#L58) | 提炼轻量协议，避免全局 settings、latest-recorder 和默认 test 反馈接线 |
| 轨迹谱系与经验复用 | [QuantaAlpha](https://github.com/QuantaAlpha/QuantaAlpha/blob/b7ceb27b1001261d7a95b209a963664ae1f8ab23/quantaalpha/pipeline/evolution/controller.py#L762) | 提炼 lineage 思路；保留原始结果；质量检查异常不能通过；复制源码前核对许可 |
| 金融角色与时点记忆 | [TradingAgents](https://github.com/TauricResearch/TradingAgents/blob/1394a3f72aa4393e1a98f51b382434c4b4c2d972/tradingagents/agents/schemas.py#L1) | 角色只是可替换 seed；增加 evidence_ref、数量/价格/仓位约束、端到端决策链 |
| 实验可观测性 | [AgentQuant](https://github.com/OnePunchMonk/AgentQuant/blob/1d2331002c3e98af33142b081c72e4071526a00e/src/agent/harness_config.py#L232) | 借数据契约；重写 knob wiring、统一 memory schema、finite metric/split checks |

完整仓库SHA及审计事实保留在source-audit.json。AgentQuant等金融agent项目作为角色/管线参考，并不直接成为投资内核。当前实现范围和未完成部分见../roadmap.md。

数据层另见[A股数据源审计（2026-10-14）](a-share-data-source-audit-2026-10-14.md)：
已实际下载并校验 2026-10-13 全市场 Qlib 快照，同时核对 Tushare、BaoStock、
AKShare、JQData 的字段、权限与许可边界。

投资模块实验另见[Qlib pre-2026 基线](qlib-pre2026-development-2026-10-15.md)和
[EnhancedIndexing 组合模块进化](qlib-enhanced-indexing-pre2026-2026-10-15.md)。两者都只
是 2024—2025 开发证据；后者没有读取或复跑已经暴露的 2026 区间。

用户随后明确要求运行 2026，结果单独记录在
[EnhancedIndexing 2026 污染区间诊断](qlib-enhanced-indexing-frozen-2026-diagnostic-2026-10-15.md)。
它是失败迁移记录，不是新的验证集，也不向后续方法提供反馈。

后续独立检索见[RSI 金融搜索第二轮](rsi-finance-search-round2-2026-10-15.md)：固定源码审计
FactorMiner、QuantaAlpha 和 MOSAIC，并在不读取 2026 的前提下实跑 MSE、top-weighted
MSE、LambdaRank 三种组合目标。三者均未通过 20% 开发门槛，因此没有晋级或追加 seed。

后续预测模块探针包括[20-session 静态 LGB](qlib-horizon20-pre2026-2026-10-15.md)、
[滚动 LGB](qlib-rolling20-pre2026-2026-10-15.md)、
[滚动 Ridge](qlib-rolling-ridge20-pre2026-2026-10-15.md)、
[快慢信号等权组合](qlib-multihorizon-blend-pre2026-2026-10-15.md)、
[TRA 首轮因果回放](qlib-tra-first-pass-pre2026-2026-10-16.md)及
[DE＋TRA 固定组合](qlib-de-tra-blend-pre2026-2026-10-16.md)。这些均只使用
2026 年之前的数据；最后的固定组合未通过 20% 开发门槛。

组合失败后又独立克隆和审阅了
[MASTER 与 MASS](master-mass-source-audit-2026-10-16.md)：前者需要重建 2024—2025
市场特征并重新训练；目前已通过三条指数数据重建了前者的 63 个市场特征，
仍未完成股票序列、训练和回测。后者完整数据未随仓库提供，默认资源和并发正确性
也需处理。两者目前都不能转成收益声明。
