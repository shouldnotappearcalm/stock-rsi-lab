# stock-rsi-lab

A股模块化投资skill研究项目。首个闭环是**明确时间范围、按到达时间唤醒、
时点快照、结构化决策、次交易日撮合、留痕及一致性回放**。

当前是工程研究工具，不是已证明有效的投资策略；不连接券商。

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

重点真实回测范围已登记为2025-01至2026-10、2026-01至2026-10，当前数据截止10-09。
新取得6只主板原价样本；公司行动、历史交易状态和投资域仍待验收，尚未生成正式收益。
详见[实际数据盘点](docs/data-inventory-2026-10-11.md)和[实验声明](experiments/a-share-2025-2026.json)。
