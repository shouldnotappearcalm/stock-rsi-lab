# 低残差波动原股来源：采集与独立核对结果

固定请求和方法在 `9420a11` 推送后才开始采集。本次只补齐原先冻结的361个名字，
窗口为2023-12-29至2025-12-31；信号、24次月度目标、预算分配器和门槛均未修改。

实际采集进程退出码0。301份旧包逐字节复用，另60个名字各完成四次金融逻辑查询，
合计240次，全部保留SDK响应和reservation链；一次登录、成功退出，没有重试或重抓。
最终175085条日线、860条供应商分派、875条调整记录，quarantine为0。

独立审计认证全部361包和240响应投影，重新核对694份旧输入、额外一份冻结请求、
42份既有金融产物；未发现字节变更。主进程另行执行同一冻结审计，报告逐字节一致，
SHA256为 `fa8baf8c5091cd1b96e617b2b41da4a50eb6082517f58dacd32d52ee1e5d36c7`。
八种非法源输入均被拒绝，另一个未准入quarantine边界检查通过。独立首跑因不在仓库目录解析相对请求路径而失败，保留原日志；
只纠正工作目录重跑，未改脚本、请求或源包。

1840个正权重目标的as_of快照均在原始记录中逐一找到，`isST=0、tradestatus=1`。
这关闭了此前362个未知目标快照；它不证明整个持仓、待成交订单及权益依赖期间正常。

两只股票仍缺日，原样保存，未补价格或从API缺行推断生命周期：

| 股票 | 原始行数 | 缺失session | 已观察范围 |
| --- | ---: | ---: | --- |
| SH603341 | 448 | 38 | 2024-03-01至2025-12-31 |
| SZ002505 | 163 | 323 | 2023-12-29至2024-08-30 |

既有有界公告库存保存了两只股票的生命周期原件，但当前候选在缺日时实际空仓尚未证明。
库存还认证了17份范围内PDF及9类事件proof线索。库存只检查旧缓存和五个公告目录，
没有覆盖本次fresh60的新增事件；不能把旧候选的税务、实际零持仓或准入结论搬过来。

终态源有13条非现金分派和16条不存在同除权日供应商分派的调整记录。它们是待核问题，
不能从调整因子或价格差制造现金、送股或免税。下一步先对全部终态记录完成公告对应，
再冻结事件投影和原股账户回放；本次没有计算账户收益或读取新的2026行情。

CI的HTML解析测试原先缺少 `beautifulsoup4`，已在 `2bde776` 声明测试依赖，
两个CI job均安装。干净环境验证通过；冻结提交的Python3.11、3.12及research三个任务
[全部成功](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39592407729)。
修复后连续四个远端运行均成功，未关闭测试或邮件通知。

公开证据：

- [源包清单](../../experiments/qlib/low-market-residual-vol1m-raw-source-capture-manifest.json)
- [独立审计](../../experiments/qlib/low-market-residual-vol1m-raw-source-independent-audit.json)
- [验证记录](../../experiments/qlib/low-market-residual-vol1m-raw-source-verification.json)
- [旧公告缓存库存](../../experiments/qlib/low-market-residual-vol1m-pre2026-corporate-cache-inventory.json)
- [首跑执行说明](../../experiments/qlib/low-market-residual-vol1m-raw-source-audit-execution-note.json)

完整响应和行情包留在本地并由公开哈希绑定。来源采集通过不等于公司行动、税务、
历史到达时间、原股账户或分钟成交已验收。“2024、2025盈利且2026年1—10月>=10%”
仍未达成，完整十月也尚未结束。
