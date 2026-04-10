# 仓库导览：给评委的最短阅读路径

这份导览不是重新设计仓库，而是告诉评委：**按什么顺序看，才能最快看懂这套系统的判断依据、边界与实现落点。**

## 1. 建议阅读顺序

### 第一步：先看 `SESSION6_HANDOFF_MANIFEST.md`
先看它，因为它定义了 Session 6 的身份：**总装与交付包装，不是重设计。**

你会从这里得到三个最重要的判断：

1. 哪些文件是 authoritative inputs
2. 冲突时优先遵守谁
3. Session 6 被允许做什么、不允许做什么

### 第二步：看 `docs/00_master_execution_spec.md`
这是顶层执行规范。它告诉你：

- 系统最终要解什么问题
- 四个 Agent 的边界是什么
- 为什么检索必须走 `32 -> 128 -> 1024 -> sparse -> RRF -> rerank`
- 为什么粗排阶段只能拉轻量字段

如果跳过这份文档，后面看到 SQL、pipeline、workflow 时会误以为它们只是“实现细节”，看不出背后的硬约束。

### 第三步：看 `docs/01_shared_contracts.md`
这份文档锁死命名契约。重点不是“风格统一”这么简单，而是：

- JSON、SQL、Python 必须共用同一批字段名
- `trace_id`、`version`、`schema_version` 等追踪字段必须稳定
- `target_vec_32`、`score_rrf`、`final_score` 之类的字段不能在不同层漂移

如果这份文档不成立，整个系统后面会退化成“每层都能随手改字段名”的脆弱脚手架。

### 第四步：看 `docs/02_agent_workflow_fsm.md`
这里说明 C 端评测链路怎么运行，以及为什么要有熔断和节流：

- persisted 生命周期只有 5 个顶层状态
- X-RAG 不能高频乱触发
- 失败必须变成结构化错误对象
- `geek_cert_report` 是展示资产，而不是向量资产替代品

### 第五步：看 `docs/03_data_model_notes.md`
这份文档把 PRD 里最危险的逻辑矛盾点名出来。评委如果想问“你们到底改了 PRD 的哪些地方”，主要答案就在这里。

### 第六步：看 `prompts/`
到这里再看 prompt，顺序就对了。因为此时你已经知道：

- Agent 只是受约束执行者
- prompt 不能凌驾于 shared contracts 和 schema 之上
- prompt 中的示意 JSON 不是自动等于最终输出契约

建议顺序：

1. `prompts/ingestion_agent.system.md`
2. `prompts/battlefield_agent.system.md`
3. `prompts/xrag_agent.system.md`
4. `prompts/oracle_judge_agent.system.md`

### 第七步：看 `schemas/` 与 `sql/`
这一层看的是“真正可落地的结构边界”。

- `schemas/judge_result.schema.json`
- `schemas/geek_cert_report.schema.json`
- `sql/001_core_tables.sql`

重点观察：

1. Judge 和 Report 是两个独立契约
2. SQL 没有把 report 当向量表替身
3. assessment 生命周期状态与 master spec 保持一致
4. 向量字段名、评分字段名都与 shared contracts 对齐

### 第八步：看 `workflow/orchestrator_flow.py`
这份文件把四个 Agent 如何串起来写成了 Python 风格伪代码。它的价值不是可直接运行，而是让你看到：

- 调用顺序
- retry budget
- contract validation
- circuit breaker
- trace_id 一致性

注意一个容易误读的点：这里存在 `INGESTING`、`XRAG_MONITORING` 等内部运行阶段，但**持久化顶层状态仍然只有**：

- `PROVISIONING`
- `COMBAT_ACTIVE`
- `EVALUATING`
- `CERTIFIED`
- `FAILED`

### 第九步：看 `app/search_pipeline.py`
这是 B 端检索 mock 的落点。评委通常会问：

- 你们有没有真的把 layered recall 写出来？
- sparse 是不是只做 sidecar？
- 有没有在粗排阶段拉大 payload？
- RRF 是不是黑盒库？

这份文件会直接回答这些问题：

- 有 layered recall
- sparse 只是补漏 sidecar
- payload fetch 被延迟到 shortlist 之后
- RRF 是手写实现，不是黑盒依赖

### 第十步：最后看 `examples/`、`run_demo.sh`、`README.md`
这里是交付包装层：

- `examples/`：给评委看输入和结构化产物长什么样
- `run_demo.sh`：给评委一个最短可执行入口
- `README.md`：把问题背景、PRD 缺陷、修正思路、目录结构和 mock 运行方式讲完整

## 2. 每个目录解决什么问题

### `prompts/`
解决“每个 Agent 在运行时被允许做什么、不允许做什么”的问题。

