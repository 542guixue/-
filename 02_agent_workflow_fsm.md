# 工作流编排、状态机与熔断设计

## 先判死刑的 PRD 缺陷

1. **每次 diff 触发 X-RAG**  
   必死。会把 WebSocket、LLM 调度和人机交互一起拖入请求风暴。必须改为 checkpoint / error_log / idle_timeout / test_state_change 触发。
2. **直接覆写 candidate vector**  
   必死。会丢来源、版本、回放能力。必须改为 contribution versioning -> snapshot recompute -> vector publish。
3. **1024 维做全库第一层召回**  
   必死。高维稀疏 + 大盘召回会把 latency 和 recall 精度一起打爆。必须先 32、再 128、最后 1024。
4. **粗排阶段拉 report / reranker_payload / battle_log**  
   必死。网络和内存先炸，再谈排序。粗排只许轻量字段。
5. **把 verified_skills 当内部主轴**  
   必死。文本标签只允许当展示资产、稀疏补漏资产、rerank 证据资产。

## C 端战役 FSM

```python
from enum import Enum

class CombatState(str, Enum):
    PROVISIONING = "PROVISIONING"
    COMBAT_ACTIVE = "COMBAT_ACTIVE"
    EVALUATING = "EVALUATING"
    CERTIFIED = "CERTIFIED"
    FAILED = "FAILED"
```

### 状态迁移

- `PROVISIONING`
  - 输入：resume_text, role_schema_id, mode
  - 动作：ingestion -> battlefield -> runtime_policy init
  - 成功：进入 `COMBAT_ACTIVE`
  - 失败：fallback_blueprint 仍失败则 `FAILED`

- `COMBAT_ACTIVE`
  - 输入：battle events, checkpoints, test_state, error_log
  - 动作：采集 `battle_log`，按节流规则触发 X-RAG
  - 成功：战役结束进入 `EVALUATING`
  - 失败：不可恢复运行时异常进入 `FAILED`

- `EVALUATING`
  - 输入：role_schema, battle_log, evidence_slices
  - 动作：judge -> schema validate -> ledger write -> snapshot recompute -> vector publish -> report build
  - 成功：进入 `CERTIFIED`
  - 失败：失败可重试的在本状态重试一次；仍失败进入 `FAILED`

- `CERTIFIED`
  - 所有资产可检索、可审计、可渲染

- `FAILED`
  - 输出结构化错误对象
  - 指明 `error_stage`、`is_retryable`、`retry_after_seconds`

## X-RAG 熔断器

```python
from dataclasses import dataclass, field
from time import time

@dataclass
class XragCircuitBreaker:
    max_concurrent_injections: int = 1
    debounce_seconds: int = 45
    same_topic_suppression_seconds: int = 120
    max_injections_per_combat: int = 6

    active_injections: int = 0
    total_injections: int = 0
    last_trigger_ts: float = 0.0
    last_topic_ts: dict[str, float] = field(default_factory=dict)

    def can_fire(self, trigger_source: str, topic: str, now_ts: float | None = None) -> tuple[bool, str]:
        now_ts = now_ts or time()
        if trigger_source not in {
            "checkpoint",
            "error_log",
            "idle_timeout",
            "test_state_change",
            "contradiction_detected",
            "unresolved_previous_injection",
        }:
            return False, "xrag_trigger_rejected"
        if self.active_injections >= self.max_concurrent_injections:
            return False, "xrag_rate_limited"
        if self.total_injections >= self.max_injections_per_combat:
            return False, "xrag_rate_limited"
        if now_ts - self.last_trigger_ts < self.debounce_seconds:
            return False, "xrag_rate_limited"
        if topic in self.last_topic_ts and now_ts - self.last_topic_ts[topic] < self.same_topic_suppression_seconds:
            return False, "xrag_rate_limited"
        return True, "ok"

    def on_fire(self, topic: str, now_ts: float | None = None) -> None:
        now_ts = now_ts or time()
        self.active_injections += 1
        self.total_injections += 1
        self.last_trigger_ts = now_ts
        self.last_topic_ts[topic] = now_ts

    def on_resolve(self) -> None:
        self.active_injections = max(0, self.active_injections - 1)
```

## Python 伪代码：主编排器

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class RuntimeContext:
    trace_id: str
    version: str
    schema_version: str
    prompt_versions: dict[str, str]
    grader_version: str
    vec_version: str
    blueprint_version: str
    state: str = "PROVISIONING"

class ContractViolation(Exception): ...
class RetryableStageError(Exception):
    def __init__(self, error_code: str, retry_after_seconds: int = 0):
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(error_code)

class FatalStageError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


