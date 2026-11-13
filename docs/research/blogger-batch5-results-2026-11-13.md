# 第五批：Hill 趋势缓冲和 Swanson 阴阳线

两套均未通过预登记的40bp两年筛选，未计算本批2026收益。开发前冻结并推送了规则、来源和请求（提交 `81ab1d2`）。

[Arthur Hill，2022-12-03](https://articles.stockcharts.com/article/articles-arthurhill-2022-12-sp-500-crosses-above-200day-sm-360/)：5日均线相对200日均线至少高1%转多，至少低1%转空仓，中间保持信号。[Jeff Swanson，2021-09-27](https://easylanguagemastery.com/indicators/price-pattern-or-indicator/)：选用作者三日下跌、两日上涨退出版本；阴阳线按同一天的收盘和开盘比较。分别从美股指数和期货规则迁移到上证50ETF，结果不代表作者原市场业绩。详细适配见[冻结计划](blogger-batch5-plan-2026-11-13.md)。

| 策略 | 额外单边成本 | 2024净收益 | 2025净收益 | 两年最大回撤 | 平均仓位 | 订单数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hill | 20bp | -5.02% | +12.50% | -10.29% | 77.91% | 3 |
| Hill | 40bp | -5.58% | +12.53% | -10.65% | 78.07% | 3 |
| Swanson | 20bp | -3.69% | -3.87% | -8.69% | 17.27% | 40 |
| Swanson | 40bp | -6.94% | -7.83% | -14.47% | 17.30% | 40 |

费用另含基础单边5bp、单笔最低5元。每个成本档按自己的净值和实际整手成交连续运行，2025分母是本档2024年末净值；不同档的分年净收益不能直接用固定费用差推算。仓位只报告。四个账户未发现未成交订单或缺失持仓估值。

开发行情物理截止2025-12-31；每个交易日15:05根据当日已完成行情形成指令，下一实际开盘模拟执行。另写的审核脚本核对价格来源，以有理数重算指标和状态，逐日核对前收盘账户、订单、费用、库存、净值、收益与回撤。四个账户共1940份决策快照；此前340份策略与证据文件的哈希未变。原始网页抓取留本地，公开URL、日期和哈希，不声称验证当年历史网页存档。

[冻结请求](../../experiments/blogger-batch5/development-request.json) · [来源清单](../../experiments/blogger-batch5/sources.json) · [审核](../../experiments/blogger-batch5/development-results/audit.json) · [快照和账本清单](../../experiments/blogger-batch5/development-results/publication.json)

仍属单ETF工程回放；历史行情到达、逐日官方价格带、完整分红现金账户与开盘可成交容量尚未验收。
