# 公开来源策略保留目录

每套规则、冻结请求、来源证据和成功/失败结果都在Git中保留，不用新结果覆盖旧规则。目录中的策略是项目研究适配，不代表原作者实盘或已取得投资资格。

| 规则 | 可调用skill | 最新结果 |
| --- | --- | --- |
| MACD公开规则 | [配置](../skills/a-share-published-macd/skill.json) | [2026截至10-27，40bp为-11.36%](research/published-strategies-2026-results-2026-10-28.md) |
| RSI公开规则 | [配置](../skills/a-share-published-rsi/skill.json) | [2026截至10-27，40bp为+8.20%](research/published-strategies-2026-results-2026-10-28.md) |
| 持有封基20日版 | [配置](../skills/a-share-blogger-fengji20/skill.json) | [2026年1—10月，40bp为-8.40%](research/blogger-2026-results-2026-11-01.md) |
| 持有封基19—21日均价版 | [配置](../skills/a-share-blogger-fengji-mean/skill.json) | [2026年1—10月，40bp为-8.65%](research/blogger-2026-results-2026-11-01.md) |
| plus2047代码版 | [配置](../skills/a-share-blogger-plus2047/skill.json) | [2026年1—10月，40bp为-11.82%](research/blogger-2026-results-2026-11-01.md) |
| BigQuant收盘通道适配 | [配置](../skills/a-share-blogger-bigquant20/skill.json) | [2024/25分别-3.16%/-6.42%，未入2026](research/blogger-batch2-results-2026-11-01.md) |
| Rayner趋势内均值回归适配 | [配置](../skills/a-share-blogger-rayner10/skill.json) | [2024/25分别-1.39%/+0.46%，未入2026](research/blogger-batch2-results-2026-11-01.md) |
| Meb Faber月末十个月均线适配 | [配置](../skills/a-share-blogger-faber10/skill.json) | [2024/25通过，2026年1—10月40bp为-9.15%](research/blogger-batch3-results-2026-11-01.md) |
| 怪老子年度股债配置适配 | [配置](../skills/a-share-blogger-glaozi50/skill.json) | [2024/25通过，2026年1—10月40bp为-1.99%；整手拒单边界保留](research/blogger-batch3-results-2026-11-01.md) |
| Cesar Alvarez RSI(2)连续下跌适配 | [配置](../skills/a-share-blogger-alvarez2/skill.json) | [2024/25在40bp为-3.23%/-0.61%，未入2026；20bp两年小幅盈利](research/blogger-batch4-results-2026-11-01.md) |
| Joe Marwood均线回撤及止损适配 | [配置](../skills/a-share-blogger-marwood10/skill.json) | [2024/25在40bp为-13.49%/-13.83%，未入2026](research/blogger-batch4-results-2026-11-01.md) |

表内40bp均指基础费用之外的额外单边压力成本；不同市场/个股/ETF适配及截止日期按各原报告，不能混为同一标准。平均仓位只报告，不设助手自行添加的硬门槛。2026已曝光，后续研究不得用其反调规则。

前五套的171份规则、请求及结果在[原文件指纹清单](../experiments/strategy-library/retained-2026-11-01.json)中逐项绑定，本批前后均验证相同。第二批另有[独立来源清单](../experiments/blogger-batch2/sources.json)、[冻结请求](../experiments/blogger-batch2/development-request.json)和[全部开发账户](../experiments/blogger-batch2/development-results/terminal.json)。项目其余历史研究仍保留在原`docs/research`与`experiments`目录。

第三批增加两位作者，共九套公开来源skill。此前七套相关210份文件仍由[第三批保留清单](../experiments/strategy-library/retained-before-batch3-2026-11-01.json)绑定，第三批两套的开发/2026完整过程均保留，没有覆盖旧策略。

第四批增加Alvarez、Marwood，共十一套。此前九套相关306份旧文件由[第四批保留清单](../experiments/strategy-library/retained-before-batch4-2026-11-01.json)绑定，四个开发账户及失败结果完整公开；两套均未通过预先登记的40bp两年筛选，本批未计算2026收益。
