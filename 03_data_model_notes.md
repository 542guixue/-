# 架构审计结论

## 必须推翻的逻辑矛盾

### 1. 原 PRD 让 X-RAG 监听 IDE diff 直接追问
这和主规范冲突。
主规范已经把合法触发源锁成 checkpoint、error_log、idle_timeout、test_state_change、contradiction_detected。
因此实现上必须以事件驱动替代高频 diff 驱动。

### 2. 原 PRD 让 Oracle Judge 直接覆写 1024 向量
这和事件账本原则冲突。
正确路径必须是：
`question_ability_scores -> assessment_ability_aggregates -> candidate_ability_contributions -> candidate_ability_snapshots -> candidate_vectors`

### 3. 原 PRD 倾向把 capability_vector 放在 candidates 主表
这只适合兼容期。
新主路径必须切到独立 `candidate_vectors` 表，避免把召回资产与基础信息、解释资产混在一起。

### 4. 原检索描述是双轨召回
这不够。
必须上四段路由：
- Filter Gate
- L1 32 维
- L2 128 维
- L3 1024 维
- Sparse sidecar
- RRF
- Rerank

### 5. 报告与 judge_result 不能复用
报告是展示资产。
judge_result 是评分资产。
vector publish 是召回资产。
三者分层，否则审计链条会坏。

## 评审时最容易被追杀的点

- 输出字段如果不是 snake_case，直接扣分
- JSON 前后有废话，直接扣分
- 用 skills 文本替代 ability_id，直接扣分
- 让 sparse recall 主导排序，直接扣分
- 在 RRF 阶段用大模型，直接扣分
- 粗排阶段拉重 payload，直接扣分
