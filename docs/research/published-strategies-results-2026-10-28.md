# 三套有历史时间戳的公开A股策略：抽象、回放与拒绝记录

后续状态：用户明确取消平均仓位90%的阻断条件，MACD、RSI的[2026冻结回放现已完成](published-strategies-2026-results-2026-10-28.md)。以下保留首批历史记录。

本批完成3套来源核验、3个项目skill和6个2024—2025连续账户。**MACD和RSI两套在较高成本口径下两年均盈利；本批没有通过完整高仓位筛选的候选，因此没有读取2026报价、没有2026收益结果。** 不能把未运行写成收益0或亏损。

## 来源

米筐原始公开仓库 [RQAlpha](https://github.com/ricequant/rqalpha)，选择 [2017-04-07历史提交](https://github.com/ricequant/rqalpha/commit/64937228246d658892fc28d0cb17f1aeeabe1c1b)，作者和提交时间均为22:32:40+08:00。Git元数据不是可信时间戳机构或实盘交易鉴证，但可检查确切代码对象。克隆后保存原始commit对象、文件blob SHA1/SHA256和当时Apache-2.0许可证，未套用后续2024—2026代码。见 `experiments/published-strategies/source-manifest.json`。

- [golden_cross.py](https://github.com/ricequant/rqalpha/blob/64937228246d658892fc28d0cb17f1aeeabe1c1b/rqalpha/examples/golden_cross.py)：固定平安银行，20/120日简单均线严格交叉，121根历史。
- [macd.py](https://github.com/ricequant/rqalpha/blob/64937228246d658892fc28d0cb17f1aeeabe1c1b/rqalpha/examples/macd.py)：固定平安银行，12/26/9交叉；每天重新用最近100根收盘初始化。
- [rsi.py](https://github.com/ricequant/rqalpha/blob/64937228246d658892fc28d0cb17f1aeeabe1c1b/rqalpha/examples/rsi.py)：按原顺序使用平安银行、中国银行、华控赛格。15根收盘计算14日RSI，低于30按剩余现金30%连续补仓，高于85清仓。

这些是原发布方的教学策略，不是三位交易者的实盘业绩，也不是三个独立收益机制。两套只交易同一家银行，不能据此推断全A股有效。另有被排除的数字货币海龟示例、开发期后修改的文章和缺少历史版本证据的网页，排除原因在来源清单中。

## skill与适配

位于 `skills/a-share-published-golden-cross`、`skills/a-share-published-macd`、`skills/a-share-published-rsi`，每个都有SKILL.md和唯一绑定的skill.json。参数与原始代码常量有回归检查，运行器拒绝不一致参数。没有优化均线、MACD、RSI阈值、股票池或候选组合。

明确适配：原100%仓位改为95%权益上限；每天实际交易日15:05唤醒一次，在下一实际交易日09:30日线开盘代理成交。只以已收盘历史和实际账户生成委托；RSI顺序预留现金、不预支未成交卖单收入。没有信号时不强行补满仓。原平台即时成交等执行语义不声称被完全复刻。

该回放没有模拟一个人当天看到的所有新闻、公告和盘口。输入只含已指定价量字段、指标窗口和账户；“15:05可见”是重建约定，不是历史实际到达证明。

## 最终第三版结果

100万元独立连续账户，2024-01-02至2025-12-31，不按年重置。下表基础买5/卖15基点、最低5元之外，额外每边40基点；完整20/40基点六组均公开在results.json。

|策略|2024净收益|2025净收益|平均仓位|两年最大回撤|
|---|---:|---:|---:|---:|
|20/120均线交叉|+0.319965%|-0.571651%|41.530446%|13.503497%|
|12/26/9 MACD|+5.176454%|+9.390950%|41.501405%|13.327192%|
|14日RSI分批买卖|+25.904517%|+8.138343%|75.083705%|30.436397%|

MACD和RSI通过“两年均正收益”这一项。当前批次在实际收益计算前冻结的完整条件还要求平均仓位至少90%和未验证估值为0；前两者的平均仓位分别约41.50%和75.08%，所以没有候选晋级。90%是沿用项目高仓位目标的实验条件，不是统计定律，也不应把它混同于用户的“两年都赚钱”这一单项条件。没有根据看到的结果临时下调仓位条件。

全部未验证持仓估值为0，并不意味着历史ST、税费、公司行动或原始股数资格已经证明。

## 实际审核与修复

1. 第一次请求在末日遇到Qlib exclusive右端点日历越界，没有完整收益。原失败保留。第二版只把来源日历中的2026-01-05作为day_future时钟右端点加入，正常报价日历仍截止2025-12-31；24个行情二进制文件和投资规则逐字节相同，没有增加2026报价或模拟session。
2. 第二版完整账本通过后，严格执行检查发现33笔成交略超委托，最大约0.0806155711股等价量。定位到Qlib原取整函数加0.1股的精度补偿，未放大验收容差。保存旧结果和失败清单。
3. 第三版只引入保守向下取整Exchange，在回放前提交冻结 `ab82c91`；源信号、skill、股票、预算、日期、成本与数据都不变。全部账户重新运行，不能复用第二版收益。严格超量检查最终为0。
4. 标准库检查器复核2910个收盘快照、258020个实际历史窗口值、225条订单，以及逐日现金、费用、持仓、净值、年收益。另一检查器核对源开盘成交价、收盘估值、原始委托量、已知现金预算和必要全日容量条件。这些是同一研究者的交叉检查，不是独立审计鉴证。
5. 最终完整回归1650项通过，包括TA-Lib合成参考、未来字段扰动、严格交叉边界、冻结与失败隔离、10000组严格取整性质检查。此前本地一次错误导入路径和一次回环HTTP沙箱权限错误被保留在临时日志中，正确启动方式及完整测试权限下最终通过；未为通过测试修改旧生产文件。

## 证据边界与2026

这是Qlib复权日频工程筛查。尚未证明原始整数股、T+1、分红现金与税费、历史ST、真实逐日价格边界、证券状态及开盘冲击。全日归一化成交量必要条件不是开盘流动性证明，不能据此声称可实盘复现。三套固定股票不使用财报筛选，原财报研究的100只门槛完全没有修改。

本批最终 `passed_full_development_gate=[]`、`2026_return_pct=null`、`2026_quote_values_read=false`。2026仅出现作为2025末日右边界的日期元数据；未读取2026报价，没有根据2026结果修改任何方法。原始账户验证只有在开发筛选通过后才进入；本批未达该条件。完整盈利目标、RSI改进器增量价值仍未证明。

## 复现与文件

冻结请求为 `experiments/published-strategies/development-strict-request.json`，SHA256 `6c7048b9fd2610c0db7db36d133c18ae9211778428c072a518d1b890106c9cd7`。从项目根目录使用 `PYTHONPATH=src:.` 和已登记的Python3.11.15/Qlib0.9.8/numpy2.4.6/pandas2.2.3环境：

```sh
python -m scripts.run_published_strategies_strict preflight --provider "$TASK_PROVIDER" --request experiments/published-strategies/development-strict-request.json --expected-sha256 6c7048b9fd2610c0db7db36d133c18ae9211778428c072a518d1b890106c9cd7
python -m scripts.run_published_strategies_strict run --provider "$TASK_PROVIDER" --request experiments/published-strategies/development-strict-request.json --expected-sha256 6c7048b9fd2610c0db7db36d133c18ae9211778428c072a518d1b890106c9cd7 --out "$TASK_FRESH_OUTPUT"
```

`TASK_PROVIDER`是本地 `published-recipes-pre2026-clock-v2-20261028` 副本。运行目录必须全新，不能覆盖现存回放。其来源、哈希及本地结果位置在公共results.json与data-clock-manifest.json中。二进制行情、完整窗口与账户原始证据保存在本地；公共仓库保存来源、可执行代码、请求、全结果、审核和原始文件哈希，不假装行情包已经上传。

最终源代码推送哈希和对应CI状态在交付消息中单独核实。
