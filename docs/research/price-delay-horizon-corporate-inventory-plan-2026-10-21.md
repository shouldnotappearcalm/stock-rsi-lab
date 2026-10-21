# Price-delay horizon corporate-source inventory protocol (2026-10-21)

状态：`PREPARED_SOURCE_ONLY_PENDING_TERMINAL_CAPTURE_AND_INDEPENDENT_RAW_AUDIT`。本文件只规定库存与问题清单方法，不是源、事件或账户 admission。未打开正在进行中的 price-delay horizon capture；未读取 2026 收益、账户持仓或财务曲线，未联网、重抓或改仓库。

固定数据根：`/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015`；固定代码根：`/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead`。

## 1. 冻结的旧账与 scope

旧基线为 151 名称、486 source sessions、24 monthly targets、378 events（375 vendor + 3 primary cash supplements），不是其他候选的账户或事件数。下列旧文件必须在任何后续库存/投影前后保持相同原字节：

| 文件（相对 B） | SHA256 |
|---|---|
| price-delay-account-source-events-20261021/derived_events.json | `465bab82c1a2c9b8566011230a3858946ef23667c4ba04e5248b088f6b0e70d0` |
| price-delay-account-source-events-20261021/event_source_receipts.json | `a1de87c2f69544e92256e4c534ecf8d6dad5a3c49291302cd2d6b71269e51cc5` |
| price-delay-account-source-events-20261021/effective_proofs.json | `81b35024c1ad6cbd5c9768901290ce352c58ca92bc710b350120feb07a1a42aa` |
| price-delay-account-source-events-20261021/summary.json | `e3b7f480e44e8cd83d9147efdda705c172bdf9bf4d82617a0b79324da1a51b0c` |
| price-delay-event-source-independent-audit-20261021.json | `934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201` |

继承要求：先用旧 151 原包、旧 effective proofs 与原 pre2026 calendar 重建旧事件，再要求旧 378 event objects、顺序、event_id、全部 receipts 完全相等。完整输出只能 `old_events + new_2026_events` / `old_receipts + new_2026_receipts`；另存两个旧文件的 byte-exact 副本。JSON 数组不应声称在关闭括号前有 byte-prefix；应同时证明原文件 byte copy 与首 378 objects/receipts literal equality。不得重排旧事件、改源 vendor 行或用新公告重写旧税务标记。

203 = 原 151 + 新 52 是 root 给定的后续 scope，尚未从终态 raw/targets 独立认证。本阶段不猜 2026 vendor 行数、supplement 数、缺口数或已覆盖数。终态后，认证冻结 targets 的 34 signals、旧 24 exact prefix、union203 和 raw manifest 名称集合。不能用实际持仓或收益来决定检查哪些事件。

原 151：检查 pre2026 raw bars/distributions/adjustments 的整个原序列相等，检查原 378 事件覆盖。新 52：其 pre2026 distributions 只保存在原包中；计数并记录 issuer/date/row digest 为 `OUT_OF_ACCOUNT_SCOPE_FUTURE_ONLY_PRE2026`，不得编译进旧账或当成新增账户阻塞。它们不是“全网无事件”，也不应篡改或清理掉。

2026 全 203 名称：检查从 2025-12-31 close 边界到 2026-10-20 的全部 bars/reference changes、2026 adjustments、2026 distributions 及相关 quarantine。保留 Dec31 以检查首个 2026 preclose；不能因未来首次入选晚而漏掉 2026 早期行动。必须独立识别 `record < 2026-01-01 <= ex` 跨年事件，按现有 append-only contract 拒绝并单列待处理，不能丢弃、回填旧账或擅自改 contract。

## 2. 固定本地 proof allowlist

按下表顺序检索，使用 event key、issuer、日期与原 PDF hash，而不是目录名推定有效性。相同事件存在多份记录时保留所有 provenance；同 hash 可去重，经济字段或证据等级不一致则 `LOCAL_PROOF_CONFLICT`。不递归扩展到其他账户、策略报告或收益文件。

