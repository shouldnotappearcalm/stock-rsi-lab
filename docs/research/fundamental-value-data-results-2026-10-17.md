# 盈利收益率的数据准入：小样采集与原文核对

下一项待研究机制为盈利收益率 E/P。`94e1eb3` 已先冻结并推送采集器、数据边界和固定样本，随后完成 120 个源查询键、5,832 条日估值和 108 条季频财务记录的采集。原始财务版本仍未完全认证，**投资因子尚未准入，未计算新策略收益或读取新的 2026 策略结果**。用户的三段收益目标保持未完成。

## 本轮实际取得的数据

固定样本沿用此前按 2024-01-02 历史 CSI500 主板成员和哈希选择的沪深各六只股票，不按价格、估值或收益换股。它只是数据小样，不能代替完整投资域。

| 项目 | 结果 |
| --- | ---: |
| 股票 | 12 |
| 每股明确交易日记录（含 2023-12-29 基准日） | 486 |
| 原股日估值记录 | 5,832 |
| 日 PE 字段非空 | 5,832 |
| 每股财务期 | 2023Q3—2025Q3，共 9 期 |
| 季频响应和 schema-valid 财务行 | 108 / 108 |
| 日期越界或其他隔离行 | 0 |
| 逐请求预算预留 / 唯一查询键 | 120 / 120 |
| 与已有巨潮原报告日期一致的 pubDate | 96 |
| 原元数据窗口不覆盖的 2023Q3 原公告 | 12 |

日估值包括 `peTTM/pbMRQ/psTTM/pcfNcfTTM`、原股收盘、量额、换手率及历史 ST/交易状态。季频数据保留原始 `pubDate/statDate/epsTTM/netProfit/totalShare` 等字段。`epsTTM/netProfit/totalShare` 各 108 条非空，但 `MBRevenue` 只有 48 条、`gpMargin` 只有 72 条非空，不能把模式正确当成所有财务字段完整；见[逐字段覆盖](../../experiments/qlib/fundamental-value-pilot-field-coverage.json)。空值不填零，负利润及负市盈率原样保留，元/股不缩放为万元/万股。

逐请求响应与整股包分别不可覆盖并保存摘要。请求前先持久化预算预留；成功、错误、未知中断各自留痕，重启不复用已消费尝试，也不重查已经成功的请求。协议为 120 个唯一键、每键最多两次尝试、跨恢复最多 240 次预留。本次均首次成功，没有重试。未登记的已有整股包会在任何网络前拒绝覆盖，另做独立恢复。

## 日期核对通过到什么程度

[独立日期对应结果](../../experiments/qlib/fundamental-value-pilot-pubdate-audit.json)认证了原始响应、请求预算、采集来源和巨潮各股元数据摘要。对财务期、标题财年、报告类型、公告 ID 与发布日期逐项对应，96 条行的供应商 `pubDate` 匹配至少一份已捕获原报告的日期。

其余 12 条属于 2023Q3，而既有巨潮元数据从 2024 年起，不把它们误记为源日期不一致，也不宣称原公告已验证。日期匹配仅核对元数据，没有证明供应商返回的历史数值未经后续追溯修改。

## 原年报确认的字段口径

在打开原文前单独登记样本名单的第一家公司福田汽车及 2023、2024 两份原年报，不依据收益挑选核对对象。已经下载原 PDF、保存来源摘要，并用文本提取和页面渲染核对六个关键页面的行、年度列、元/股单位。

| 财务年度 | 原文合并总净利润（元） | 原文归母净利润（元） | 期末总股本（股） | 供应商 epsTTM |
| --- | ---: | ---: | ---: | ---: |
| 2023 | 858,396,742.86 | 909,480,896.06 | 8,003,763,475 | 0.113632 |
| 2024 | 41,913,726.65 | 80,542,788.99 | 7,917,400,367 | 0.010173 |

