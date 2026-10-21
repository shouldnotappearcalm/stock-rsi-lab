# 固定价格延迟候选：2026 分钟来源清单

`inventory_price_delay_horizon_minutes.py` 只生成来源清单，不发起查询、运行账户或
计算收益。首次实际清单执行前冻结请求、脚本、原始方法与输入哈希，并commit/push。
输出固定新目录 `price-delay-horizon-minute-inventory-20261021`，存在则拒绝覆盖。

保持旧累计 seen 名单 × 固定月度执行日生成算法；唯一AST差异是把来源日期上限
从2025-12-31扩展到2026-10-20。普通分钟准入函数的AST不变，仅绑定新来源日期
检查；日历、前24个目标对象、旧2502pair/2halt、2490普通通过和12ST拒绝逐项对齐。
ST/unknown不能按静态目标名单删掉，也不能据此证明实际零持仓。

缓存顺序在实际清单前固定为请求中的11个root。对每个新pair检查所有命中缓存，
逐包核验hash、证券、日期、状态与响应签名。不同响应保留为conflict；无效、失败
缓存保留为invalid，不当作missing重新抓取，不按回测效果或质量挑更有利的root。
真正无缓存的pair单独列出，数量才是后续另行冻结的采集预算。

核对203原始包、676显式日历、34固定目标及原独立raw重建报告。48个旧财务文件
逐个实际hash前后复验；仅summary里的artifactmap相同不能证明文件未变。旧分钟
采集、原失败准入和ordinary-scope独立报告的对应SHA/完整标志必须与实际文件一致。

产物 `details.json` / `summary.json` 记录全部新pair、缓存来源、缺口、invalid、
conflict及ST/unknown标志。此清单不授予source/account准入；后续真实账户仍需
按所有实际持仓、父子单及登记权益检查ordinary依赖，未知税/非整数权益守卫不变。