| 允许的 reviewed/proof 文件（相对 B） | 当前 SHA256 | PDF refs |
|---|---|---|
| low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json | `01dcd1f8e96c544243ee88c446075cdaf68e8fd772dc45813144c85094251c0a` | 7 |
| low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json | `7fdec0f62c3a83842c9e447a19416d9dd4b4165a44669484822e9d841c5a7d80` | 6 |
| szse-value-momentum-full-reviewed-proofs-20261021.json | `ac0cf40ccc3dc1d4ab3a723bfcd1e75cb34f51cac3068bba879b12033a09b9d8` | 14 |
| szse-value-full-corporate-notices-20261017/reviewed-manifest.json | `0c14b8e9bfa421a20b5bb6b1befd4b8c0c7c93e674b9f87e910394efacd64723` | 2 |
| return-family-corporate-notices-20261017/reviewed-manifest.json | `a77d0caf8788616fee773c1c4e5a0b9614956cbd0f79732644fee0b0b85b1bd8` | 3 |
| reversal-full-corporate-notices-20261017/reviewed-manifest.json | `ff7d6c9e1a17978c74d204a616f1bd965600a5605d02667570256d881ccbf022` | 9 |

上述 41 个 PDF references 的实际文件 bytes 已按各 manifest SHA 核对（跨根允许重复；不是本次重新做全文内容审查）。低 beta 两个 reviewed 目录 PDF 就地解析；Value+Momentum 的 PDF 优先使用 `documents[].source_path`，两份继承 PDF 明确指向 low-beta horizon reviewed 目录，不按任意 basename 全盘搜索。

辅助 primary capture 只允许上述 manifest 明确绑定的本地 capture/request/receipt 链：low-beta 原 2026 与 horizon primary、`szse-value-momentum-primary-2026-gaps-20261021`、`szse-value-momentum-noncash-2026-capture-20261021`、reversal 原 capture。只有单独 capture 而没有完整内容 review 的资料标为 `CAPTURED_NOT_REVIEWED`，不能直接成为经济或税务 proof。

原 price-delay reviewed 15 PDF 及 budgeted-residual / illiquidity / SZSE-value development manifests 只作原 378 继承 provenance，不将其中 pre2026 行加入新 52 的账户。当前 SZSE-value full（2 docs）与 return-family（3 docs）allowlist 没有新增 2026 proof：这仅表示这些固定本地 manifest 无匹配，不表示发行人未公告或全网不存在。

公共内容 review 固定文件及 hash：

- `/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead/experiments/qlib/low-beta60-2026-corporate-content-review.json`：`8a78937656054e77e4107a13d85d7d8475a1d1d1c2bfb11caba64cabc563c960`。
- `/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead/experiments/qlib/low-beta60-horizon-primary-content-review.json`：`66fd7313d11a9ed1ed60c48121b904baed9a915a2a2c49fc2847ee978a73168b`。
- `/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead/experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json`：`0b1f5dc599412f0b0e37fbe11e6a4ab508519e9320b848858aa05bae4e0cc4ec`。
- `/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead/experiments/qlib/szse-value-momentum-noncash-2026-content-review.json`：`eadbd5d0262d2780040e2bf5e835ccfa427f2254be7aaaf4a0cc53f5cde290b7`。

## 3. 当前仅作为候选证据的 event keys

下表来自固定本地 proof；尚未与 price-delay 终态 203 raw 匹配，不能声称均是该候选必需事件。所有金额仅为公告来源字段，不涉及收益。

| 候选 event key | 类型 / 既有证据边界 |
|---|---|
| SH601128\|2026-06-09 | low-beta 直接 issuer premium-source/no-tax statement；仅该 event |
| SH603826\|2026-07-14 | low-beta 0.3 stock/original share、0.3 taxable income/original share；来自公告税例算术，不是资本转增免税 |
| SZ000937\|2026-06-17 | unresolved capital tax：实施现金0.1、capital0.1；后出半年报只补 retrospective premium-source，不补 no-tax 声明 |
| SZ000975\|2026-04-24 | primary precision 0.480402 → 0.4804021；0.4796827 是 reference deduction，不能当应收现金 |
| SH601918\|2026-02-06 | low-beta primary cash supplement0.05；终态若 vendor 已有同一 event 则不可重复 supplement |
| SH601598\|2026-10-20 | low-beta primary cash0.14；conservative publication Oct13 / signature Oct12 保留区别 |
| SZ000034\|2026-05-19; SZ001309\|2026-10-13; SZ002335\|2026-05-29; SZ002595\|2026-05-11; SZ002837\|2026-06-01 | VM 五份有限 `PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE`，不可改为 direct/no-tax/statutory；SZ002837 原 metadata/signature caveat 保留 |
| SZ000563\|2026-10-20; SZ000783\|2026-10-20; SZ002608\|2026-10-19; SZ002756\|2026-10-20; SZ002812\|2026-10-20; SZ003031\|2026-10-20 | VM 六份 cash supplements 候选，分别0.01/0.05/0.05/0.3/0.41/0.185；只在对应终态 vendor 同 event 确实缺失时使用 |
| SZ002131\|2026-10-16 | VM 七公告之一；原 VM vendor 已存在现金，故本地 proof 不意味着再新增 supplement。新候选也须先逐行匹配 |
| SH603737\|2026-06-01 | reversal 直接 premium/no-tax statement，capital0.2；不得移植到不同年份事件 |
| SH600895\|2026-10-16; SH601966\|2026-06-24 | reversal primary cash0.064/0.042；同样只能缺 vendor event 时 supplement |

