# 第六批：月末效应和 Halloween

两套日历规则都未通过预先登记的额外单边40bp两年筛选；本批未算2026。规则、输入和开发请求在运行前已推送冻结（`6c6cd8a`）。

| 上证50ETF适配 | 额外单边成本 | 2024净收益 | 2025净收益 | 全期最大回撤 | 平均仓位 | 订单数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| McConnell / Xu 月末效应 | 20bp | -0.43% | -11.72% | -13.74% | 18.84% | 49 |
| McConnell / Xu 月末效应 | 40bp | -5.07% | -15.69% | -19.97% | 18.88% | 49 |
| Bouman / Jacobsen Halloween | 20bp | +6.26% | -0.42% | -7.91% | 47.46% | 5 |
| Bouman / Jacobsen Halloween | 40bp | +5.66% | -0.80% | -7.92% | 47.55% | 5 |

另计基础单边5bp、最低5元。四账户均无未成交订单、无缺失持仓估值。每年收益以实际连续账户年初净值计算。仓位只报告。

[月末效应论文](https://business.purdue.edu/faculty/mcconnell/publications/Equity-Returns-at-the-Turn-of-the-Month.pdf)观察月末最后一个交易日与次月前三个交易日的日收益。本项目从月末最后一日开盘持有到次月第四日开盘，不等价于原论文的收盘收益窗口。[Halloween 论文](https://doi.org/10.1257/000282802762024683)的11–4月股票配置在本项目按对应月份首个实际开盘切换；5–10月用零息现金，未复制国库券收益。两套都只在上证50ETF验证，不能推断原文市场的效应失效。

使用真实交易日历；额外的下一交易日期只用于判断报价截止日是否为月末，不含该日行情。独立脚本重新分组交易日并复算目标、前收盘账户、订单、源开盘价、费用、逐日账本及分年指标。四账户共1,940份快照；此前374份策略与证据文件的哈希未变。原始论文PDF留本地，公开来源及哈希。当前复权、开盘代理和工程价格带依旧是工程验证口径。

[规则与适配](blogger-batch6-plan-2026-11-14.md) · [来源](../../experiments/blogger-batch6/sources.json) · [冻结请求](../../experiments/blogger-batch6/development-request.json) · [独立审核](../../experiments/blogger-batch6/development-results/audit.json) · [账本与快照清单](../../experiments/blogger-batch6/development-results/publication.json)
