# RSI-Anything 源码分析 — 2026-10-12

分析版本：`99dbf000a424b9033651b1096c5da2b6d5fa3865`。实际clone后阅读源码、论文v1及官方发布索引，共570个tracked文件。未修改上游代码；浅克隆固定到此commit。
论文：[RSI-Anything](https://arxiv.org/abs/2610.13912)，2026-10-09提交。

## 结论

它把“生成候选→预测结果→选择候选→获得外部反馈→学习→保留更新”连成跨轮过程，核心是policy/workflow与预测器的耦合更新。适合作为投资harness中候选评估、失败归因、预测器更新和版本验收的参考；仓库没有股票投资内核或金融验证结果。

论文的policy配置可以是可训练参数，也可以是持久化agent workflow。代码中最完整的policy/world共同更新路径是GUI；code repair主要固定coder、更新执行结果预测器。更新反馈记录本身不等于更新了策略或模型。

## 已发布实现与论文主张的边界

| 领域 | 实际代码范围 | 更新范围 |
| --- | --- | --- |
| Code repair | 初始/semantic/expanded/incumbent四阶段world训练、候选排序、公开测试反馈、最终hidden judge | coder冻结；world及readout更新；eval期间optimizer_steps=0 |
| GUI | 浏览器交互、真实训练分支、policy SFT、world训练、两代提案、开发选择、冻结、交叉测试 | policy和world都可变，保留被接受的组合 |
| Laboratory planning | 4候选生成、预训练policy adapter和world的推理/选择 | 当前推理时冻结；没有本地五轮完整训练/保留链 |
| Reaction optimization | 321候选池的已校准预测表，EI序贯推荐 | 表冻结；反馈更新incumbent和已观测集合，online_prediction_update=false |
| Immune science | README | 当前Coming soon，官方模型索引为planned |

共享CLI目前只接受code_repair/gui，其他领域有独立入口；不能把五域论文结果理解为一个统一可插拔训练器已全部交付。证据：[共享任务配置](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/src/rsi_anything/workflow/config.py#L38)。

## 机制：代码里真正值得提炼的部分

### 1. 候选与保持现状一起比较

Code repair每轮四个修改候选加keep_current，预测新候选效用必须严格超过当前版本才替换；最多三轮公开反馈，最终所有决策封存后才读取hidden tests。效用由全套通过概率和部分通过率读出构成，而非直接执行所有评估测试再选最好的。

[choose / Predictor](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/code_repair/src/evaluation.py#L27)；[public seal与最终judge](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/code_repair/src/evaluation.py#L164)。

对股市的映射建议：候选应是明确的组合目标/退出动作，包含维持当前组合或现金选择；预测分数是排序工具，实际收益与成交账本仍由外部回放环境产生。

### 2. 预测与实际反馈绑定

GUI每个动作保存before/action/after、proposal、forecast、selection和严格任务反馈；训练分支来自真实访问状态，环境可重置后执行全部合法分支和专家延续。训练分支的反馈不会在当次acting中提前打开。world训练使用新反馈与旧经验回放；policy只用严格成功episode的正动作，去重并配旧经验。

[episode与分支回放](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/src/rsi_anything_gui/experiment.py#L40)；[policy update](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/src/rsi_anything_gui/policy_train.py#L9)。

金融映射需保留预测时的snapshot hash、输入/版本、预测分布、真实成交、收益兑现时间和误差。股票盈亏具有随机性，不能直接照搬“成功轨迹即好策略”的筛选法；失败和亏损案例也需要保留用于归因。

### 3. policy/world成对保留，交叉诊断

GUI两代proposal从当前incumbent采集反馈，分别训练policy/world，做终止概率校准与controller开发选择。开发集新组合收益和成本通过固定门槛才替换incumbent；两代均冻结后才打开RSI test。之后执行旧policy×旧world、旧policy×新world、新policy×旧world、新policy×新world，以及policy-only测试。被拒绝的候选也报告。

交叉测试是归因诊断，代码没有在test结果里再挑一个赢家回写incumbent。

[两代更新及成对晋级](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/src/rsi_anything_gui/rsi.py#L9)；[冻结后交叉测试](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/src/rsi_anything_gui/rsi.py#L59)。

对股市最重要的启发：策略修改会改变候选/持仓分布，使旧预测器失准；预测器修改也会改变选择。需要知道收益变化来自哪一方，不能只保存“最新版”。

### 4. 世界模型有明确的退回路径

独立terminal calibration cohort按Brier选温度/偏置；开发集测试hybrid alpha。未达到开发增益和成本门槛则alpha=0，按policy排序，world不参与该次action selection。

[校准与controller选择](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/src/rsi_anything_gui/worker.py#L14)；[alpha=0分支](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/src/rsi_anything_gui/experiment.py#L17)。

因此这里的Gate还管“预测器何时值得启用、哪个组合值得保留”。其GUI数值门槛（如4个百分点、1.2倍成本）属于特定协议，不可直接移植为股票收益阈值。

### 5. 可恢复实验与数据身份

共享runner使用独占锁、源码/输入身份、阶段产物hash、原子状态、失败输出归档和checkpoint继承；resume会验证已完成阶段。结果文件存在不等于阶段完成，进程退出成功也必须生成声明产物。

[runner](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/src/rsi_anything/workflow/runner.py)。我们已有的快照/账本可保留，并补policy/world成对身份与预测误差轨迹。

## 不能被结果表迷惑的几点

1. GUI 99%主结果在同一click-checkboxes模板的100个测试实例上，两个RSI提案、一个训练seed。文档明确selected controller为alpha=0。随附终点记录可重算51→79→99，policy-only也为51→79→99；不能把此headline全部归因于推理阶段world融合。纯world结果另报，不能把它也忽略。[GUI results](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/gui/docs/RESULTS.md#L21)。
2. Reaction的96.15%是一个固定反应上下文/候选池的观测最优yield，100次不同初始化回放；预测表保持冻结，不代表100次在线模型自进化。[selector](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/reaction_optimization/src/suzuki_inference/selector.py#L19)。
3. 论文描述条件性world adaptation；GUI发布流程按固定两代训练world，并非可插拔、全域通用的漂移触发器。金融非平稳预测器的校准、数据充分性、触发规则仍需自己实现。
4. JEPA的OPF factors是潜在表示分解，不是价值/质量/动量等投资因子，更不等于可直接编辑的投资skill。实验室推理OutcomeModel直接predictor→head，OPF用于可选factor导出；仅从发布推理代码不能验证训练时OPF贡献。[laboratory world](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/tasks/laboratory_planning/src/lab_inference/world.py#L13)。
5. 作者在code repair复现文档中自披露：打包验证没有完整epoch重训，reference checkpoint严格正交/因子独立geometry检查未通过。需要按实际诊断判断表示性质，不能根据OPF名字假定严格独立。[reproduction guide](https://github.com/Gen-Verse/RSI-Anything/blob/99dbf000a424b9033651b1096c5da2b6d5fa3865/docs/reproduction.en.md)。

## 对当前股市项目的具体组合建议（本报告的推断）

建议在现有PIT时钟和账户上增加两条独立的版本链：

- 投资policy/workflow：投资假设、因子读取/解释、候选排序、组合分配、退出与风控skill。通过ACP等调用外部agent时，进化对象可以是这些持久workflow，不必训练Codex权重。
- 结果预测器：给同一时点的候选组合预测收益/风险/费用/成交结果与不确定性；先与简单模型和不用预测器的policy比较，证明确有候选排序或评估效率增量后再投入复杂JEPA训练。

每轮先输出候选和预测，真实回放提供成熟反馈；失败报告区分信号、仓位、退出、成本与预测失准；提案只改明确模块，重跑后做组件/成对验收，保留父子版本。阶段性校准和旧经验回放用于抵抗候选分布改变与遗忘。

需要固定状态/行动/目标与总预算，所有反馈只有在历史时钟中已经兑现才可学习。股票价格路径难以像GUI那样重置并开展真实反事实交互；历史价格重放只能在明示价格接受者/成交模型下提供模拟反馈，仍需按时间向前验证。

因此该项目最值得借鉴的是预测误差驱动的共同更新和成对归因，仍需与模块契约/谱系设计及具体投资内核结合。它本身不补出经济假设、历史投资域或可交易收益。

## 本次实际验证

- 22项共享workflow/assets测试通过；这些测试使用本地临时子进程/模拟资源，不是GPU训练结果。
- GUI release verifier通过，443个文件一致；full_gpu_rerun=false。
- 6项纯选择函数AST断言通过，检验保持当前候选、拒绝非有限分数、alpha=0退回和pure-world排序；未加载GPU模块。
- 仓库总verify_repository失败：英文/中文README与SHA256SUMS不一致，其余manifest文件hash一致。克隆tracked clean，未修改上游文件。
- 另有结果口径待解释：README/论文CodeContests为31.2%，打包reference为188/600=31.3333%，validation文件也记188；本次没有重跑600个GPU评估，不能判断差异来源。
- 读了官方Hugging Face MODEL_INDEX/MANIFEST。Lab发布索引主要是三个world checkpoint，免疫planned；没有下载大模型，也没有宣称复现全部论文指标。

原始盘点在audit.json，官方小型索引已保存；所有源码引用固定到本commit。项目自有代码Apache-2.0，第三方模型/数据保留各自条款。
