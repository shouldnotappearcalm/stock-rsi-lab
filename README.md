# stock-rsi-lab

A股模块化投资skill研究项目。首个闭环是**明确时间范围、按到达时间唤醒、
时点快照、结构化决策、次交易日撮合、留痕及一致性回放**。

当前是工程研究工具，不是已证明有效的投资策略；不连接券商。

2026-10-17 更新：固定低波动候选已完成整数原股、分红现金与独立账本复算。
100 万场景模拟净收益：2024 年 +19.95%、2025 年 +7.95%、2026 截至 10-16
+10.69%；10 万场景 2026 年为 +8.45%，未满足 10% 条件。全部四种资金场景与
成交/日期边界见[结果与审计](docs/research/low-risk-raw-share-results-2026-10-17.md)。
开盘流动性、冲击和完整 10 月尚未验收，目标继续保持未完成。
后续[执行核验](docs/research/execution-tape-validation-2026-10-17.md)已发现
1 亿元轨迹的超量单笔订单和旧分钟数据差异；100 万固定成交额外 40bp 成本后
降为 +9.93%。这些失败证据已保留，尚无资金场景通过完整执行验收。

进一步[完整账户费用反馈回放](docs/research/feedback-cost-validation-2026-10-17.md)
已重新计算后续订单、持仓与股利资格：100 万额外每边 20bp 时，2024/2025/2026
分别为 +19.39%/+7.53%/+10.30%；40bp 时 2026 为 +9.85%。1000 万/40bp 为
+10.06%，1 亿元各档均按单笔上限拒绝。全部场景和边界完整披露，未宣告正式达标。

进一步[跨接口数据核验](docs/research/cross-provider-data-validation-2026-10-17.md)
确认 68,003 个活跃日线 OHLCV 一致，并取得 1,299 个下单日的历史分时响应及
1,296 个价格匹配的 09:25 撮合记录。开盘量基准显示大资金成交假设仍未成立，
不会把五分钟量、09:25 撮合记录和 09:30 代理成交混为同一执行证据。

[盘中子单回放](docs/research/intraday-execution-results-2026-10-17.md)已完成 60 个固定场景，
开发段均盈利；2026 截至 10-16 有 11 个满足 10% 数值条件。5% 参与率、每边
额外 20bp 的 100 万场景为 +9.06%，未满足门槛。完整矩阵和未成交均保留，
没有根据 2026 选择执行参数；完整十月和真实冲击仍未验收。

新一轮[长期反转冻结诊断](docs/research/reversal-frozen-2026-results-2026-10-17.md)已完成：
60 场景在 2024、2025 年分别盈利，但 2026 截至 10-16 全部亏损，0/60 达到 10%。
100 万、5% 参与率、每边额外 20bp 为 +9.21%/+7.50%/−18.60%，候选失败。
开发前缀全部复现，独立审核重建 294,643 笔成交；不用这次 2026 结果修改投资规则。

独立的[日历月 MAX 候选](docs/research/lottery-max-pre2026-results-2026-10-17.md)也完成一次冻结开发检验：
40bp 费用压力下，2024/2025 为 +16.55%/−1.12%，候选被拒绝，未查询其 2026 收益。

独立项目，不修改已有a-share-skill。实现取舍来自多个已clone项目的
[源码审计](docs/research/README.md)，不按现有skill仓库目录直接堆模块。

| 组成 | 当前定义 | 是否可进化 |
| --- | --- | --- |
| 数据/时钟/唤醒 | 显式日历，发布/到达时间，固定快照 | 固定基础设施 |
| 因子 | 可见窗口趋势、短期回撤；持有期/账户状态作为条件 | 首版固定计算 |
| 投资skill | 回撤阈值、窗口、仓位上限、退出期限 | 有界JSON patch |
| agent | 规则解释器；Codex提出修改或作快照决策 | 可替换adapter |
| VerifyGate | 契约、因果性、账户、真实激活、等预算、开发集权限 | 固定评估者 |
| 证据 | 数据/源码/skill hash，快照、提案、订单、回放 | 追加留痕 |

## 运行

Python 3.11+，基础运行与测试只用标准库，不需要安装依赖。以下在项目根目录执行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v

PYTHONPATH=src python3 -m stock_rsi snapshot \
  --dataset data/fixtures/synthetic_cn_v1.json \
  --as-of 2024-09-27T16:04:59+08:00

PYTHONPATH=src python3 -m stock_rsi run \
  --dataset data/fixtures/synthetic_cn_v1.json \
  --start 2024-09-02T00:00:00+08:00 \
  --end 2024-10-18T23:00:00+08:00 \
  --skill skills/trend-pullback/skill.json \
  --output artifacts/synthetic-first

PYTHONPATH=src python3 -m stock_rsi replay \
  --run-dir artifacts/synthetic-first --output artifacts/synthetic-replay
