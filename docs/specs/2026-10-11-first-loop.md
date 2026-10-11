# A股时点回放与技能进化首个闭环

用户授权创建独立项目、写计划并直接实施。先做A股。时间范围、唤醒时机、
特定时点的数据快照和测试回归数据是首版核心要求。

## 投资研究问题与证据边界

工作假设：在已存在的中期上升趋势中，短期回撤后的候选不一定都值得买入；
基于失败证据修改回撤识别skill，是否比固定规则、等预算普通搜索或打乱证据
更有效。该假设是可替换的实验起点，不是已证明的alpha。

固定价量因子，先只修改一个有界JSON skill：trend_window、pullback_window、
min_pullback、max_pullback、target_weight、max_holding_sessions。交易运行
使用确定性解释器；Codex作为提出skill修改的研究agent。另提供时点决策
adapter作端到端工程验证。预算、编辑空间与全部结果保存在campaign账本。

初始趋势定义为trend_window可见收盘价窗口首尾收益为正；回撤为最近
pullback_window的最高可见收盘价到当前收盘价的跌幅。两者只用快照中的
历史bar，按交易日期而非到达顺序排序；不以短期低于均线自动否定中期趋势。

首版不将18个候选因子全部实现，不进行跨skill百分位合并，不声称严格RSI
或投资有效性已成立。严格递归的改进器迁移实验属于后续里程碑。

## 时间与数据

UTC存储、Asia/Shanghai展示。所有timestamp必须有offset。交易日来自显式
session表，每天包含09:30–11:30、13:00–15:00两个session。

记录字段：record_id、security_id、kind、event_at、public_at、available_at、
payload。available_at是实际到达或明确标记为重建的时间；约束
event_at<=public_at<=available_at。财报period_end在payload里，不用于可见性。
决策快照在as_of仅包含available_at<=as_of的记录，且不含将来的市场事件。
修订版只覆盖快照中已经可见的同一事实，保留所有版本与源内容摘要。

模拟clock只前进。唤醒条件：PRE_OPEN、每周首交易日POST_CLOSE、持仓每日
检查、公告实际到达后。如果公告在午休/盘后/假期到达，唤醒可立即取证，
下单仍等合法交易session。相同原因/记录只唤醒一次；可在指定as_of查询快照。

范围[start,end]包含事件时间端点；运行必须拒绝不一致/naive时间。调度不依赖
真实sleep，不创建操作系统定时任务。

## 决策与交易

Decision只允许BUY/SELL/HOLD/ABSTAIN、证券、整数股数量、evidence_ids和
reason；数值必须有限，BUY/SELL数量正，HOLD/ABSTAIN数量0。证据须属于当次
snapshot。模拟订单只在决策之后的下一个合格开盘撮合。A股100股买入单位、
T+1可售库存、涨停不买/跌停不卖、停牌不成交、现金不可透支。使用Decimal。
日频不模拟队列和真实开盘冲击；不把当日close信号按当日close成交。
同证券最新的可执行意图替换旧未成交意图，避免假期/公告多次唤醒累加同一
买入目标；HOLD本身不取消挂起意图，撤销需要后续独立CANCEL协议。

首版账本明确支持普通主板股；fixture提供实际价格边界，而非推广统一涨跌幅。
公司行动/复杂退出未验收的数据不可用于投资有效性声明。

## 运行记录

每次run保存数据hash、配置/skill/runtime版本、UTC范围、数据证据等级、
wake原因、as_of、snapshot_hash、完整输入输出、决策、订单、成交、账户
快照和错误。原样回放要验证请求/响应/skill/数据摘要并复算账本；新skill必须
重新运行历史环境，不能复用旧响应证明新策略。

Codex adapter用非交互CLI、JSON schema、ephemeral、read-only和隔离cwd；
不主动暴露完整数据集。实际工具调用使该次严格snapshot运行无效。此模式
仍不构成强OS隔离，证据等级固定ENGINEERING_ONLY。

## 回归数据

synthetic_cn_v1显式包含：时区边界、午休、国庆假期、盘后公告、晚到行情、
财报修订、T+1、涨跌停、停牌、次日跳空和重复事件。每项有手工预期值。
future perturbation测试：修改as_of之后的数据不得改变当时快照/确定性决策。

real_price_smoke：若公开无凭证来源可得，保存原响应、下载时间和hash；作为
真实价格工程样本，标记缺少完整PIT投资域/财报/行动/成交条件，不能给正式
研究结论。Tushare完整dataset是后续适配器，不静默混源。

## 验证层次

G0契约/时间/数据身份；G1快照无未来；G2决策/账户/成交；G3修改实际激活；
G4等预算开发对照；G5封存集不允许在进化运行中读取；G6未来paper后续启用。
bootstrap块长只影响不确定性，不影响原均值；首版不使用未经功效校准的
1%收益/20%回撤作为正式收益晋级条件。
