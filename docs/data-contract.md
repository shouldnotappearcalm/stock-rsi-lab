# A股数据契约与验收

每条记录有稳定record_id、fact_key、security_id、kind，以及带时区的event_at、
public_at、available_at。财报period_end属于内容，不能替代披露时间。
同fact_key的修订按实际到达顺序覆盖当前视图；源数据保留各版本。
每日完整bar的event_at必须对应trade_date收盘之后，且trade_date在显式日历内。
午休/假期公告可到达；交易日不会因此生成。

决策读available_at<=as_of的快照。撮合器作为评估环境可读取随后实际开盘价，
该价格不能传给之前的决策。缺失待成交日行情、持仓日行情或最终有效估值使run无效；
不能把缺失当成停牌。停牌、limit_up和limit_down须明确提供。

| 证据等级 | 当前用途 | 不能证明什么 |
| --- | --- | --- |
| SYNTHETIC_REGRESSION | 合成时间、账本、快照与回放回归 | 投资alpha |
| REAL_PRICE_ENGINEERING_ONLY | 真实价格格式与流程探针 | PIT完整性、可成交收益 |
| PIT_RESEARCH_VERIFIED | 预留，尚无已验收数据 | 仅填标签不能升级证据 |

当前真实样本来自腾讯raw `day`字段，600519，2024-01-02至03-29，共58行。
原响应及摘要与获取时间保存在data/local下。导入器拒绝只有qfqday的响应，
避免把事后复权序列作为原价成交。日历暂为返回的价格日期，17:00到达时间、
普通主板10%边界及不停牌是**重建假设**；volume单位未验证，未参与策略。
该样本的规则回测零成交，不能由此计算有意义的投资效果。

完整数据验收应逐个覆盖：历史证券身份/退市、投资域成员变化、交易所日历、
历史原价/行动、逐日涨跌停和停复牌、财报版本/实际到达日志。先验证ST状态切换、
除权、停牌、财报修订、退市等复杂案例，再开放相应因子；缺失不静默插值。

split registry按development→validation→sealed排序，区间不可重叠。campaign导出
只包含开发截止时已到达的记录，候选agent只接收开发反馈。普通run/snapshot工具
可由研究者检查任意时点；这是API访问边界，不是对有本机文件权限者的封存隔离。
后续正式实验须使用独立评估进程/存储权限、封存清单和披露后的实验预算。

2026-10-11后续盘点：已新增6只主板2024-01-02至2026-10-09原价工程样本，
重点2025—2026与2026单独区间已登记；仍非完整PIT。覆盖、双源抽查和断点见
[data-inventory-2026-10-11.md](data-inventory-2026-10-11.md)。

VerifyGate采用两层协议：结构/时间/账本硬错误拒绝执行；未验收的数据假设明确
记录到report.verify_gate.warnings，允许工程探索。正式研究晋级另行验证，
不会用数据不足阻止所有试跑，也不会把工程完成自动转为投资有效。

## v0.2组合候选契约

因子证据绑定一个`snapshot_hash`，记录factor/security、有限Decimal值或明确缺失原因、
单位、lookback、as-of、源记录ID和质量标志。同一FactorFrame不允许重复键或混入其他
快照证据。

PortfolioProposal绑定同一个snapshot、account和PolicyBundle，包含全组合目标和且仅一个
`CASH`目标；六位小数权重合计必须严格为1。每次policy至少给出两个候选并且恰有一个
`keep-current`。候选先完整持久化，selector随后返回候选ID；未选候选不标记为真实观察。

运行时保存PolicyBundle的规范化内容副本与摘要，而非依赖运行结束后仍可变的源目录。
同一开盘的行情先整批验证，订单按SELL后BUY、同动作证券代码排序执行。缺少实际需要的
成交行情会令订单和运行失效，不能解释成停牌或零成交。

`portfolio_runner`目前是程序化基础接口，没有公开为投资CLI。其contract fixture没有经济
假设，不产生收益结论；Outcome Model和成熟反馈账本属于后续实施片。