low-beta 原 horizon 另外两个 vendor-backed Oct cash（SH600398 Oct14、SH600312 Oct15）不是仅凭已有 compiled account 或 vendor row即可认证的 primary proof；若 price-delay 终态需要额外证明，应列明原行及本地 primary evidence 是否足够，不能从其他候选账户倒推。

## 4. 每次 reuse 必须认证的字段与链

每条问题/候选复用项记录：`instrument|economic_ex_date`、原 vendor literal row、row SHA、raw packet SHA、manifest SHA、原 adjustment row/day/SHA、原 preclose anomaly day（若适用）、source kind、匹配状态、所有 proof根与 hash、原PDF绝对路径/hash、完整内容 review 路径/hash、相关完整页及字段页、未解决问题。event key 相同不替代全字段检查。

PDF 与 receipt：认证原发行人/证券及 A/B class、原文件 bytes/hash、publication day与signature day、notice类型/announcement id；capture manifest+request hash；若为 HTTP 路线，递归认证 request/reservation/response 文件 hash、原响应到 PDF bytes digest、成功/无 redirect/完整体与 received-at。若是 byte reuse，认证原 reviewed/capture manifest 与原 PDF 的 byte identity，保留原 receipt 缺失，不制造新的 HTTP receipt 或 arrival timestamp。

经济字段：公告实际 eligible original share gross cash、单位及每10股换算；cash reference deduction单列且永不替代entitlement；stock、capital分别独立；record/ex/pay/list日期与适用对象、币种及自派/代派范围；差异化 eligible base、excluded treasury/compensation class如影响应收口径须保留。税后示例不能当 gross cash；通用股本送转 boilerplate 不构成送转。

capital proof：源类别（明确 share premium 还是 generic reserve）、原 no-tax 明文或有限税例推断、适用投资者范围、proof evidence kind/pages、verified_exempt 的既有语义，不因为目录是 reviewed 就升级。stock proof：expected_stock_per_original_share 与 taxable_income_per_original_share（税基，不是市价）均需原公告/税例完整推导；没有证明时只加 zero-ownership guard，不能套资本转增豁免。

precision proof：仅支持 cash-only 原 vendor event；同时绑定 source_row_sha256、expected_vendor_cash、有效主公告gross cash、原PDF hash、announcement；数值必须是同源显示精度截断的更完整值。若原行/announcement不同，先标为 `ROW_BINDING_MISMATCH`，不得沿用别的 raw row digest。完全缺 vendor row 的现金是 supplement，不是 precision；已有 event 或同日期重复必须拒绝。

content review 尚不足完整认证上述必要字段时，只列 `LOCAL_PDF_PRESENT_CONTENT_FIELD_PENDING`，保留原 PDF/review 索引；必要时后续授权读完整相关页再投影，不能将现有税务推断强化。

## 5. 问题清单重建与 guard

终态后分别重建三组集合：2026 vendor distributions（包括正 cash/stock/capital 与 blank component）、2026 adjustment labels、raw preclose相邻session差异；仅将原始 source facts 与本地 primary 匹配，不从 adjustment ratio 或 price gap解出现金/送转。raw coverage 数学规则：邻日 valid close 到当前 preclose 差异超过原0.005容差，需要该日已编译 event；adjustment无同日 event 时只允许前一明确 session存在已独立日期 event作为 coverage关系，仍标 `FACTOR_DATE_SEMANTICS_UNAUTHENTICATED`，不创第二收入。沿用代码算法而非其旧全局cutoff，新的范围/endpoint必须另行绑定 reviewed adapter；不得偷偷改变旧方法常量。