来源：[2023 年报](https://static.cninfo.com.cn/finalpage/2024-04-27/1219874919.PDF)第 5、95、109 页；[2024 年报](https://static.cninfo.com.cn/finalpage/2025-04-26/1223327299.PDF)第 5、88、103 页。页码为 PDF 内显示的页码。

两个年度中，供应商 `netProfit` 与合并总净利润完全相同，**不能将它改名为归母净利润用于 E/P**。独立 Decimal 计算的“归母年度净利润 ÷ 期末总股本”，四舍五入至六位小数，分别精确对应供应商的 `epsTTM`。若错误使用总净利润分子，得到的是约 0.107249 和 0.005294，均与该字段不符。

这一核对支持这两个年度观测的字段映射，不能推广为全部 108 行都通过了数值验证。年报基本每股收益、归母利润、合并总净利润和期末总股本仍须分别建模，不能凭名称混用。

2024 年报还披露了期内股份注销及股本变化；这份年报在 2025 年发布，不能据它把整年期末股本提前填入 2024 年各日快照。历史日股本的真实可见版本仍需同期公告支持。2023 年报中的上年同期调整前/后列也必须分别保留，不能仅用财务期键覆盖旧值。

具体逐项数值、页面、原文和包摘要见[原文数值映射核对](../../experiments/qlib/fundamental-first-issuer-numeric-audit.json)。

## 仍需解决的准入缺口

- 补齐 2023Q3 等初始状态的原始公告以及 TTM 所需的同口径财务期。
- 逐版本支持原始/更正数值、对应公告日期及每日股本，不能把后来的财报或更正倒填到旧快照。
- 从小样扩展到完整历史投资域，并为每次排名的财务来源留证；这 12 股不充当投资域。
- 即使日期级信息就绪，真实历史到达小时仍未认证。所有报告暂按公告日期结束后才可能可见，不能把午夜时间戳当成真实发布时刻。

在这些缺口解决前，数据保留 `financial_version_history_complete=false`、`investment_factor_admitted=false`。目前是基本面研究输入准入，尚无候选晋级或新收益结果。

## 证据与复现

- [冻结采集请求](../../experiments/qlib/fundamental-value-pilot-capture-request.json)，SHA256 `d72e8e0e98b0d2711d4995c7e7c9200e38c1a33e593f0fafa8dc8fa01c8fc801`。
- [完整源清单](../../experiments/qlib/fundamental-value-pilot-capture-manifest.json)，SHA256 `12886f2f96547599c7dceb553fa16c5e19764cde995c28a6358560b17d58d409`。
- [日期复核源码](../../experiments/qlib/audit_sources/2026-10-17-fundamental-pubdate-audit.py)与[矩阵结果](../../experiments/qlib/fundamental-value-pilot-pubdate-audit.json)。
- [原文获取请求](../../experiments/qlib/fundamental-first-issuer-primary-doc-request.json)、[PDF 清单](../../experiments/qlib/fundamental-primary-documents-capture-manifest.json)及[数值核对](../../experiments/qlib/fundamental-first-issuer-numeric-audit.json)。PDF 获取清单保留捕获当时的“数值待核对”状态，后续核对另附证据，不覆盖旧清单。

229 项回归测试通过，含源中断、跨恢复预算、成功响应复用、原包拒绝覆盖、源摘要篡改及财务日期边界的反例。旧投资/执行源码摘要保持不变。原日估值、季频响应、PDF 和完整查询日志保留在本地不可变目录；公开仓库保存协议、摘要和核对证据，不重新分发完整第三方数据。

在项目根目录使用已安装 BaoStock 的研究环境执行；输出目录必须不存在（恢复才加 `--resume`）：

```bash
RESEARCH_DATA=/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015
PROVIDER=/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-investment-data-2026-10-13/qlib_bin
PYTHONPATH=src python3 -m scripts.capture_fundamental_pilot_pre2026 \
  --request experiments/qlib/fundamental-value-pilot-capture-request.json \
  --expected-request-sha256 d72e8e0e98b0d2711d4995c7e7c9200e38c1a33e593f0fafa8dc8fa01c8fc801 \
  --csi500-instruments "$PROVIDER/instruments/csi500.txt" \
  --calendar-file "$PROVIDER/calendars/day.txt" \
  --report-dir "$RESEARCH_DATA/cninfo-csi500-reports-20261017" \
  --output-dir "$RESEARCH_DATA/fundamental-value-pilot-new"
```

重新访问供应商可能取得不同的现时版本，新的采集应保留为独立数据集并比较差异，不替换这次数据。
