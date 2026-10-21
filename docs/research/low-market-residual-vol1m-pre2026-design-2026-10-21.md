# 一个完整月的低市场残差波动：开发试验

状态：设计定稿于首次真实形成、首次新候选收益之前。本次计入既有低风险/lottery
研究族的一个新增指标trial，不称全新经济族或独立重复验证。价格延迟候选的2026
ST目标失败保留，不通过删ticker、改目标、放宽ordinary守卫或改账户重跑补结果。

## 文献依据与反证

Ang、Hodrick、Xing、Zhang的[2006年论文官方摘要](https://business.columbia.edu/faculty/research/cross-section-volatility-and-expected-returns)
报告高特质波动股票随后平均收益较低。[作者2003年手稿](https://www.ruf.rice.edu/~jgsfss/vol.pdf)
第19页分别定义CAPM与FF3残差，第20页/表8比较一个月形成、随后一个月持有的
quintile组合。本试验取其CAPM式排序思想，改为中国CSI500市场、long-only等权和
本地费用模型；不声称FF3或原文组合复现，也没有原文美国收益可迁移到A股的结论。

[FU的2009年原始研究](https://doi.org/10.1016/j.jfineco.2008.02.003)提示已实现的
滞后特质波动和条件预期风险不是同一变量。因此这里检验的只是过去一个月残差
波动排序，不宣称发现风险补偿机制；若两开发年有一年不盈利，即不晋级。

旧 `low_beta60` 排序60个月收益回归的beta；其control排序60个月total volatility。
旧residual momentum用残差波动作收益评分的分母。本次直接排序一个自然月每日
收益回归的残差标准差，数学量和窗口不同，但经济研究族仍相关，必须计入搜索历史。

## 唯一主候选和来源约束

- 名称 `low_market_residual_vol_1m`，开发2024-01-02至2025-12-31。
- 每月首个实际交易日执行；前一实际交易日收盘15:05形成。成员取当时历史主板
  CSI500 membership。不得使用执行日价格、2026行情或事后ticker黑名单。
- 执行月为M时，取M−1完整自然交易月的全部实际sessions（包含形成日），以及该月首日的前一个session的
  基准收盘；股票所有n+1日close/factor/volume须finite且正。任何缺失或零成交
  整股排除，不拼接、补常数或用更早交易日凑样本。市场仅用CSI500 close；指数
  源没有factor/volume，不制造这两个字段。
  例如2024年1月首日执行，使用2023年12月的全部日收益，基准收盘为2023年11月最后一个session；不额外跳月。
- 对股票及市场简单日收益回归 `y = alpha + beta*x + residual`，以
  `sqrt(sum(residual^2)/(n-2))` 排序，不年化。市场退化或缺失使整月失败，股票
  退化/零残差使该股不合格。市场centered SS或股票residual SSE<=1e-24为固定数值
  退化保护，不据收益修改。完整月须n>=15；该下限是本地来源协议，不冒称
  原文参数。已查看的pre26显式日历2024-02只有15个session，没有查看新因子收益。
- 同一合格pool至少5股；取最低 `floor(N/5)`，ticker确定性打破同分，95%等权。
  只有这1个主trial，不扫窗口、分位、阈值、方向或季度。eligible equal-weight
  和同月total-vol最低quintile只作诊断，不能被晋升为主候选。

## 实施与阶段出口

新增 `src/stock_rsi/low_market_residual_vol.py` 及行为测试；
`scripts/prepare_low_market_residual_vol_pre2026.py` 只形成24个月目标/回归收据；
`scripts/run_qlib_low_market_residual_vol_pre2026.py` 复用既有prior-close Qlib执行、
逐日守恒及费用模型。原有方法文件、账户和源数据不改。每次实际阶段前独立请求
SHA绑定最终方法、设计、全部源哈希，测试/审查/commit/push，固定新目录不覆盖。

复用原已核验的 `qlib-price-delay-pre2026-clock-v2-20261021`：实际day.txt和全部
行情都物理止于2025-12-31；day_future仅已有真实下一交易日2026-01-05的clock
metadata，无任何2026行情。检查4010个既有feature SHA、market close、成员表、
完整日历及manifest。形成器通过AsOfPrices读取，只记录到形成日的字段与回归
alpha/beta/残差sigma/样本日期/排名/选择。先验证全部24次形成和完整性，不算收益。

形成冻结后，独立冻结开发回放：同一100万元、20/40bp两档成本、月度目标，
40bp为预设参考。只主候选在2024、2025各自净收益严格>0、平均exposure>=90%、
无未验证持仓估值且逐日账户/前收盘边界核对通过才保留。两档和controls全部保存，
不因看到结果改指标、排序或费用。Qlib normalized daily-open仍仅工程筛选，不能
替代raw physical shares、企业行动、分钟撮合、PIT或2026收益证据。

本试验不读取2026收益/财务/持仓。项目过去已有2026检查，研究目录还有混合年份
文档的偶然暴露记录，因此不能称整个项目2026样本从未看过或是封存检验。
预26选择与后续2026结果分别记账；未满足三个收益口径前不宣称目标达成。