```

输出目录必须不存在，防止覆盖原始结果。所有timestamp必须有时区。

```bash
PYTHONPATH=src python3 -m stock_rsi compare \
  --dataset data/fixtures/synthetic_cn_v1.json \
  --splits data/fixtures/synthetic_cn_splits.json \
  --budget 2 --output artifacts/comparison
```

默认运行fixed/grid/random/evidence/shuffled五组。evidence是离线启发式，
Codex提案需显式设置`--arms codex`。每组使用相同候选目录和尝试预算，
无效提案消耗次数；validation/sealed不能传入进化入口。

本机验证成功的CLI为桌面应用内置0.159.0-alpha.12.1；PATH上的0.139.0与
当前账号模型不兼容。使用已登录的兼容CLI，不需在项目存API密钥：

```bash
PYTHONPATH=src python3 -m stock_rsi compare \
  --dataset data/fixtures/synthetic_cn_v1.json \
  --splits data/fixtures/synthetic_cn_splits.json \
  --arms codex --budget 1 --agent-timeout 60 \
  --model gpt-6.1-sol \
  --codex-bin /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex \
  --output artifacts/codex-proposal
```

CLI单次prompt≤60KB，stdout≤1MB、stderr≤100KB、answer≤100KB；限制超时和
调用次数，工具事件拒绝。token验收上限是调用后的检查，不能保证服务端不超额计费。
read-only、临时cwd和拒绝工具事件只构成工程约束，不等于强OS数据隔离。

每次输出包括`report.json`、`cassette.json`、完整数据版本及逐次`snapshots/`。
回放会校验数据、运行源码、请求与响应摘要，然后重新执行账本。

## 时间定义

- calendar是明确交易日列表，不从工作日推断节假日。
- PRE_OPEN在09:00；每周首交易日17:00研究；持仓每天17:00检查。
- 公告按available_at到达触发，可在午休、盘后、假期唤醒；成交仍等合法开盘。
- 信号后最早下一交易日上午开盘成交；不是当日close成交。
- 同一事实的修订只有到达后生效，旧快照不变。

## 研究边界

`SYNTHETIC_REGRESSION`验证工程行为，不验证alpha。
`REAL_PRICE_ENGINEERING_ONLY`是真实价格样本，但可能缺少投资域、行动、价格边界
或历史可得时间证据。两者都不能产生正式收益通过结论。

当前主板撮合包含100股买入、T+1可售库存、涨跌停、停牌、整数股和现金约束。
20bps单边费用是研究假设。真实队列、公司行动、退出回收和完整时点证券池仍需
专门数据验收。详见[设计](docs/specs/2026-10-11-first-loop.md)与
[实施计划](docs/plans/2026-10-11-bootstrap.md)。

运行结果见[首版验收记录](docs/validation.md)，后续工作见[路线图](docs/roadmap.md)。

重点真实回测范围已登记为2025-01至2026-10、2026-01至2026-10。旧探索数据为
截至10-09的6只主板原价样本；已完成两个重点区间的冻结规则探索回测；公司行动、
历史交易状态和投资域限制随结果标注。
详见[实际数据盘点](docs/data-inventory-2026-10-11.md)和[实验声明](experiments/a-share-2025-2026.json)。

2026-10-14 已下载并校验覆盖全市场的 2026-10-13 Qlib 冻结快照：6,166 个历史
区间，过滤指数/B股后当日 5,560 只 A 股；2025-01-02 与 2026-01-05 分别覆盖
5,382 和 5,468 只。新增标准库只读审计器可恢复原始 OHLCV，但该包缺少完整证券
状态、停复牌、涨跌停和 PIT 财务版本，继续标为 `REAL_PRICE_ENGINEERING_ONLY`。
CNEquity 的 TDX/BaoStock 小样也已实跑：原价与 Qlib 一致，3 只边界股票的 428 个
session 状态回填完整。首个研究 universe 固定为沪深主板，三个起点约 3,175—3,189
只；全市场状态收据与精确价格边界完成前不计算正式策略收益。
详见[数据源审计](docs/research/a-share-data-source-audit-2026-10-14.md)。

不读取 2026 的首个外部证据基线已经完成：Qlib Alpha158 + DoubleEnsemble + CSI500，
训练/验证/开发全部截止 2025-12-30。开发期保留组合 `Top-100 / Drop-2` 的净复合
年化为 27.13%，平均仓位 99.58%，最大回撤 -20.12%；2024 单年仅 11.47%，所以
尚未满足逐年 20% 或封存测试要求。详见
[Qlib 开发记录](docs/research/qlib-pre2026-development-2026-10-15.md)。

第二次模块进化保持上述预测完全不变，只替换组合构建：用前一交易日 CSI500 权重、
240 session 风险快照和周频首次开市唤醒做 EnhancedIndexing。固定 6 候选预算后，
开发期保留版本两年复合 81.14%、年化 34.67%，2024/2025 分别为 21.43%/49.17%，
平均仓位 97.74%，最大回撤 -18.88%。这是 2024—2025 自适应开发结果；自有
CLARABEL 优化器逐次验算全部约束，一个过紧候选因不可行被记为失败。由于尚无新的
未来区间，该结果不能作为封存证据。
详见[组合模块进化记录](docs/research/qlib-enhanced-indexing-pre2026-2026-10-15.md)。

用户随后要求对该版本运行已污染的 2026 区间。经济参数冻结后，
2026-01-05—2026-10-13 诊断净收益为 -3.79%，CSI500 为 -5.10%，相对超额 +1.30%，
平均仓位 94.92%，最大回撤 -15.54%。20% 目标失败，且绝对收益比冻结
Top100/Drop2 低 1.80 个百分点。该结果只记录迁移失败，不得用于下一轮选法或调参。
详见[EnhancedIndexing 2026 诊断](docs/research/qlib-enhanced-indexing-frozen-2026-diagnostic-2026-10-15.md)。

按用户要求，预先固定的 DoubleEnsemble/Top-100/Drop-2 随后原样复跑
2026-01-05—2026-10-13：净收益 -2.00%，平均仓位 99.42%，最大回撤 -16.30%，
同期 CSI500 为 -5.10%。策略有 +3.10% 超额，但绝对收益目标失败。该区间此前已经
被观察，只能作为固定版本诊断，详见
[2026 复跑记录](docs/research/qlib-frozen-2026-replay-2026-10-15.md)。

2026-01-05—2026-10-13 的结果曾被用于提出后续方法，该区间因此永久失去测试资格。
同一区间不得用测试事实反推方法后再次声称验证通过。污染记录与新封存登记见
[方法论记录](docs/research/2026-test-contamination-2026-10-14.md)和
[`prospective-sealed-after-freeze.json`](experiments/prospective-sealed-after-freeze.json)。

后续只在 2024—2025 开发期寻找独立信号：20-session LGB 与滚动 Ridge 均未过
20% 年化门槛；TRA 首次因果推断为 19.03% 年化，2024/2025 分别 +18.13%/+19.69%；
预先固定的 DE＋TRA 等权组合为 16.12% 年化，2024/2025 为 +9.03%/+23.45%，
也失败。没有因此重试 2026。各次实验与哈希见
[研究索引](docs/research/README.md)。

独立的 MASTER 市场门控与跨股票注意力候选也已按预先冻结协议运行：
2024—2025 开发期净年化 12.30%，2024/2025 分别 +4.79%/+20.02%，
同日期 DE 对照为 26.13% 年化；该候选失败，没有因此读取或重试 2026。
详见[MASTER 开发回测](docs/research/qlib-master-pre2026-2026-10-16.md)。

财报公告后的隔夜反应也完成了一次经济机制检验：先审计 501 只历史 CSI500 主板股票的
公告日期、版本、次日价格与除权事件，再冻结 60/20 日事件收益诊断。正隔夜反应组
在两个窗口的按信号日等权、扣成本超额均为负，未通过开发闸门；没有反向选择负信号。
详见[公告事件研究](docs/research/pead-orj-full-universe-2026-10-17.md)。

[2025—2026与2026单独回测结果](docs/priority-backtest-results-2026-10-11.md)：
两个独立10万元账户，6只股票诊断样本；目前为冻结seed基线，未做RSI效果声明。

复现（输出目录须不存在）：
```bash
PYTHONPATH=src python3 -m stock_rsi.priority \
  --capture-dir data/local/coverage-20261011 \
  --plan experiments/a-share-2025-2026.json \
  --engineering --output artifacts/priority-new