def run_assessment(resume_text: str, role_schema: dict[str, Any], mode: str) -> dict[str, Any]:
    ctx = RuntimeContext(
        trace_id=gen_trace_id(),
        version="assessment.v1",
        schema_version="1.0.0",
        prompt_versions={
            "ingestion": "ingestion.v1",
            "battlefield": "battlefield.v1",
            "xrag": "xrag.v1",
            "oracle_judge": "oracle_judge.v1",
        },
        grader_version="judge.v1",
        vec_version="vec.publish.v1",
        blueprint_version="blueprint.v2",
    )
    breaker = XragCircuitBreaker()

    try:
        # --- PROVISIONING ---
        candidate = mock_candidate_identity()
        dna = call_ingestion_agent(
            candidate_id=candidate["candidate_id"],
            role_schema=role_schema,
            resume_text=resume_text,
            mode=mode,
            trace_id=ctx.trace_id,
            version=ctx.prompt_versions["ingestion"],
        )
        validate_candidate_dna(dna)

        try:
            blueprint = call_battlefield_agent(
                candidate_dna=dna["candidate_dna"],
                role_schema=role_schema,
                mode=mode,
                trace_id=ctx.trace_id,
                version=ctx.prompt_versions["battlefield"],
            )
            validate_battlefield_blueprint(blueprint)
        except Exception:
            blueprint = build_fallback_blueprint(candidate, role_schema, mode, ctx)
            blueprint["is_fallback"] = True

        ctx.state = "COMBAT_ACTIVE"

        # --- COMBAT_ACTIVE ---
        battle_log: list[dict[str, Any]] = []
        for event in stream_mock_combat_events(blueprint):
            battle_log.append(event)
            decision = maybe_trigger_xrag(event, battle_log, breaker, ctx, role_schema)
            if decision["trigger_source"] != "no_op":
                battle_log.append({"event_type": "xrag_injection", "payload": decision})

        ctx.state = "EVALUATING"

        # --- EVALUATING ---
        judge_response = call_oracle_judge(
            role_schema=role_schema,
            allowed_ability_ids=role_schema["allowed_ability_ids"],
            battle_log=battle_log,
            trace_id=ctx.trace_id,
            version=ctx.prompt_versions["oracle_judge"],
        )
        try:
            validate_judge_result(judge_response)
        except ContractViolation:
            judge_response = retry_oracle_judge_once(...)
            validate_judge_result(judge_response)

        ledger_bundle = write_ledger_bundle(candidate, role_schema, blueprint, battle_log, judge_response, ctx)
        snapshot = recompute_candidate_snapshots(candidate["candidate_id"], ledger_bundle, ctx)
        vectors = publish_candidate_vectors(candidate["candidate_id"], snapshot, role_schema, ctx)
        report = build_geek_cert_report(candidate, role_schema, blueprint, judge_response, vectors, battle_log, ctx)

        ctx.state = "CERTIFIED"
        return {
            "status": ctx.state,
            "trace_id": ctx.trace_id,
            "candidate_id": candidate["candidate_id"],
            "judge_result": judge_response,
            "candidate_vectors": vectors,
            "geek_cert_report": report,
        }

    except RetryableStageError as exc:
        ctx.state = "FAILED"
        return structured_error(
            error_code=exc.error_code,
            error_message="retryable stage failure",
            error_stage=ctx.state,
            is_retryable=True,
            retry_after_seconds=exc.retry_after_seconds,
            trace_id=ctx.trace_id,
        )
    except FatalStageError as exc:
        ctx.state = "FAILED"
        return structured_error(
            error_code=exc.error_code,
            error_message="fatal stage failure",
            error_stage=ctx.state,
            is_retryable=False,
            retry_after_seconds=0,
            trace_id=ctx.trace_id,
        )
```

## B 端检索状态机

```python
from enum import Enum

class SearchState(str, Enum):
    CREATED = "CREATED"
    FILTERED = "FILTERED"
    RECALLING = "RECALLING"
    FUSED = "FUSED"
    RERANKED = "RERANKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
```

## 极客认证报告 JSON 结构说明

- `candidate`: 对外展示的基础身份卡片
- `role`: 岗位与 schema context
- `assessment`: 战役元信息
- `combat_summary`: 高压战役摘要
- `radar_metrics`: 前端雷达图多维值
- `verified_skills`: 仅展示与稀疏补漏
- `vector_signature`: 三层向量发布摘要，不暴露全量向量
- `anti_forgery`: 防伪确权块
- `evidence_slices`: 证据切片
- `risk_flags`: 风险提示
- `final_recommendation`: 最终建议

## Mock 约束

- 不硬编码最终 top candidate
- mock requirement profile 必须带三层目标向量
- mock battle_log 必须可映射到 judge_result
- mock candidate 集合必须结构化，可过滤、可召回、可 rerank
