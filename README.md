# L9 极客战役评测 + 分层混合检索（Mock 交付包）

> **重要声明**
>
> 这是一个 **mock-only implementation**。仓库中没有接通真实 PostgreSQL / pgvector、真实 Supabase RPC、真实 reranker、真实大模型推理链路。当前代码的目标是把 **架构约束、命名契约、状态机边界、样例数据与检索链路** 交付清楚，便于后续落地为真实系统，而不是伪装成“已经上线”。

## 1. 问题背景

这个仓库解决的是两个互相衔接的问题：

1. **C 端评测**：把候选人的简历、战役过程、追问证据、最终裁决拆成可审计的独立资产，而不是混成一个大对象。
2. **B 端检索**：把岗位查询转换成可检索的 requirement profile，然后在候选人向量资产上执行 **32 -> 128 -> 1024 -> sparse sidecar -> RRF -> rerank** 的分层混合召回。

目标不是做一个“会聊天的面试 bot”，而是做一个 **能追溯、能解释、能扩展为真实数据库实现** 的评测与检索骨架。

## 2. 识别出的 PRD 缺陷

本仓库没有照抄 PRD，而是先对 PRD 做了冲突审计。关键缺陷如下：

### 2.1 每次 IDE diff 都触发 X-RAG
这会把追问变成高频噪声源，直接把 WebSocket、Agent 调度和人机交互拖进请求风暴。修正后只允许在 **checkpoint、error_log、idle_timeout、test_state_change、contradiction** 等受治理事件上触发。

### 2.2 Oracle Judge 直接覆写 1024 维向量
这会破坏账本、版本、可回放能力。修正后必须走：

`question_ability_scores -> assessment_ability_aggregates -> candidate_ability_contributions -> candidate_ability_snapshots -> candidate_vectors`

也就是说，Judge 产生的是 **评分资产**，不是直接可检索向量。

### 2.3 把 candidate vector 塞进 candidates 主表
这会把基础资料、解释资产、召回资产耦合在一起。修正后向量发布资产独立到 `candidate_vectors`，并且和 ledger / snapshot 分层。

### 2.4 把检索理解成“dense + sparse 双轨即可”
这不够，也不稳。正确链路是：

`filter_gate -> vec32 -> vec128 -> vec1024 -> sparse_sidecar -> RRF -> rerank`

其中 sparse 只能补漏，不能主导最终排序。

### 2.5 在粗排阶段拉重 payload
如果在早期召回就取 report、battle_log、reranker_payload，大概率先炸内存和 RPC，再谈排序。修正后粗排阶段只拉 **轻量 id/score/少量展示字段**，重 payload 只能在 RRF shortlist 之后获取。

### 2.6 把 report、judge_result、vector publish 混成一个输出
这会破坏资产边界。修正后：

- `judge_result` 是 **评分资产**
- `geek_cert_report` 是 **展示资产**
- `candidate_vectors` 是 **召回资产**

三者必须分层。

## 3. 修正思路

整个仓库遵守三条主线：

1. **主规范优先**：先服从 `SESSION6_HANDOFF_MANIFEST.md`，再服从 `docs/00_master_execution_spec.md` 与 `docs/01_shared_contracts.md`。
2. **核心字段不漂移**：保持 snake_case，保持 `target_vec_32`、`score_rrf`、`final_score`、`trace_id`、`version` 等字段稳定。
3. **总装而非重设计**：Session 6 只做 README、导览文档、示例 JSON、mock demo 包装与目录树，不重写 prompts、schemas、SQL、pipeline。

## 4. 架构总览

### 4.1 C 端评测主链路

```text
resume / role_schema
  -> ingestion agent
  -> candidate_dna
  -> battlefield agent
  -> battlefield_blueprint
  -> combat events + governed xrag
  -> oracle judge
  -> judge_result
  -> ledger / aggregate / snapshot
  -> candidate_vectors
  -> geek_cert_report
```

### 4.2 B 端搜索主链路

```text
hr query
  -> query parser
  -> requirement_profile
  -> filter gate
  -> vec32 recall
  -> vec128 recall
  -> vec1024 recall
  -> sparse sidecar recall
  -> hand-written RRF
  -> payload fetch on shortlist only
  -> mock rerank
  -> final results
```

### 4.3 两条链路如何衔接

C 端评测不是为了生成一份漂亮报告，而是为了形成后续检索可消费的资产：

- Judge 产出 evidence-governed scoring
- SQL 设计把 scoring 沉淀为 ledger / aggregate / snapshot
- 向量发布后，B 端搜索只消费稳定的 `candidate_vectors` 与轻量 profile
- 报告仍然存在，但它是展示层，不反向支配召回层

## 5. 四个 Agent

### 5.1 Ingestion Agent
作用：把简历压缩成 role-scoped 的 `candidate_dna`。

关键边界：
- 只允许在 `allowed_ability_ids` 内提取信号
- 不做战役生成
- 不做最终评分
- 证据不足时降低置信度，而不是补脑

### 5.2 Battlefield Agent
作用：把 `candidate_dna` 和岗位范围渲染成高压战场 `battlefield_blueprint`。

关键边界：
- 生成可观察、可施压、可评测的 scenario
- 不出泛泛八股题
- 不越出 role scope

### 5.3 X-RAG Agent
作用：只在受治理事件发生时进行证据驱动追问或故障注入。

关键边界：
- 不监听每次 diff
- 不无限追问
- 必须受 debounce、suppression、max_injections 等规则约束

### 5.4 Oracle Judge Agent
作用：对允许能力范围内的表现做最终裁决，输出 `judge_result`。

