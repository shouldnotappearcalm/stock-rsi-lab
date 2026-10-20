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
也已准备 158 特征的股票面板、核对 5 日标签到期和模型前向，尚待训练和回测。
后者完整数据未随仓库提供，默认资源和并发正确性
也需处理。[MASTER 的一次固定开发回测](qlib-master-pre2026-2026-10-16.md)已经完成：
2024—2025 净年化 12.30%，低于同日期 DE 对照的 26.13%，未通过 20% 目标。
这不是对论文原架构的普遍否定，也没有提供新的 2026 验证。

下一条不同经济机制的候选是[财报公告后价格延续的时点数据审计](pead-cninfo-data-admission-2026-10-16.md)：
固定抽样的 12 只主板股票在 2024–2025 有 96 个原始报告事件和 96 对可用隔夜价格；
一次分类漏报需要全文回查，公告时间字段均显示 00:00，因此只能按公告日结束后可见处理。
这一步是小样数据准入，当时未计算策略收益。

随后完成了[501 只历史 CSI500 主板股票的巨潮全量公告、BaoStock 除权日期和一次冻结的 ORJ 信号诊断](pead-orj-full-universe-2026-10-17.md)。
3,985 个可识别原始报告事件中，3,046 个有可用价格配对且次开盘无已列出的除权日；
按预先固定的 60/20 日规则，正隔夜反应并未显示稳健的扣成本超额，候选被拒绝。
这仍不是可投资组合回测，也未读取 2026 价格或收益。

[持续隔夜趋势的弱股回避模块](overnight-avoidance-pre2026-2026-10-17.md)也完成一次预先冻结的检验：
同一 DE 预测上每月降级隔夜趋势最弱的一成，2024 收益由 11.47% 降至 6.96%，
2025 至 12-30 由 44.85% 降至 44.33%，故拒绝晋级且未查询 2026。
用户最新的三段目标见[独立验收登记](../../experiments/a-share-10pct-2026-objective.json)。

[固定低波动策略的盘中执行回放](intraday-execution-results-2026-10-17.md)：前桶定量、五分钟容量、显式子单、逐单收费、开发前缀复现与完整 60 场景披露。

[三项价格收益机制的固定开发筛查](return-families-pre2026-results-2026-10-17.md)：短期反转/长期反转/季节性共三候选，仅长期反转通过原股开发确认。
随后[冻结规则回放 2026](reversal-frozen-2026-results-2026-10-17.md)：全部 60 场景亏损，0/60 达到阶段 10% 数值门槛；保留失败记录，不据此调参。独立审核已重建全部 294,643 笔成交。

[单一日历月 MAX 开发检验](lottery-max-pre2026-results-2026-10-17.md)：先冻结再跑候选/对照和两档费用，
40bp 固定资格档的 2025 年为 −1.12%，候选被拒绝，没有查询它的 2026 收益。四场景 CSV 账本独立汇总已核对，
对照缺价与 Qlib 精度保护导致的请求量差异均单独保留。

[盈利收益率的基本面数据准入](fundamental-value-data-results-2026-10-17.md)：固定 12 股的 5,832 条日估值和 108 条财务行已采集，96 条发布日期匹配原公告；
两份原年报核实 `netProfit` 的总净利口径和归母利润/期末股本与 `epsTTM` 的关系。完整修订版本与历史日股本仍未认证，未计算新策略收益。

[深交所原月报低 PE 开发结果](szse-monthly-value-pre2026-results-2026-10-17.md)补上原始月报数据路径：
24 期原表、24 次固定选股，40bp 压力下 2024/2025 为 +3.09%/+20.30%。
原股开发 60 场景复算通过后再固定运行[2026 诊断](szse-monthly-value-frozen-2026-results-2026-10-17.md)：
100 万/5%/40bp 为 +0.17%/+18.83%/−0.48%，0/60 满足 2026 的 10% 条件，候选失败。
全部开发前缀和完整账本独立复算一致，未依据 2026 改规则。

[接近 52 周高点的开发检验](high52-pre2026-results-2026-10-17.md)固定一次信号、先冻结再跑：
40bp 下 2024/2025 为 +8.97%/+19.70%，平均仓位 88.50%，未通过原定门槛，因此未测 2026。
独立原二进制窗口/排名及 CSV 审计通过；后续停牌来源核对和取整/未成交诊断保留原失败结论。

[高点候选的未成交源探针](high52-execution-source-probe-results-2026-10-17.md)冻结全部 35 个案例：
34 个源有效，其中 21 个出现盘中候选窗口；1 个缺包在两服务器复现协议错误。
未补写成交或收益、未开 2026，原筛查拒绝保留。

[较早 7—12 个月中期动量开发结果](intermediate-momentum-pre2026-results-2026-10-20.md)：
一个事先固定的旧六个月收益信号，40bp 下 2024/2025 为 +12.01%/+18.90%。
平均仓位 89.06% 低于原定 90%，独立重建 24 次形成和四场景后仍判拒绝，没有追加 2026 诊断。

[流动性溢价的固定 22 日筛查](illiquidity-pre2026-results-2026-10-20.md)：
单位小样 5,831 条活跃记录核对通过，四场景和全部 24 次形成独立重建一致。
40bp 下 2024/2025 为 +0.35%/+11.76%，平均仓位 90.48%，通过日频开发资格；原股/盘中确认未完成，尚无新 2026 结果。

[流动性候选原股数据结果](illiquidity-raw-development-data-results-2026-10-20.md)：144 股、69,623 行，176 次续取响应全部持久化并核对，原 75 个检查点保持不变。
两只证券的缺行与原上市/摘牌公告对应；另保留 5 笔非现金分派和潜在 ST 状态。未造行情或自动取得账户准入，尚无新原股收益。

[流动性候选红股账户与生命周期契约](illiquidity-account-contract-2026-10-20.md)：已核对三份实施公告，并增加独立红股账户和生命周期源检查模块，262 项回归通过。
真实事件生成、组合回放接入及盘中源准入仍待完成；模块测试不代表原股确认通过，也没有新 2026 收益。