逐项状态：`VENDOR_EVENT_PRIMARY_MATCH`、`PRIMARY_SUPPLEMENT_REQUIRED_VENDOR_ABSENT`、`PRIMARY_CASH_PRECISION_COMPLETION`、`LATE_FACTOR_EXISTING_DIVIDEND_ONLY`、`CAPITAL_TAX_DIRECT`、`CAPITAL_TAX_CONDITIONAL_INFERENCE`、`UNRESOLVED_CAPITAL_TAX_ZERO_RECORD_OWNERSHIP`、`UNRESOLVED_STOCK_TAX_BASIS_ZERO_RECORD_OWNERSHIP`、`LOCAL_PROOF_CONFLICT`、`NO_MATCH_IN_FIXED_LOCAL_ALLOWLIST`、`OUT_OF_ACCOUNT_SCOPE_FUTURE_ONLY_PRE2026`。quarantine中本窗内且未分类的分红、同 event conflicting revisions、缺 session或不明上市边界均单列，不能因为capture成功就admit。

必须原样保留旧 SH603596|2024-05-20 unknown guard（capital0.4，stock0，未获得豁免）；若203 scope出现 SZ000937|2026-06-17，同样保留 literal unresolved（verified_exempt=false，strict_tax_admission_resolved=false）。凡新发现capital>0而无同事件足够tax proof，或stock>0而无同事件税基proof，都要求登记持仓为零；实际股份账户后续若登记数量>0应在变更前fail。不能以target无权重、此刻未持仓或“未来名称”豁免2026该条件，不能改信号/交易以绕过guard。该库存不认证实际zero ownership。

## 6. 终态通知后的退出条件与负控

先要求 root明确capture进程terminal，绑定 manifest/calendar/203包/target hashes、完整 source journal、errors/pending/stop/logout/postcheck 与独立raw audit；partial或rejected packet保留原原因，不从缺文件推断无行动，不重抓。先确认旧151所有原序列与原378/receipts不变；所有2026 scope 行归类后再形成冻结的新reviewed proposal；当前不写该proposal、不编译源、不调用账户。

后续独立source-output audit必须重建新事件的全部经济字段/日期/ID/receipts与原378prefix。meaningful内存负控至少包括：改变原151前缀、给新52塞入pre2026事件、遗漏Dec31边界、重复supplement、reference cash冒充应付、错A/B日期/单位、错PDF/row hash、factor创造第二收入、把conditional改direct或把SZ000937/SH603596升为exempt、删unknown guard、跨年record/ex漏检。真实输入与缓存保持不变。

本阶段仅ready for bounded local source inventory after terminal notification；不授权网络、真实新查询、账户重放、策略选择、2026收益观察或ROI。historical first-arrival/PIT、actual FIFO税额、实际到账与registry零碎股分配始终未认证。

## 7. SH603233 Oct19 限定本地检索附录

root 后续报告 June26 fore coordinate 从1.000000到0.977969且新增Oct19 adjustment、无对应vendor分红。本阶段没有读取新raw核验这些源事实；它们仅是待查问题。按既有根展开上述 reviewed/capture provenance 后，以下26份manifest全文及对应根顶层文件名无603233命中。故没有可给出的 SH603233 Oct19 registered primary PDF/经济proof/hash，状态是 `NO_MATCH_IN_FIXED_LOCAL_ALLOWLIST`，不是全网不存在。不得从0.977969反推cash，不能据此reassemble或admit。