### `schemas/`
解决“结构化输出到底长什么样”的问题。它比 prompt 示例更硬，因为它更接近验证边界。

### `sql/`
解决“数据如何存、如何回放、如何发布为检索资产”的问题。

### `workflow/`
解决“四个 Agent 如何串联、如何失败、如何重试、如何限流”的问题。

### `app/`
解决“mock 版检索链路是否真的按规范落地”的问题：

- `mock_data.py`：生成程序化 mock 资产
- `mock_rpc.py`：模拟 RPC 风格的轻量召回与延迟 payload 获取
- `search_pipeline.py`：执行 query parse、layered recall、RRF、rerank

### `tests/`
解决“这些关键纪律是否被代码守住”的问题，例如：

- 分层召回顺序
- payload fetch 时机
- filter gate 是否先执行
- must-have 能力是否参与排序校正

### `examples/`
解决“给人看的示例输入和示例产物应该长什么样”的问题。

### `docs/`
解决“从执行规范到工作流、数据模型、检索说明，再到仓库导览”的说明问题。

## 3. 如何从 Prompt 走到 Schema / SQL / Pipeline

这是评委最值得看的主线。

### 3.1 Ingestion：从简历证据到候选人能力信号

- Prompt：`prompts/ingestion_agent.system.md`
- 约束：只能输出 role-scoped `candidate_dna`
- Workflow 落点：`workflow/orchestrator_flow.py` 中 `_ingest()`
- SQL 含义：它不是直接发向量，而是后续账本与聚合的输入之一

结论：Ingestion 只负责提取信号，不负责“定终身”。

### 3.2 Battlefield：从能力信号到可观察战场

- Prompt：`prompts/battlefield_agent.system.md`
- 约束：必须生成可观察 checkpoint、故障面和注入槽位
- Workflow 落点：`_render_battlefield()` 与 `_execute_battle()`
- SQL 含义：后续 battle evidence 会沉淀到问题、证据和评分账本

结论：Battlefield 的职责是造战场，不是给分。

### 3.3 X-RAG：从战斗事件到受治理追问

- Prompt：`prompts/xrag_agent.system.md`
- 约束：只在合法 trigger source 下触发，且必须受 circuit breaker 管控
- Workflow 落点：`_maybe_trigger_xrag()`
- 设计目的：让追问成为精确施压，而不是噪声放大器

结论：X-RAG 是证据驱动的补刀器，不是持续话痨。

### 3.4 Judge：从战斗证据到结构化评分

- Prompt：`prompts/oracle_judge_agent.system.md`
- Schema：`schemas/judge_result.schema.json`
- Workflow 落点：`_judge()`
- SQL 含义：Judge 输出进入评分账本与聚合链，而不是直接覆盖向量表

这里有一个关键评审点：**prompt 里的 JSON 片段是示意，schema 才是最终示例输出的约束依据。**

因此 `examples/sample_judge_result.json` 是按 schema 风格包装的，而不是把 prompt 片段原样抄下来。

### 3.5 从 Judge 到向量发布，再到搜索 Pipeline

- SQL：`question_ability_scores -> assessment_ability_aggregates -> candidate_ability_contributions -> candidate_ability_snapshots -> candidate_vectors`
- 检索实现：`app/search_pipeline.py`
- RPC mock：`app/mock_rpc.py`
- Mock 数据来源：`app/mock_data.py`

也就是说：

1. Judge 先输出评分资产
2. SQL 负责把评分沉淀为可追溯的向量发布前置资产
3. 搜索 pipeline 最终消费的是稳定发布后的 `candidate_vectors`

这正是“报告资产、评分资产、召回资产分层”的落地体现。

## 4. 评委最值得追问的几个点

### 4.1 为什么 persisted lifecycle 只有 5 个状态？
因为这是 master spec 与 shared contracts 锁定的顶层生命周期。内部可以有运行态细分，但持久化顶层状态不能漂移。

### 4.2 为什么 examples 不直接照着 prompt 片段写？
因为 examples 要服从 schema。总装会话要做的是“按 authoritative contract 包装”，不是“按示意片段抄录”。

### 4.3 为什么 demo 只做 mock？
因为本次交付要证明的是：

- 架构链路是否合理
- 命名契约是否稳定
- 检索纪律是否落地
- 包装是否完整

而不是假装真实数据库、真实模型已经接通。

## 5. 建议评委实际动手的最短路径

```bash
bash run_demo.sh
```

然后再对照：

1. `examples/sample_hr_query.json`
2. `app/search_pipeline.py`
3. `docs/04_search_pipeline_notes.md`
4. `tests/test_search_pipeline.py`

这样能最快验证：

- 输入长什么样
- 代码怎么跑
- 设计为什么这么写
- 测试是否守住关键纪律
