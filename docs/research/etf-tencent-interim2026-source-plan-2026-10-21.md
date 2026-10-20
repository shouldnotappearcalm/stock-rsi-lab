# 腾讯原价替代来源：三只ETF、固定重叠验证

东财原价原3次及quote请求头额外3次均未收到成功HTTP价格响应；不宣称请求头已修复，不再增加这个端点的尝试。两个终态manifest和所有reservation/SOURCE_ERROR原样保存。策略仍为已冻结prior2–12，无新窗口/资产/仓位/费用或2026反馈改进。

依据AKShare项目[当前原始实现](https://raw.githubusercontent.com/akfamily/akshare/master/akshare/stock_feature/stock_hist_tx.py)的腾讯接口路径与参数，使用`proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get`，`param=symbol,day,start,end,640,`尾部空调整模式表示不复权；固定JSONP变量，不运行返回脚本或用eval。不会调用其额外上市年探测或逐年自动循环。

新增预算3身份、每只一次、间隔0.3秒、10MiB、禁重定向。三个已选ETF，范围2025-01-01至2026-10-20，640条上限覆盖预期433个session。起点增加2025仅用于原价跨源重叠校验，不改变投资形成或收益区间：2025的243个显式session及原始OHLC应与此前已固定东财数据逐日匹配，原开发账本前缀必须保持。没有新2024/2025方法试验，不从不同源挑表现更好的价格。

实际原始JSONP先留存，随后另行解析并验证`day`原价节点；不降级使用qfqday/hfqday，不猜成交量单位或宣称盘口容量。三只2026日期必须相同并延伸已有188日显式前缀，最后两日由三个真实序列共同报告10月19/20，结合已捕获上交所休市原文核对，不由工作日生成交易日。

成功只表示原文可获取；原价身份/重叠、现金公告和日历未通过前不算组合ROI，账户、PIT、官方限制流/真实到达/开盘队列未认证标志不变。日期截止固定10月20日，整月尚未结束。旧东财错误不能改为新腾讯成功；新独立manifest保存来源差别。