| 已检索文件（相对B） | SHA256 |
|---|---|
| low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json | `01dcd1f8e96c544243ee88c446075cdaf68e8fd772dc45813144c85094251c0a` |
| low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json | `7fdec0f62c3a83842c9e447a19416d9dd4b4165a44669484822e9d841c5a7d80` |
| szse-value-momentum-full-reviewed-proofs-20261021.json | `ac0cf40ccc3dc1d4ab3a723bfcd1e75cb34f51cac3068bba879b12033a09b9d8` |
| szse-value-full-corporate-notices-20261017/reviewed-manifest.json | `0c14b8e9bfa421a20b5bb6b1befd4b8c0c7c93e674b9f87e910394efacd64723` |
| return-family-corporate-notices-20261017/reviewed-manifest.json | `a77d0caf8788616fee773c1c4e5a0b9614956cbd0f79732644fee0b0b85b1bd8` |
| reversal-full-corporate-notices-20261017/reviewed-manifest.json | `ff7d6c9e1a17978c74d204a616f1bd965600a5605d02667570256d881ccbf022` |
| price-delay-corporate-reviewed-20261021/reviewed-manifest.json | `a7cd5b97694232e3503990e3db60a805c0e6e82f8ec894f02283b7d9b3582fb9` |
| budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json | `dc4238cd0ad53c6fb064010cb44dbfd11d3a8ee2e766e7f7484ff92f22033247` |
| illiquidity-corporate-reviewed-20261020/reviewed-manifest.json | `d589c067f1498df1f6cffb810863751414155f05429dc44c934e5be861fa9ae4` |
| szse-value-corporate-notices-20261017/reviewed-manifest.json | `fe5d1b9b29cee2b674c65caaafdd0910ec463945b32f8f4b7a8a60f727aecda6` |
| low-beta60-corporate-reviewed-20261021/reviewed-manifest.json | `931d97fc704c0e2c3e08717b584048698752c3a791ee04935c8d91fe959300e4` |
| low-beta60-corporate-2026-20261021/manifest.json | `bbc2ca69bea797b7edb4228c70356972fc055fe18bf8dd8c18e446bdfc8a7ddf` |
| low-beta60-horizon-cninfo-primary-20261021/manifest.json | `154b58f1baff99e059c641ab3ada1369d5cf6865f2f3c0604c04638bc5e84710` |
| low-beta60-horizon-missing-primary-20261021/manifest.json | `e8d9088504c3e4ea0fc9c2c2075a0a34eb73fe3429117fdc747dec0a05340555` |
| low-beta60-primary-literature-20261021/manifest.json | `68d0f1794e910ee69e2b1259330823d3aef8c584b3804d241aabd61e85ca2556` |
| szse-value-momentum-primary-2026-gaps-20261021/manifest.json | `31f32ff7ff86ecea75c543eea78967deedcd2262fe8e5d00543a4bdcba48cb65` |
| szse-value-momentum-noncash-2026-capture-20261021/manifest.json | `faa7a5ec488e6b35021d96ce5d379cfa9e37c32d4b0fe8073bd98bb1a86d5a04` |
| szse-value-momentum-primary-capture-20261021/manifest.json | `f2191de5406e83a9d6319000cdeca525199fae531f8e7b0cd908d6644eff7c80` |
| price-delay-corporate-primary-20261021/manifest.json | `238c63fcbeaad7e78c6bf69e928c54da3d46c1faab6439ca139bfb866b6b5c76` |
| low-beta60-corporate-sources-20261021/manifest.json | `4575c850becfa049fa7876dfe1f6fff0869d685f848dde76ed4c8d3cd3bc1158` |
| low-beta60-corporate-continuation-20261021/manifest.json | `d5368ff85a6a46443d0869d13354e3ea8ccc76426feb1cac58ac227509976e19` |
| budgeted-residual-corporate-notices-20261021/manifest.json | `d1f2ad707004e111e9270f8b953b9abe97332182f8f7ba17794ca027db2b527d` |
| reversal-full-corporate-notices-20261017/manifest.json | `c9e547dafce1037f9b9725abc64ce883c88c1773e4df916f253ae86da43d8f59` |
| szse-value-full-corporate-notices-20261017/manifest.json | `4db4f616056c618419f053b57497ee39bb97aa1c347b085ce05b4bed99b77e7a` |
| return-family-corporate-notices-20261017/manifest.json | `dc42da1e6683a418e2d59a358b978515b2f985f65885082c6207757d1e0f1de9` |
| low-risk-corporate-proofs-20261017/manifest.json | `ef97c73712072ed58a05dceea01cc041063a013f8229defbe22d25089a4d1c25` |

结构化原始检索报告：`/tmp/price-delay-SH603233-local-primary-inventory-20261021.json`；SHA256 `113f452ca9267b5b273726467a3d5b09d0c4d3ad5265bb50711642be19f74acf`。未联网、未读partial raw、未计算账户/收益。
