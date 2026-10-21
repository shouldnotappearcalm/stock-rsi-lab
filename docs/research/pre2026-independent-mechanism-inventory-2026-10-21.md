# pre2026 独立机制盘点（只读，未运行研究）

结论：本次可读历史登记不足以确认一个可直接冻结的新 alpha 机制。现有量价数据可以计算一些尚未见独立登记的统计量，但“可计算”不等于存在可靠收益机制，更不能据此承诺目标收益。本次没有新建候选计划、选参数或计算任何账户收益。

范围：仅检查文件名含 pre2026/development 且属于 plan/results/summary/design 的文件；先用内容筛查排除含疑似2026收益/结果表述的文件，不展示被排除正文。最终纳入41份JSON，排除48份文件，名单保存在 `/tmp/pre2026-mechanism-allowlist-20261021.json`。未读取任何年度延长结果、full/horizon结果、目标持仓文件或原始行情。因不少计划被保守排除，以下“未见登记”只对本次可读子集成立，不是全仓库未实现声明。

## 已覆盖，不能重新包装成新机制

| 机制族 | 已见独立登记/结果 |
|---|---|
| 趋势、信息反应与价格锚定 | intermediate_mom12_7、total_mom12_2 控制、market_residual_mom36_12_2、near_52w_high；ETF relative12m / prior2-12 |
| 低风险与偏好 | low_vol36、low_vol60 控制、low_beta60；low_max_calendar 彩票偏好适配 |
| 流动性与交易摩擦 | amihud22；不能仅改成交额窗口或分位数便算独立机制 |
| 估值、规模及组合 | szse_monthly_low_pe、szse_monthly_small_issued_cap、固定 value+momentum；ETF equal-entry 是基准机制，非新alpha证据 |
| 量价预测与配置实现 | LightGBM/DoubleEnsemble、TRA、MASTER、rolling ridge/LGB、多期限/等权融合、enhanced indexing、weak_ovnt avoidance |

残差策略的 budgeted allocator、原股与分钟账户、成本档位、税压力和源修复属于实现/评估变化，不是新增信号机制。模型更换或训练窗口更换也不自动构成新的经济机制。此处未依收益高低排序，控制策略仍只是控制。

## 两条有限的数据可行性线索，不构成候选注册建议

1. **市场信息反映的滞后程度（price delay）**。研究问题是价格对共同市场冲击的即时与滞后反应差异，而不是beta大小或既往累计趋势。既有 low-beta/residual 计划已证明存在股票调整收盘价、CSI500价格指数和历史证券资格；因此计算滞后响应统计量所需的基础字段有登记依据。本次未见一个专门的price-delay经济机制条目。但尚未核实独立原始文献、日/周同步样本质量、停牌造成的机械延迟，以及它是否只是在重述已测动量/流动性。不能据此选择交易方向、回看长度或立即回测。

2. **跨年度同一日历月的重复需求效应**。与滚动相邻月份的动量不同，待检验问题是同一日历位置的重复资金需求。已有61个连续月末价格的资格约束说明“若干年历史”存在；可做字段和样本长度盘点。本次未见独立季节性机制登记。但五年通常每个日历月仅约五次观察，低beta的覆盖下限还只有历史资格集的一半，远不足以证明稳定的季节性alpha；是否拥有更长且可追踪退市/调出的历史样本，本次没有验证。优先级只能是资料核验，不是候选运行。

## 现有证据不能支持的跳跃

- 质量、盈利能力、应计、投资/资产增长：已读计划只证明交易所月度PE及发行股数等字段，不能冒充完整PIT财务报表与公告到达记录。
- 净发行/回购供给：月度发行股数字段并非完整股份变动事件流，拆并股、送转及口径变化不能自动解释成经济发行。
- 行业联动、供应链或配对套利：本次未验证历史行业/关系身份或可借券条件；证券代码本身不够。
- 订单流与做市：日OHLCV不支持盘口、排队和市场冲击识别。
- 低偏度、尾部风险、换手率等若只是低波动/彩票/流动性的另一种代理，须先说明可区分机制；不能为增加候选数而另命名。

证据依据（均为本次允许读取的pre2026文件）：`experiments/qlib/low-beta60-pre2026-plan.json`、`market-residual-momentum-pre2026-plan.json`、`intermediate-momentum-pre2026-plan.json`、`high52-pre2026-plan.json`、`illiquidity-pre2026-plan.json`、`lottery-max-pre2026-plan.json`、`szse-value-pre2026-plan.json`、`szse-issued-size-pre2026-results.json`、`szse-value-momentum-pre2026-results.json`，及同范围模型/ETF development结果登记。

最终边界：这是一份有限范围研究覆盖与数据条件盘点；没有新的机制被验证，没有收益预测，没有根据任何后续年度输赢修改规则。