```

初始投资内核的局限、现金闲置与市场参考见[诊断报告](docs/seed-diagnosis-2026-10-11.md)。

[RSI-Anything源码分析（2026-10-12）](docs/research/rsi-anything-2026-10-12/analysis.md)：
固定commit，含真实验证结果、各领域发布边界及股市项目迁移建议。

## v0.2组合候选基础

`stock_rsi.portfolio_runner`提供程序化的多候选组合运行与回放接口：policy必须同时
输出完整目标组合和`keep-current`，selector只能从已记录候选中选择；选中目标转换为
确定性订单，同一开盘先卖后买。候选、选择、bundle内容、订单和账户均纳入回放校验。

`policies/v0.2-contract-fixture`只验证七类投资skill的模块边界与内容寻址，明确标记为
`CONTRACT_ONLY_NOT_AN_INVESTMENT_STRATEGY`。它不是可回测投资策略。当前公开CLI仍以
前述合成单决策流程作为演示；真正的价格/风险/流动性因子、投资policy和Outcome Model
将按[v0.2设计](docs/superpowers/specs/2026-10-14-policy-outcome-rsi-design.md)分阶段接入。

## 许可证

Copyright 2026 stock-rsi-lab contributors。

项目自有代码采用[Apache License 2.0](LICENSE)。外部数据、模型和引用源码继续适用
各自许可或使用条款；仓库中的来源说明不将这些第三方内容重新授权。
