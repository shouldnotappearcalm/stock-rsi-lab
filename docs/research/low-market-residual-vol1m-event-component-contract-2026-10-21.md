# 原件经济组成补全合约：独立版本，尚未作用于真实源

本合约解决原股账户前的两处数据接口问题，不改变信号、股票、仓位目标或费用。
既有编译器、precision合约和账户文件保持原字节。

新增 `src/stock_rsi/primary_event_components.py`：

- `project_primary_event_components(packets, proofs)` 只返回深复制的派生视图和来源receipt。
- `compile_primary_event_components(packets, proofs, calendar)` 调用既有V2编译器，再为
  新派生事件指定独立ID和准确source kind；未涉及的旧事件及receipt逐项保持相同。

调用者必须先认证真实源包、原始PDF、内容审查和冻结请求。这两个函数不负责证明
PDF内容本身，也不授予账户、到达时间、税务或登记结算完整性准入。

## 仅支持两种补全

`proofs.primary_event_component_contract` 必须为 `PRIMARY_EVENT_COMPONENT_COMPLETION_V1`，
`primary_event_components` 以issuer/ex-date为键。每条proof严格检查version整数1、
verified、issuer、publication/record/ex/pay/list日期、原件file/SHA及正整数页码。
额外税务字段、同事件的其他更正/税务合约或补充事件均拒绝。本适配器只接V2，
不支持的V3 component precision字段必须为缺省或空字典；非空或类型错误均全局拒绝，
包括没有primary组成补全的路径，不能静默忽略其他事件的更正证明。

`PRIMARY_TWO_CASH_COMPONENT_SUM` 需要恰好两个不同原始行SHA及对应正现金金额。
两个源行与原件的日期必须一致，送股/转增均为0，不得存在股份上市日。声明的
合计金额必须以精确有理数等于两组成之和。漏行、重复、孤立proof、错误PDF/证券/
日期、价格参考数替代实际现金，以及任何非现金组成均拒绝。

派生行保留原件确定的合计现金，清除第一组成的税后显示字段，使用明确派生标记；
不将第一组成的税后数伪装成合计。按原件合计比例生成一个事件，沿用账户既有
聚合现金/税准备金取分规则。4股合并现金取分可能与两个组成分别取分相差1分，
测试明确展示这种差别；本合约不声称逐组成结算等价或实际登记结算取分已证实。

`PRIMARY_STOCK_ZERO_CAPITAL` 只允许把原始股票股利行的空capital字段在派生视图中
补为原件确认的0。原现金及送股比例必须逐项核等，有明确股份上市日。不得改
非空capital、改金额、把送股改成转增、增加股票计税基础或资本免税。
股票税基未知继续保留；合成正持仓在除权时仍被既有账户拒绝。

## 来源链与验证

派生receipt保留全部原始行SHA、派生行SHA、PDF SHA、proof及projection receipt SHA，
以及经济补全类型。新事件ID绑定规范事件和该receipt，不能被记录成未经修改的
vendor事件。未涉及的V2现金精度补全及其ID/receipt继续完全相同。

八项新增合成测试覆盖上述行为，并和既有编译器测试一起验证兼容性。测试使用
人工fixture，不读取本次真实PDF、行情、目标或收益。真实事件投影尚未执行：需要
另一个冻结入口认证原件审查、旧九类proof、三笔原件补充现金、一个现金精度补全、
两个生命周期边界及上市锚；再把该合约输出交给独立事件审计。

所有六项未知税务及零碎股/ST实际持仓守卫继续保留。之后账户可能通过，也可能
在明确的依赖时失败；不能先假定通过。本合约不产生2024、2025或2026收益数字。

独立审查发现过不相关V3更正字段被V2静默忽略的Important问题。原始复现已保留，
新增负例先失败再通过；修复后25项编译器合成测试及20个独立负例通过，主进程
730项全套回归通过。干净研究环境同730项通过，其中3项可选Qlib依赖跳过。
真实原件转录的两条补全proof和两笔新现金supplement也经独立只读核对；它们保存于
`experiments/qlib/low-market-residual-vol1m-primary-completion-proposal.json`，尚未应用。
