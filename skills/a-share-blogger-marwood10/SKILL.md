---
name: a-share-blogger-marwood10
description: 回放Joe Marwood的固定日频规则A股ETF适配，核对实际持仓、来源和次日成交边界。
---

读取[skill.json](skill.json)，由stock_rsi.blogger_batch4和blogger_batch4_qlib解释。
完整定义见docs/research/blogger-batch4-plan-2026-11-01.md；来源见experiments/blogger-batch4/sources.json。
账户、日历、费用和撮合由harness管理。只读取as_of以前的完整日线；不跳过缺价，不按2026改规则。
先冻结并测2024/25，各年为正者再冻结跑2026，保留全部失败。仓位只报告。
这是单只境内ETF适配，不代表原作者实盘；Marwood止损在收盘后观察已完成low，下一开盘退出，不保证盘中止损价成交。当前复权、原始整数份额和真实开盘容量未经投资级验收。
