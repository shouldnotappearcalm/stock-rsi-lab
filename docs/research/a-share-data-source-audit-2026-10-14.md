# A股回放数据源审计（2026-10-14）

## 结论

2025—2026-10 与 2026-01—2026-10 的行情底座已经找到并完成本地字节校验：
[chenditc/investment_data](https://github.com/chenditc/investment_data) 发布的
2026-10-13 Qlib 快照。它可以替换原先 6 只股票的行情诊断样本，但目前只能标为
`REAL_PRICE_ENGINEERING_ONLY`，不能直接进入收益验收。

证券状态层也找到可运行的开源基础：[CNEquity](https://github.com/rootSunc/CNEquity)
以 TDX 建证券/行情湖，以 BaoStock 重建沪深逐日 `tradestatus/isST`，并保留覆盖收据、
来源和数据版本。固定 commit 的真实 demo 与两个状态探针已经跑通。首个研究 universe
因此收窄为**沪深主板**；北交所、科创板和创业板等状态与交易规则验收后再加入。

Tushare Pro 仍是精确 `stk_limit`、北交所历史 ST 与 PIT 财务的首选补充源。当前环境
没有 token，而且其数据服务协议限定个人、不可转让、非商业用途，所以项目只实现
环境变量适配，不提交 token 或抓取结果。

## 已下载并验证的快照

- 发布：<https://github.com/chenditc/investment_data/releases/tag/2026-10-13>
- 压缩包：567,791,316 bytes
- SHA-256：`3b8a2153beada4d2004035f52447ba3c56af68499f058553548b9b69fbe8d444`
- 数据截止：2026-10-13；显式交易日历从 2000-01-04 开始，共 6,486 个交易日。
- 来源身份：Dolt、构建仓库、Qlib 和镜像 digest 均在 511-byte manifest 中固定。
- 本地使用发布仓库自带 `validate_archive.py --require-publishable` 验证通过。

Qlib `all.txt` 有 6,166 个历史区间。过滤沪深指数与 B 股后：

| 日期 | A股数量 | 上交所 | 深交所 | 北交所 |
| --- | ---: | ---: | ---: | ---: |
| 2025-01-02 | 5,382 | 2,274 | 2,847 | 261 |
| 2026-01-05 | 5,468 | 2,299 | 2,882 | 287 |
| 2026-10-13 | 5,560 | 2,315 | 2,896 | 349 |

2026-10-13 的全部活跃区间是 5,566 个，多出的 6 个是指数
`SH000300/852/905/906/985` 与 `SZ399300`。因此不能把 Qlib 的 `market=all`
原样当 A 股股票池。

二进制恢复原价的 spot check：贵州茅台 2026-10-13 收盘 1274.89，平安银行
11.57；退市样本 `SH600555` 的观察区间结束于 2022-07-06。项目新增的
`stock-rsi-qlib-audit` 使用 `price / factor` 与 `volume * factor` 恢复来源值，
不依赖 Qlib 包。

首个沪深主板 universe 使用 `SH600/601/603/605` 与 `SZ000/001/002/003`。三个起点的
观察数量分别为 3,175、3,189 和 3,187。这个范围与当前撮合器的主板规则一致，避免
在同一次验收中混入创业板/科创板 20% 和北交所 30% 的制度差异。

## CNEquity 实跑结果

固定 `c118038ea82b5bb78783c0c17a1d9251b36de71d`，安装锁文件依赖后执行了两组真实探针：

1. 5 只股票 × 最近 30 个交易日，TDX 写入 150 行。贵州茅台 2026-10-13 的
   OHLCV 与已校验 Qlib 快照完全一致。
2. 对 `600053.SH/600289.SH/600519.SH` 回填 2025-01-02—2026-10-13 状态，
   BaoStock 写入 1,284 行，3 只各 428 个 session，覆盖收据为 `complete`。

边界行为不是空跑：`600053.SH` 在 2026-04-29 停牌，随后从 2026-04-30 起进入风险
警示；`600289.SH` 有 12 个“风险警示且停牌”的 session；`600519.SH` 全区间正常交易。
这证明 `status` 与 `risk_warning` 两列正交，足以支持沪深历史股票池和 5% ST 价格带。
探针身份与 content digest 保存在
[`cnequity-demo-2026-10-14.json`](../data-sources/cnequity-demo-2026-10-14.json)。

## 为什么仍不能直接回测

1. `all.txt` 的起止日期是第一/最后一条观察行情，不是交易所确认的上市、暂停上市和
   退市状态。Dolt 的 `ts_a_stock_list` 仅有 5,023 条记录，退市日期最大值停在
   2022-07-13，明显落后于 2026 行情。
2. 发布包只含 OHLCV、amount、factor 等特征，没有把 `final_a_stock_limit` 打进包。
   Dolt 里的该表也只到 2023-06-12，2025-01-02 是 0 行；对某日缺失值也无法区分
   停牌与抓取缺口。
3. `final_a_stock_eod_price` 混合了 Tushare、BaoStock、AKShare、Yahoo 以及 2019 年以前
   的 Wind/财汇静态数据。交叉校验是优点，但不同来源的量/额单位仍需单独验收。
4. 没有财报公告版本、实际披露时间和修订链。基本面因子不能从报告期直接回填。
5. 仓库的 Apache-2.0 只覆盖构建代码。Tushare 当前数据服务协议把授权限定为个人、
   不可转让、非商业用途，因此公开仓库不能提交抓取后的数据文件或 token。

## 数据分层决定

| 层 | 首选来源 | 用途 | 当前状态 |
| --- | --- | --- | --- |
| 冻结行情 | `investment_data` 每日 release + manifest | 2025—2026 OHLCV、复权重建、指数成分 | 已验证，可做工程回放 |
| 证券主数据 | CNEquity TDX/交易所/BaoStock | 上市/退市/板块身份 | 代码和 demo 已验收；全市场湖待建 |
| 可交易状态 | CNEquity BaoStock 历史回填 | 沪深逐日停复牌与 ST | 3 只边界探针通过；全市场收据待建 |
| 精确价格边界 | Tushare `stk_limit` 或版本化规则引擎 | 当日实际上下限/无涨跌幅日 | 阻断项；不能使用过期 Dolt 表 |
| 公司行动 | CNEquity TDX/CNInfo/东财，Tushare 交叉验收 | 股数、现金、价格基准调整 | 数据契约已核对，真实案例待验收 |
| PIT财务 | CNEquity 严格 PIT + Tushare `ann_date/f_ann_date` 抽样 | 只在实际公告后进入快照 | 尚未抽样 |
| 公告原文 | CNEquity 巨潮资讯/CNInfo | 披露证据、修订与退市事件 | 代码已核对，尚未建湖 |
| 交叉核验 | Qlib、CNEquity TDX、AKShare 腾讯/东财 | 收盘价、停牌和 ST 异常复核 | Qlib/TDX spot check 已通过 |

Tushare 官方文档明确给出了退市日期、单日全市场复权因子、2000 年起的每日停复牌、
每日上下限价格，以及财务报表的 `ann_date/f_ann_date`。这些字段正好补齐行情包的
缺口，但基础接口多要求 2,000 积分，且受数据服务协议限制。

系统 Python 的 BaoStock 0.8.9 首次 TCP 登录等待超过 60 秒；CNEquity 锁定的
BaoStock 0.9.3 随后成功登录并完成状态回填。因此关键路径固定包版本、超时、重试和
覆盖收据，不能依赖系统里偶然安装的客户端。
AKShare 明确说明前复权历史会随当前日期变化，且接口本质是多个网站的适配器，适合
第二来源核验，不适合承担不可变快照职责。

另外审计了 [SimTradeData](https://github.com/kay-ou/SimTradeData) commit
`b925da2f2cda2842f92c1b68235fcb4e52e643eb`。它的 TDX/Mootdx/BaoStock 分工和
XDXR 表很有参考价值，但导出层按 `preclose` 直接计算上下限，且代码是 AGPL-3.0；
本项目不复制实现，也不把该计算结果当真实 `stk_limit`。

已从 manifest 对应的 Dolt commit 单独下载 `final_a_stock_limit`：509,537,052 bytes，
14,057,413 行，范围 1996-12-16—2023-06-12，SHA-256 为
`2869dfa878b36d0d925b4cd3de929e129753f1937d6cfbda277f6d7410b2b3ff`。它只用于对
版本化价格边界规则做历史回归；因为目标窗口没有行，不能被外推成 2025–2026 真值。

## 回测数据 Gate

两个重点区间固定为：

- 主区间：2025-01-02 至 2026-10-13；
- 单独区间：2026-01-05 至 2026-10-13。

开始计算收益前，每个交易日与拟下单股票都必须满足：

1. 股票在该日的证券主数据有效区间内；
2. 行情来自固定 release，且 manifest、压缩包哈希与解压内容验证通过；
3. 有明确停牌状态和当日真实上下限，未知时拒绝成交；
4. 公司行动能够同时解释价格、持仓股数和现金变化；
5. 基本面记录以 `f_ann_date/ann_date` 控制可见性，修订保留旧版本；
6. 关键字段至少有第二来源抽样，差异写入数据缺陷账本。

行情包已经满足第 2 条；CNEquity 小样已证明第 1/3 条所需的状态链能运行。全市场
状态收据、精确价格边界和公司行动案例仍未完成，所以此时仍不能发布策略收益结论。

## 复现审计

下载 release 的 `qlib_bin.tar.gz` 和 `qlib_bin.manifest.json`，先执行发布仓库的
validator，再解压。不要把第三方数据提交到本公开仓库。

```bash
PYTHONPATH=src python3 -m stock_rsi.qlib_snapshot \
  --root /path/to/qlib_bin \
  --date 2026-10-13 \
  --symbols SH600519,SZ000001,SH600555
```

固定来源身份和本次结果保存在
[`docs/data-sources/qlib-investment-data-2026-10-13.json`](../data-sources/qlib-investment-data-2026-10-13.json)。

## 主要来源

- [Qlib 官方仓库的数据说明](https://github.com/microsoft/qlib#data-preparation)
- [investment_data 构建与多源校验](https://github.com/chenditc/investment_data)
- [CNEquity 数据湖与研究口径](https://github.com/rootSunc/CNEquity)
- [CNEquity 数据源边界](https://github.com/rootSunc/CNEquity/blob/c118038ea82b5bb78783c0c17a1d9251b36de71d/docs/zh/datasets/sources.md)
- [SimTradeData TDX/BaoStock 工程](https://github.com/kay-ou/SimTradeData)
- [BaoStock Python API](https://github.com/zxygithub/baostock/blob/master/docs/pythonAPI.md)
- [Tushare 股票基础信息](https://tushare.pro/document/2?doc_id=25)
- [Tushare 复权因子](https://tushare.pro/document/2?doc_id=28)
- [Tushare 每日停复牌](https://tushare.pro/document/2?doc_id=214)
- [Tushare 每日涨跌停价格](https://tushare.pro/document/2?doc_id=183)
- [Tushare 财务公告日期字段](https://tushare.pro/document/2?doc_id=33)
- [Tushare 数据服务协议](https://tushare.pro/document/1?doc_id=405)
- [AKShare A股数据与复权说明](https://github.com/akfamily/akshare/blob/main/docs/data/stock/stock.md)
- [JQData SDK 的历史股票池、价格边界和停牌字段](https://github.com/JoinQuant/jqdatasdk/blob/master/jqdatasdk/api.py)
