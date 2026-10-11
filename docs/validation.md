# 首版验收记录 — 2026-10-11

测试使用Python 3.12标准库，`PYTHONPATH=src python -m unittest discover -s tests -v`，43项通过。
独立agent代码审查先复现问题，再补回归；最后针对修复复审，无剩余重要问题。
审查覆盖工程边界，不代表投资方法经过独立实证评价。

| 验证 | 实际结果 | 留存路径 |
| --- | --- | --- |
| 合成全区间 2024-09-02至10-18 | 45次wake，3笔fill，无错误 | artifacts/final-synthetic |
| 固定响应重放 | wake/订单/错误/成交/账户一致，校验保存快照 | artifacts/final-synthetic-replay |
| 五组开发对照 | 每组2次有效评估，均保留seed；未发现改进 | artifacts/final-comparison |
| Codex时点决策 | 1次成功；BUY100，仅挂至10-08，不在09-30成交 | artifacts/final-codex-decision |
| Codex决策重放 | 固定响应与挂单/账户一致，不重复调用模型 | artifacts/final-codex-decision-replay |
| Codex修改提案 | 1次成功；min_pullback改0.005，重跑后成交/收益未改善 | artifacts/final-codex-proposal |
| 600519真实原价探针 | 58行、70次wake、零成交，无工程错误 | artifacts/final-real-price |

实际Codex运行：内置CLI 0.159.0-alpha.12.1，gpt-6.1-sol，low。
最终决策调用input19756/output325 tokens；最终提案input16824/output100 tokens。
这些是两个单次接入smoke，不是与两次候选对照的等预算LLM效果实验。
旧CLI 0.139.0失败及原始事件仍保留在artifacts，未被计为成功或零成本交易。

合成净值数字仅用于计算回归，不作金融收益推断。随机组中的shorter-hold实际改变了
成交数并降低该合成开发期结果；所有组仍保留seed。真实价格探针零成交不能支持收益结论。

审查后修复：日线未来日期/收盘时间校验；缺失成交日/持仓行情无效；最终陈旧估值识别；
回放同时校验订单、错误、wake、快照和agent-call摘要；流式stdout/stderr上限、回答大小、
有限超时、整进程组清理；手续费舍入前验证可支付；反馈解析修订及统一17:00估值。

手算回归：国庆前发出BUY100，10-08开盘11.7成交，手续费2.34；随后SELL100在
10-09开盘12.98成交，手续费2.60；初始2000，最终现金2123.06，无持仓。

当前验证范围：时间/接口/回归/有界搜索工程。真实PIT数据、正式封存评估、跨情境迁移、
改进器自身递归、前向paper尚待后续实施，见roadmap.md。

运行源码摘要：`38c40c758c105edc5db6f29a1dbc398e925b266352440e35b4cac168bc40e14e`。
源码修改会拒绝旧cassette重放，须重新运行历史环境。原始真实价格数据及旧实验为
本地研究材料，data/local与artifacts被Git忽略，但本机项目目录保留完整副本。
