# stock-rsi-lab

A股模块化投资skill研究项目。首个闭环是**明确时间范围、按到达时间唤醒、
时点快照、结构化决策、次交易日撮合、留痕及一致性回放**。

当前是工程研究工具，不是已证明有效的投资策略；不连接券商。

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
