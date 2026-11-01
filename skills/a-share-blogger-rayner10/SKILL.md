---
name: a-share-blogger-rayner10
description: 回放Rayner公开趋势内均值回归规则的上证50ETF适配版本，绑定来源和预先冻结假设。
---

读取[skill.json](skill.json)，解释器stock_rsi.blogger_batch2。来源见experiments/blogger-batch2/sources.json，所有口径见docs/research/blogger-batch2-plan-2026-11-01.md。只接受截至as_of的完整日线与实际账户；现金预算、持仓计时和撮合不归skill修改。

保留原规则与适配区别，不声称复现作者实盘。先冻结再测2024/25，两个年份均盈利者才跑2026。不得根据2026改窗口、阈值、品种或费用；平均仓位没有硬门槛。
