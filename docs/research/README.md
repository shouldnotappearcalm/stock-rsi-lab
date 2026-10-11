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