关键边界：
- 只能评分 `allowed_ability_ids`
- 不允许 out-of-scope ability
- 只输出结构化结果，不输出鸡汤总结
- 产出的是评分资产，不直接覆写向量资产

## 6. 数据模型

SQL 主体放在 `sql/001_core_tables.sql`，核心思想是 **账本、快照、向量发布分离**。

### 6.1 关键表分层

- `assessments`：顶层评测生命周期，状态必须保持：
  - `PROVISIONING`
  - `COMBAT_ACTIVE`
  - `EVALUATING`
  - `CERTIFIED`
  - `FAILED`
- `assessment_question_instances` / `question_ability_bindings` / `question_ability_scores`：问题与能力评分账本
- `assessment_ability_aggregates`：单次评测内能力聚合
- `candidate_ability_contributions`：可版本化的贡献账本
- `candidate_ability_snapshots`：可重算快照
- `candidate_vectors`：最终检索消费的三层向量发布资产
- `job_requirement_profiles` / `search_sessions`：B 端检索输入与会话落点

### 6.2 三层向量字段

必须保持以下稳定字段名：

- `target_vec_32`
- `target_vec_128`
- `target_vec_1024`
- `ability_vec_32`
- `ability_vec_128`
- `ability_vec_1024`

### 6.3 评分字段

必须保持以下稳定字段名：

- `score_32`
- `score_128`
- `score_1024`
- `score_sparse`
- `score_rrf`
- `score_rerank`
- `final_score`

## 7. 搜索链路说明

`app/search_pipeline.py` 是本交付包里最重要的 B 端 mock 实现。

### 7.1 输入风格
输入本质上是：

```json
{
  "query_text": "需要一个能在高并发下处理 Redis 分布式锁和死锁的 Golang 后端",
  "filters": {
    "city": "上海",
    "remote_policy": "onsite",
    "min_years_experience": 3
  },
  "top_k": 3,
  "rerank_top_n": 8,
  "trace_id": "trace_demo_search",
  "version": "session5.mock.v1"
}
```

### 7.2 执行顺序

1. `parse_hr_query()` 归一化 query，并抽出 `must_have_abilities`、`nice_to_have_abilities`、`ability_weights`
2. 构造 `target_vec_32 / 128 / 1024`
3. 先做 filter gate
4. 再做三层 dense recall
5. 再做 sparse sidecar 补漏
6. 手写 RRF 融合
7. **只对 shortlist** 拉 `reranker_payload`
8. 用 mock rerank 产出 `final_score`

### 7.3 为什么 sparse 只是 sidecar
因为 `verified_skills` 是文本资产，适合作为：
- 展示标签
- 稀疏补漏
- rerank 证据

但不该成为内部主轴。真正的召回主轴是分层向量资产。

## 8. 目录结构

```text
.
├── README.md
├── SESSION6_HANDOFF_MANIFEST.md
├── app/
├── docs/
├── examples/
├── prompts/
├── run_demo.sh
├── schemas/
├── sql/
├── tests/
├── tree.txt
└── workflow/
```

更详细的目录导览见 `docs/05_repo_walkthrough.md`。

## 9. 如何运行 mock demo

### 9.1 直接运行

```bash
bash run_demo.sh
```

### 9.2 指定输入 JSON

```bash
bash run_demo.sh examples/sample_hr_query.json
```

### 9.3 你会得到什么

脚本会：

1. 读取 `examples/sample_hr_query.json`
2. 用固定 seed 构造 mock candidate repository
3. 调用 `app/search_pipeline.py` 中的 `run_search_pipeline()`
4. 将最终 JSON 结果打印到 stdout

### 9.4 再强调一次

这只是 **mock demo**，不是：

- 真实数据库查询
- 真实 pgvector HNSW 检索
- 真实 Supabase RPC
- 真实 cross-encoder reranker
- 真实线上候选人数据

## 10. 示例文件说明

- `examples/sample_hr_query.json`：演示搜索输入
- `examples/sample_judge_result.json`：演示 Judge 结构化输出
- `examples/sample_geek_cert_report.json`：演示报告展示资产

注意：示例 JSON 以 **`schemas/*.json` 为准**，而不是按 prompt 中较松散的示意片段去“脑补字段”。

这点尤其重要，因为 prompt 文本与最终 schema 在少数字段上存在精细度差异；打包示例必须服从 authoritative schema，而不能把 prompt 示意当成最终契约。

## 11. 为什么这不是照抄 PRD

如果只是照抄 PRD，通常会出现这些问题：

- 把 X-RAG 绑定到每次 diff
- 让 Judge 直接改向量
- 让报告、评分、召回资产混成一个对象
- 让 sparse recall 直接主导排序
- 在粗排阶段拉重 payload
- 字段名和状态机到处漂移

本仓库之所以体现的是 **架构判断** 而不是 PRD 复述，原因在于它做了下面这些纠偏：

1. 用 authoritative manifest 锁优先级，不让后续会话随意漂移
2. 用 shared contracts 锁字段名，不让 JSON / SQL / Python 三套命名分叉
3. 用 SQL 把 ledger、snapshot、vector publish 分层
4. 用 workflow 把四个 Agent 的边界和熔断机制写清楚
5. 用 search pipeline 把 layered recall、RRF、delayed payload fetch 落成 mock 代码
6. 用示例文件把 schema 风格、演示输入、报告资产分开包装

## 12. 已知非目标

当前交付 **不包含**：

- 真实在线数据库迁移与部署
- 真实模型服务接入
- 真实 prompt routing 框架
- 真实审计后台与前端页面
- 不存在的 `prompt_output_contracts.json`

最后一条需要明确说明：`prompt_output_contracts.json` **并未恢复**，因此本交付不会伪造对它的引用。
