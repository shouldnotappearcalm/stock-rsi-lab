---
name: a-share-blogger-faber10
description: 回放Meb Faber月末十个月均线的境内ETF适配，保留来源差异和执行边界。
---

读取[skill.json](skill.json)。独立规则解释器为stock_rsi.blogger_batch3，来源和完整预先定义见experiments/blogger-batch3/sources.json与docs/research/blogger-batch3-plan-2026-11-01.md。使用完整实际会话和可见价格，信号频率不得改为日频。账户预算、订单取整、已实现现金与执行状态由harness管理。

这是境内资产适配，市场、现金收益、费用、成交时刻及债券期限与原文不同，不声称复现作者实盘。先冻结、测2024/25，再冻结所有通过者测2026。保留失败，不按2026改规则或添加仓位门槛。
