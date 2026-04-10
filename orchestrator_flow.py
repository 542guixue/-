from __future__ import annotations

"""
Python-style pseudocode for the four-agent orchestration layer.

Goals:
- explicit state machine
- no hard-coded candidate facts
- circuit breaker + cooldown + contract validation
- shared trace_id across ingestion -> battlefield -> x_rag -> judge -> report
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time
import uuid


class Stage(str, Enum):
    PROVISIONING = "PROVISIONING"
    INGESTING = "INGESTING"
    BATTLEFIELD_RENDERING = "BATTLEFIELD_RENDERING"
    COMBAT_ACTIVE = "COMBAT_ACTIVE"
    XRAG_MONITORING = "XRAG_MONITORING"
    EVALUATING = "EVALUATING"
    CERTIFIED = "CERTIFIED"
    FAILED = "FAILED"


class ErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    DNA_EXTRACTION_FAILED = "dna_extraction_failed"
    BLUEPRINT_GENERATION_FAILED = "blueprint_generation_failed"
    XRAG_TRIGGER_REJECTED = "xrag_trigger_rejected"
    XRAG_RATE_LIMITED = "xrag_rate_limited"
    JUDGE_OUTPUT_INVALID = "judge_output_invalid"
    JUDGE_EVIDENCE_INSUFFICIENT = "judge_evidence_insufficient"
    INTERNAL_CONTRACT_VIOLATION = "internal_contract_violation"
    REPORT_BUILD_FAILED = "report_build_failed"


@dataclass
class StructuredError(Exception):
    error_code: str
    error_message: str
    error_stage: str
    is_retryable: bool
    retry_after_seconds: int
    trace_id: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeContext:
    candidate_id: str
    assessment_id: str
    role_schema_id: str
    trace_id: str
    version: str
    stage: Stage = Stage.PROVISIONING
    artifacts: Dict[str, Any] = field(default_factory=dict)
    retry_budget: Dict[str, int] = field(default_factory=lambda: {
        "ingestion": 1,
        "battlefield": 1,
        "judge": 1,
    })
    cooldown_registry: Dict[str, float] = field(default_factory=dict)
    breaker_counts: Dict[str, int] = field(default_factory=lambda: {
        "contract_validation": 0,
        "xrag": 0,
        "judge": 0,
    })
    audit_log: List[Dict[str, Any]] = field(default_factory=list)


class ContractValidator:
    REQUIRED_FIELDS = {
        "ingestion": ["candidate_id", "role_schema_id", "mode", "candidate_dna", "evidence_refs", "confidence", "trace_id", "version"],
        "battlefield": ["candidate_id", "role_schema_id", "mode", "battlefield_blueprint", "failure_conditions", "observation_points", "injection_slots", "time_budget_minutes", "trace_id", "version"],
        "xrag": ["candidate_id", "assessment_id", "trigger_reason", "trigger_source", "severity", "checkpoint_id", "injection_plan", "followup_question", "cooldown_seconds", "trace_id", "version"],
        "judge": ["candidate_id", "assessment_id", "allowed_ability_ids", "judge_result", "trace_id", "version"],
    }

    @classmethod
    def validate(cls, stage_key: str, payload: Dict[str, Any], trace_id: str) -> None:
        missing = [key for key in cls.REQUIRED_FIELDS[stage_key] if key not in payload]
        if missing:
            raise StructuredError(
                error_code=ErrorCode.MISSING_REQUIRED_FIELD.value,
                error_message=f"missing required fields: {missing}",
                error_stage=stage_key,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=trace_id,
                details={"missing_fields": missing},
            )

        invalid_keys = [key for key in payload.keys() if key.lower() != key or "-" in key]
        if invalid_keys:
            raise StructuredError(
                error_code=ErrorCode.SCHEMA_VALIDATION_FAILED.value,
                error_message="invalid snake_case keys detected",
                error_stage=stage_key,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=trace_id,
                details={"invalid_keys": invalid_keys},
            )

        if payload.get("trace_id") != trace_id:
            raise StructuredError(
                error_code=ErrorCode.INTERNAL_CONTRACT_VIOLATION.value,
                error_message="trace_id drift detected",
                error_stage=stage_key,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=trace_id,
                details={"payload_trace_id": payload.get("trace_id")},
            )


class CircuitBreaker:
    THRESHOLDS = {
        "contract_validation": 2,
        "xrag": 4,
        "judge": 2,
    }

    @classmethod
    def hit(cls, ctx: RuntimeContext, domain: str, reason: str) -> None:
        ctx.breaker_counts[domain] += 1
        ctx.audit_log.append({
            "event": "breaker_hit",
            "domain": domain,
            "reason": reason,
            "count": ctx.breaker_counts[domain],
            "trace_id": ctx.trace_id,
        })
        if ctx.breaker_counts[domain] >= cls.THRESHOLDS[domain]:
            raise StructuredError(
                error_code=ErrorCode.INTERNAL_CONTRACT_VIOLATION.value,
                error_message=f"circuit open: {domain}",
                error_stage=ctx.stage.value,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=ctx.trace_id,
                details={"domain": domain, "reason": reason},
            )


class AgentRuntime:
    def __init__(
        self,
        ingestion_agent: Callable[[Dict[str, Any]], Dict[str, Any]],
        battlefield_agent: Callable[[Dict[str, Any]], Dict[str, Any]],
        xrag_agent: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
        judge_agent: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self.ingestion_agent = ingestion_agent
        self.battlefield_agent = battlefield_agent
        self.xrag_agent = xrag_agent
        self.judge_agent = judge_agent

    def run(self, resume_blob: str, role_schema: Dict[str, Any], battle_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        ctx = RuntimeContext(
            candidate_id=f"cand_{uuid.uuid4().hex[:12]}",
            assessment_id=f"asm_{uuid.uuid4().hex[:12]}",
            role_schema_id=role_schema["role_schema_id"],
            trace_id=f"trace_{uuid.uuid4().hex}",
            version="session.v2",
        )

        try:
            self._provision(ctx, role_schema)
            self._ingest(ctx, resume_blob, role_schema)
            self._render_battlefield(ctx, role_schema)
            self._execute_battle(ctx, battle_events)
            self._judge(ctx, role_schema)
            return self._build_report(ctx, role_schema)
        except StructuredError as exc:
            ctx.stage = Stage.FAILED
            return {
                "error_code": exc.error_code,
                "error_message": exc.error_message,
                "error_stage": exc.error_stage,
                "is_retryable": exc.is_retryable,
                "retry_after_seconds": exc.retry_after_seconds,
                "trace_id": exc.trace_id,
                "details": exc.details,
            }

    def _provision(self, ctx: RuntimeContext, role_schema: Dict[str, Any]) -> None:
        ctx.stage = Stage.PROVISIONING
        if not role_schema.get("allowed_ability_ids"):
            raise StructuredError(
                error_code=ErrorCode.INVALID_INPUT.value,
                error_message="allowed_ability_ids is empty",
                error_stage=ctx.stage.value,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=ctx.trace_id,
            )
        ctx.audit_log.append({"event": "provisioned", "trace_id": ctx.trace_id})

    def _ingest(self, ctx: RuntimeContext, resume_blob: str, role_schema: Dict[str, Any]) -> None:
        ctx.stage = Stage.INGESTING
        payload = {
            "candidate_id": ctx.candidate_id,
            "role_schema_id": ctx.role_schema_id,
            "trace_id": ctx.trace_id,
            "version": "ingestion.v2",
            "resume_blob": resume_blob,
            "role_schema": role_schema,
        }
        result = self._retry_once("ingestion", ctx, lambda: self.ingestion_agent(payload))
        self._validate_and_store(ctx, "ingestion", result, "candidate_dna_payload")

    def _render_battlefield(self, ctx: RuntimeContext, role_schema: Dict[str, Any]) -> None:
        ctx.stage = Stage.BATTLEFIELD_RENDERING
        payload = {
            "candidate_id": ctx.candidate_id,
            "role_schema_id": ctx.role_schema_id,
            "trace_id": ctx.trace_id,
            "version": "battlefield.v2",
            "candidate_dna": ctx.artifacts["candidate_dna_payload"]["candidate_dna"],
            "allowed_ability_ids": role_schema["allowed_ability_ids"],
        }
        result = self._retry_once("battlefield", ctx, lambda: self.battlefield_agent(payload))
        self._validate_and_store(ctx, "battlefield", result, "battlefield_payload")

    def _execute_battle(self, ctx: RuntimeContext, battle_events: List[Dict[str, Any]]) -> None:
        ctx.stage = Stage.COMBAT_ACTIVE
        ctx.artifacts["battle_log"] = []
        observed_checkpoints = set()

        for event in battle_events:
            checkpoint_id = event["checkpoint_id"]
            ctx.artifacts["battle_log"].append(event)
            observed_checkpoints.add(checkpoint_id)

            ctx.stage = Stage.XRAG_MONITORING
            xrag_result = self._maybe_trigger_xrag(ctx, event)
            if xrag_result:
                self._validate_and_store(ctx, "xrag", xrag_result, f"xrag::{checkpoint_id}")

            ctx.stage = Stage.COMBAT_ACTIVE

        if not observed_checkpoints:
            raise StructuredError(
                error_code=ErrorCode.JUDGE_EVIDENCE_INSUFFICIENT.value,
                error_message="empty battle_log",
                error_stage=ctx.stage.value,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=ctx.trace_id,
            )

    def _judge(self, ctx: RuntimeContext, role_schema: Dict[str, Any]) -> None:
        ctx.stage = Stage.EVALUATING
        payload = {
            "candidate_id": ctx.candidate_id,
            "assessment_id": ctx.assessment_id,
            "trace_id": ctx.trace_id,
            "version": "judge.v2",
            "allowed_ability_ids": role_schema["allowed_ability_ids"],
            "battle_log": ctx.artifacts["battle_log"],
            "candidate_dna": ctx.artifacts["candidate_dna_payload"]["candidate_dna"],
            "xrag_findings": [v for k, v in ctx.artifacts.items() if str(k).startswith("xrag::")],
        }
        result = self._retry_once("judge", ctx, lambda: self.judge_agent(payload))
        self._validate_and_store(ctx, "judge", result, "judge_payload")

        out_of_scope = [
            item["ability_id"]
            for item in result["judge_result"].get("vector_updates", [])
            if item["ability_id"] not in set(role_schema["allowed_ability_ids"])
        ]
        if out_of_scope:
            CircuitBreaker.hit(ctx, "judge", "judge_out_of_scope_ability")
            raise StructuredError(
                error_code="judge_out_of_scope_ability",
                error_message="judge emitted ability outside role schema",
                error_stage=ctx.stage.value,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=ctx.trace_id,
                details={"out_of_scope_ability_ids": out_of_scope},
            )

    def _build_report(self, ctx: RuntimeContext, role_schema: Dict[str, Any]) -> Dict[str, Any]:
        try:
            ctx.stage = Stage.CERTIFIED
            judge_payload = ctx.artifacts["judge_payload"]
            report = {
                "report_id": f"rpt_{uuid.uuid4().hex[:12]}",
                "candidate": {
                    "candidate_id": ctx.candidate_id,
                    "role_schema_id": ctx.role_schema_id,
                },
                "assessment": {
                    "assessment_id": ctx.assessment_id,
                    "status": ctx.stage.value,
                },
                "combat_summary": {
                    "observed_checkpoints": len(ctx.artifacts["battle_log"]),
                    "xrag_trigger_count": len([k for k in ctx.artifacts if str(k).startswith("xrag::")]),
                },
                "verified_skills": judge_payload["judge_result"]["verified_skills"],
                "vector_signature": judge_payload["judge_result"]["vector_signature"],
                "anti_forgery": {
                    "trace_id": ctx.trace_id,
                    "judge_digest": judge_payload["judge_result"]["vector_signature"]["digest_placeholder"],
                    "grader_version": judge_payload["version"],
                    "vec_version": role_schema["vec_version"],
                    "prompt_version": role_schema["prompt_version"],
                },
                "trace_id": ctx.trace_id,
                "schema_version": "geek_cert_report.v1",
                "created_at": int(time.time()),
            }
            return report
        except Exception as exc:  # pragma: no cover - pseudocode path
            raise StructuredError(
                error_code=ErrorCode.REPORT_BUILD_FAILED.value,
                error_message=str(exc),
                error_stage=ctx.stage.value,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=ctx.trace_id,
            )

    def _maybe_trigger_xrag(self, ctx: RuntimeContext, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        checkpoint_id = event["checkpoint_id"]
        now = time.time()
        cooldown_until = ctx.cooldown_registry.get(checkpoint_id, 0.0)

        if now < cooldown_until:
            return None

        result = self.xrag_agent({
            "candidate_id": ctx.candidate_id,
            "assessment_id": ctx.assessment_id,
            "trace_id": ctx.trace_id,
            "version": "xrag.v2",
            "event": event,
        })

        if result is None:
            return None

        if not result.get("trigger_source", {}).get("evidence_snippets"):
            CircuitBreaker.hit(ctx, "xrag", "trigger_without_evidence")
            raise StructuredError(
                error_code=ErrorCode.XRAG_TRIGGER_REJECTED.value,
                error_message="xrag trigger rejected due to missing evidence",
                error_stage=ctx.stage.value,
                is_retryable=False,
                retry_after_seconds=0,
                trace_id=ctx.trace_id,
                details={"checkpoint_id": checkpoint_id},
            )

        cooldown_seconds = int(result.get("cooldown_seconds", 0))
        ctx.cooldown_registry[checkpoint_id] = now + cooldown_seconds
        return result

    def _validate_and_store(self, ctx: RuntimeContext, stage_key: str, payload: Dict[str, Any], artifact_key: str) -> None:
        try:
            ContractValidator.validate(stage_key, payload, ctx.trace_id)
            ctx.artifacts[artifact_key] = payload
        except StructuredError as exc:
            CircuitBreaker.hit(ctx, "contract_validation", exc.error_message)
            raise

    def _retry_once(self, stage_name: str, ctx: RuntimeContext, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return fn()
        except Exception as exc:
            if ctx.retry_budget.get(stage_name, 0) <= 0:
                raise StructuredError(
                    error_code=ErrorCode.INTERNAL_CONTRACT_VIOLATION.value,
                    error_message=f"{stage_name} exhausted retry budget: {exc}",
                    error_stage=ctx.stage.value,
                    is_retryable=False,
                    retry_after_seconds=0,
                    trace_id=ctx.trace_id,
                )
            ctx.retry_budget[stage_name] -= 1
            ctx.audit_log.append({
                "event": "retry",
                "stage_name": stage_name,
                "remaining": ctx.retry_budget[stage_name],
                "trace_id": ctx.trace_id,
            })
            return fn()
