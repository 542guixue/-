from __future__ import annotations

"""Programmatic mock data for the layered hybrid search pipeline.

The mock dataset intentionally follows the naming style from:
- docs/00_master_execution_spec.md
- docs/01_shared_contracts.md
- schemas/judge_result.schema.json
- schemas/geek_cert_report.schema.json
- sql/001_core_tables.sql

No real database is used. This module only generates in-memory structures that
look like the assets the search pipeline would consume after vector publish.
"""

from dataclasses import dataclass
import math
import random
from typing import Any, Sequence

ASSESSMENT_LIFECYCLE_STATES: tuple[str, ...] = (
    "PROVISIONING",
    "COMBAT_ACTIVE",
    "EVALUATING",
    "CERTIFIED",
    "FAILED",
)

DEFAULT_TRACE_ID = "trace_mock_search"
DEFAULT_VERSION = "session5.mock.v1"
DEFAULT_VEC_VERSION = "vec.publish.v1"

VECTOR_DIM_32 = 32
VECTOR_DIM_128 = 128
VECTOR_DIM_1024 = 1024


@dataclass(frozen=True)
class SpecialAbilitySpec:
    ability_id: str
    ability_code: str
    ability_name: str
    vector_index: int
    family_index: int
    macro_index: int
    aliases: tuple[str, ...]
    verified_skill_label: str
    is_hard_skill: bool
    default_weight: float


SPECIAL_ABILITY_SPECS: tuple[SpecialAbilitySpec, ...] = (
    SpecialAbilitySpec("ability_0001", "backend_engineering", "Backend Engineering", 0, 0, 0, ("backend", "后端"), "Backend", False, 0.75),
    SpecialAbilitySpec("ability_0002", "golang", "Golang", 1, 1, 0, ("golang", "go"), "Golang", True, 1.00),
    SpecialAbilitySpec("ability_0003", "redis", "Redis", 2, 2, 0, ("redis",), "Redis", True, 1.00),
    SpecialAbilitySpec("ability_0004", "distributed_locking", "Distributed Locking", 3, 3, 0, ("distributed locking", "distributed lock", "分布式锁"), "Distributed Locking", True, 1.00),
    SpecialAbilitySpec("ability_0005", "deadlock_debugging", "Deadlock Debugging", 4, 3, 0, ("deadlock", "死锁"), "Deadlock Debugging", False, 0.90),
    SpecialAbilitySpec("ability_0006", "high_concurrency", "High Concurrency", 5, 0, 0, ("high concurrency", "concurrency", "高并发", "并发"), "High Concurrency", False, 0.95),
    SpecialAbilitySpec("ability_0007", "microservices", "Microservices", 6, 1, 0, ("microservice", "microservices", "微服务"), "Microservices", False, 0.70),
    SpecialAbilitySpec("ability_0008", "incident_response", "Incident Response", 7, 0, 0, ("incident", "incident response", "故障", "应急"), "Incident Response", False, 0.70),
    SpecialAbilitySpec("ability_0009", "postgresql", "PostgreSQL", 8, 2, 0, ("postgresql", "postgres", "pg"), "PostgreSQL", True, 0.85),
    SpecialAbilitySpec("ability_0010", "kubernetes", "Kubernetes", 9, 4, 1, ("kubernetes", "k8s"), "Kubernetes", True, 0.80),
    SpecialAbilitySpec("ability_0011", "python", "Python", 10, 5, 1, ("python",), "Python", True, 0.85),
    SpecialAbilitySpec("ability_0012", "machine_learning", "Machine Learning", 11, 6, 1, ("machine learning", "ml", "机器学习"), "Machine Learning", False, 0.80),
    SpecialAbilitySpec("ability_0013", "llm_systems", "LLM Systems", 12, 6, 1, ("llm", "大模型"), "LLM Systems", False, 0.85),
    SpecialAbilitySpec("ability_0014", "feature_engineering", "Feature Engineering", 13, 5, 1, ("feature engineering", "特征工程"), "Feature Engineering", False, 0.60),
    SpecialAbilitySpec("ability_0015", "frontend_engineering", "Frontend Engineering", 14, 8, 2, ("frontend", "前端"), "Frontend", False, 0.75),
    SpecialAbilitySpec("ability_0016", "react", "React", 15, 8, 2, ("react",), "React", True, 0.85),
    SpecialAbilitySpec("ability_0017", "typescript", "TypeScript", 16, 8, 2, ("typescript", "ts"), "TypeScript", True, 0.80),
    SpecialAbilitySpec("ability_0018", "system_design", "System Design", 17, 9, 2, ("system design", "architecture", "架构"), "System Design", False, 0.90),
    SpecialAbilitySpec("ability_0019", "product_prd", "Product PRD", 18, 10, 2, ("prd", "产品"), "Product PRD", False, 0.60),
    SpecialAbilitySpec("ability_0020", "observability", "Observability", 19, 4, 1, ("observability", "监控"), "Observability", False, 0.65),
    SpecialAbilitySpec("ability_0021", "java", "Java", 20, 11, 2, ("java",), "Java", True, 0.75),
    SpecialAbilitySpec("ability_0022", "stream_processing", "Stream Processing", 21, 12, 3, ("stream", "kafka", "流处理"), "Stream Processing", False, 0.75),
    SpecialAbilitySpec("ability_0023", "data_engineering", "Data Engineering", 22, 12, 3, ("data engineering", "数据工程"), "Data Engineering", False, 0.75),
    SpecialAbilitySpec("ability_0024", "qa_automation", "QA Automation", 23, 13, 3, ("qa", "automation testing", "测试"), "QA Automation", False, 0.55),
)

SPECIAL_ABILITY_BY_ID: dict[str, SpecialAbilitySpec] = {spec.ability_id: spec for spec in SPECIAL_ABILITY_SPECS}
ALIAS_TO_ABILITY_IDS: dict[str, list[str]] = {}
for _spec in SPECIAL_ABILITY_SPECS:
    for _alias in _spec.aliases:
        ALIAS_TO_ABILITY_IDS.setdefault(_alias.lower(), []).append(_spec.ability_id)

ARCHETYPE_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "archetype_code": "go_redis_backend",
        "display_name_prefix": "GoRedis",
        "ability_ids": [
            "ability_0001",
            "ability_0002",
            "ability_0003",
            "ability_0004",
            "ability_0005",
            "ability_0006",
            "ability_0007",
            "ability_0008",
            "ability_0009",
            "ability_0018",
        ],
        "search_keywords": ["backend", "golang", "redis", "distributed locking", "deadlock"],
    },
    {
        "archetype_code": "platform_sre",
        "display_name_prefix": "Platform",
        "ability_ids": [
            "ability_0001",
            "ability_0006",
            "ability_0008",
            "ability_0009",
            "ability_0010",
            "ability_0018",
            "ability_0020",
            "ability_0022",
        ],
        "search_keywords": ["platform", "incident", "kubernetes", "postgresql"],
    },
    {
        "archetype_code": "python_ml",
        "display_name_prefix": "PyML",
        "ability_ids": [
            "ability_0011",
            "ability_0012",
            "ability_0013",
            "ability_0014",
            "ability_0018",
            "ability_0023",
        ],
        "search_keywords": ["python", "ml", "llm", "feature engineering"],
    },
    {
        "archetype_code": "frontend_fullstack",
        "display_name_prefix": "Frontend",
        "ability_ids": [
            "ability_0015",
            "ability_0016",
            "ability_0017",
            "ability_0018",
            "ability_0019",
            "ability_0024",
        ],
        "search_keywords": ["frontend", "react", "typescript"],
    },
    {
        "archetype_code": "java_streaming",
        "display_name_prefix": "JavaFlow",
        "ability_ids": [
            "ability_0001",
            "ability_0006",
            "ability_0018",
            "ability_0021",
            "ability_0022",
            "ability_0023",
            "ability_0009",
        ],
        "search_keywords": ["java", "stream", "kafka", "backend"],
    },
)

CITY_OPTIONS: tuple[str, ...] = ("上海", "北京", "深圳", "杭州", "远程")
REMOTE_POLICY_OPTIONS: tuple[str, ...] = ("onsite", "hybrid", "remote")
EDUCATION_LEVELS: tuple[str, ...] = ("bachelor", "master", "phd")


def _unit_normalize(values: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return [0.0 for _ in values]
    return [value / norm for value in values]


def _build_macro_catalog() -> list[dict[str, Any]]:
    macro_names = [
        "backend_and_concurrency",
        "infra_and_reliability",
        "product_and_frontend",
        "data_and_streaming",
    ]
    catalog: list[dict[str, Any]] = []
    for index in range(VECTOR_DIM_32):
        if index < len(macro_names):
            ability_name = macro_names[index]
        else:
            ability_name = f"macro_ability_{index + 1:02d}"
        catalog.append(
            {
                "ability_id": f"macro_ability_{index + 1:04d}",
                "ability_code": ability_name,
                "ability_name": ability_name,
                "layer": 32,
                "vector_index": index,
                "parent_id": None,
                "metadata": {},
            }
        )
    return catalog


def _build_family_catalog() -> list[dict[str, Any]]:
    family_name_overrides = {
        0: "concurrency_runtime",
        1: "backend_platform",
        2: "cache_and_storage",
        3: "distributed_coordination",
        4: "reliability_platform",
        5: "python_and_feature_stack",
        6: "ml_and_llm_stack",
        8: "frontend_web_stack",
        9: "architecture_design",
        10: "product_prd_stack",
        11: "java_backend_stack",
        12: "stream_and_data_stack",
        13: "quality_and_automation_stack",
    }
    catalog: list[dict[str, Any]] = []
    for index in range(VECTOR_DIM_128):
        ability_name = family_name_overrides.get(index, f"ability_family_{index + 1:03d}")
        catalog.append(
            {
                "ability_id": f"family_ability_{index + 1:04d}",
                "ability_code": ability_name,
                "ability_name": ability_name,
                "layer": 128,
                "vector_index": index,
                "parent_id": f"macro_ability_{(index // 4) + 1:04d}",
                "metadata": {},
            }
        )
    return catalog


def build_ability_taxonomy() -> dict[str, list[dict[str, Any]]]:
    """Create a 32/128/1024 ability taxonomy with deterministic indices."""
    macro_catalog = _build_macro_catalog()
    family_catalog = _build_family_catalog()
    atom_catalog: list[dict[str, Any]] = []
    special_by_index = {spec.vector_index: spec for spec in SPECIAL_ABILITY_SPECS}

    for index in range(VECTOR_DIM_1024):
        family_index = index // 8
        macro_index = family_index // 4
        spec = special_by_index.get(index)
        if spec is None:
            ability_id = f"ability_{index + 1:04d}"
            ability_code = f"generic_ability_{index + 1:04d}"
            ability_name = f"Generic Ability {index + 1:04d}"
            metadata = {
                "aliases": [],
                "verified_skill_label": ability_name,
                "is_hard_skill": False,
            }
        else:
            ability_id = spec.ability_id
            ability_code = spec.ability_code
            ability_name = spec.ability_name
            family_index = spec.family_index
            macro_index = spec.macro_index
            metadata = {
                "aliases": list(spec.aliases),
                "verified_skill_label": spec.verified_skill_label,
                "is_hard_skill": spec.is_hard_skill,
                "default_weight": spec.default_weight,
            }
        atom_catalog.append(
            {
                "ability_id": ability_id,
                "ability_code": ability_code,
                "ability_name": ability_name,
                "layer": 1024,
                "vector_index": index,
                "parent_id": f"family_ability_{family_index + 1:04d}",
                "metadata": metadata,
            }
        )
    return {"layer_32": macro_catalog, "layer_128": family_catalog, "layer_1024": atom_catalog}


def _roll_up_from_atoms(atom_scores: Sequence[float]) -> tuple[list[float], list[float]]:
    family_scores: list[float] = []
    for family_index in range(VECTOR_DIM_128):
        start = family_index * 8
        family_slice = atom_scores[start : start + 8]
        family_scores.append(sum(family_slice) / len(family_slice))

    macro_scores: list[float] = []
    for macro_index in range(VECTOR_DIM_32):
        start = macro_index * 4
        macro_slice = family_scores[start : start + 4]
        macro_scores.append(sum(macro_slice) / len(macro_slice))
    return family_scores, macro_scores


def project_target_vectors_from_weights(ability_weights: dict[str, float]) -> tuple[list[float], list[float], list[float]]:
    """Project atom-level weights into 128/32 vectors using fixed taxonomy indices."""
    atom_values = [0.0] * VECTOR_DIM_1024
    for ability_id, weight in ability_weights.items():
        spec = SPECIAL_ABILITY_BY_ID.get(ability_id)
        if spec is None:
            continue
        atom_values[spec.vector_index] = max(atom_values[spec.vector_index], float(weight))
    family_values, macro_values = _roll_up_from_atoms(atom_values)
    return _unit_normalize(macro_values), _unit_normalize(family_values), _unit_normalize(atom_values)


def build_search_alias_map() -> dict[str, list[str]]:
    return {alias: ability_ids[:] for alias, ability_ids in ALIAS_TO_ABILITY_IDS.items()}


def _pick_noise_ability_ids(rng: random.Random, exclude: list[str] | set[str] | tuple[str, ...], count: int) -> list[str]:
    excluded = set(exclude)
    generic_candidates = [
        f"ability_{index + 1:04d}"
        for index in range(24, VECTOR_DIM_1024)
        if f"ability_{index + 1:04d}" not in excluded
    ]
    return rng.sample(generic_candidates, count)


def _build_candidate_vectors(active_ability_ids: Sequence[str], rng: random.Random) -> tuple[list[float], list[float], list[float], dict[str, Any]]:
    atom_scores = [0.02] * VECTOR_DIM_1024
    active_set = set(active_ability_ids)

    for ability_id in active_ability_ids:
        if ability_id in SPECIAL_ABILITY_BY_ID:
            spec = SPECIAL_ABILITY_BY_ID[ability_id]
            atom_scores[spec.vector_index] = min(1.0, 0.55 + rng.random() * 0.40)
            family_start = spec.family_index * 8
            family_end = family_start + 8
            for index in range(family_start, family_end):
                atom_scores[index] = max(atom_scores[index], 0.05 + rng.random() * 0.12)
        else:
            index = int(ability_id.split("_")[-1]) - 1
            if 0 <= index < VECTOR_DIM_1024:
                atom_scores[index] = min(1.0, 0.35 + rng.random() * 0.30)

    family_scores, macro_scores = _roll_up_from_atoms(atom_scores)
    normalized_32 = _unit_normalize(macro_scores)
    normalized_128 = _unit_normalize(family_scores)
    normalized_1024 = _unit_normalize(atom_scores)

    support_profile = {
        "verified_ability_ids": sorted(
            [ability_id for ability_id in active_set if ability_id in SPECIAL_ABILITY_BY_ID]
        ),
        "support_count": len(active_set),
        "coverage_32": round(sum(1 for value in macro_scores if value > 0.03) / VECTOR_DIM_32, 4),
        "coverage_128": round(sum(1 for value in family_scores if value > 0.03) / VECTOR_DIM_128, 4),
        "coverage_1024": round(sum(1 for value in atom_scores if value > 0.03) / VECTOR_DIM_1024, 4),
    }
    return normalized_32, normalized_128, normalized_1024, support_profile


def _build_verified_skills(active_ability_ids: Sequence[str]) -> list[str]:
    labels = []
    for ability_id in active_ability_ids:
        spec = SPECIAL_ABILITY_BY_ID.get(ability_id)
        if spec is not None:
            labels.append(spec.verified_skill_label)
    return sorted(set(labels))


def _build_reranker_payload(
    candidate_id: str,
    display_name: str,
    archetype_code: str,
    verified_skills: Sequence[str],
    city: str,
    years_experience: float,
) -> str:
    focus = ", ".join(verified_skills[:6]) if verified_skills else "general engineering"
    return (
        f"{display_name} ({candidate_id}) shows certified combat evidence in {focus}. "
        f"Primary archetype={archetype_code}; city={city}; years_experience={years_experience:.1f}. "
        "Recent assessments indicate practical delivery, evidence-backed debugging, and stable execution under time-boxed constraints."
    )


def generate_mock_candidates(candidate_count: int = 256, seed: int = 7) -> list[dict[str, Any]]:
    """Generate deterministic candidate records for the mock RPC layer."""
    if candidate_count <= 0:
        raise ValueError("candidate_count must be positive")

    rng = random.Random(seed)
    candidates: list[dict[str, Any]] = []
    for index in range(candidate_count):
        candidate_rng = random.Random(seed * 10_000 + index)
        archetype = ARCHETYPE_BLUEPRINTS[index % len(ARCHETYPE_BLUEPRINTS)]
        active_ability_ids = list(archetype["ability_ids"])
        if index % 11 == 0:
            active_ability_ids.extend(["ability_0010", "ability_0020"])
        if index % 13 == 0:
            active_ability_ids.extend(["ability_0018", "ability_0009"])
        if index % 17 == 0:
            active_ability_ids.extend(["ability_0006", "ability_0008"])
        active_ability_ids.extend(
            _pick_noise_ability_ids(candidate_rng, active_ability_ids, count=6)
        )

        ability_vec_32, ability_vec_128, ability_vec_1024, support_profile = _build_candidate_vectors(
            active_ability_ids,
            candidate_rng,
        )
        verified_skills = _build_verified_skills(active_ability_ids)
        city = CITY_OPTIONS[index % len(CITY_OPTIONS)]
        years_experience = round(2.0 + (index % 12) * 0.7 + candidate_rng.random() * 0.5, 1)
        expected_salary_k = 18 + (index % 15) * 3 + int(candidate_rng.random() * 4)
        remote_policy = REMOTE_POLICY_OPTIONS[index % len(REMOTE_POLICY_OPTIONS)]
        visibility = "private" if index % 19 == 0 else "public"
        private_pool_ids = [f"pool_{(index % 4) + 1}"] if visibility == "private" else []
        assessment_status = "CERTIFIED" if index % 23 != 0 else "FAILED"
        display_name = f"{archetype['display_name_prefix']}_{index + 1:03d}"
        candidate_id = f"candidate_{index + 1:04d}"

        candidates.append(
            {
                "candidate_id": candidate_id,
                "display_name": display_name,
                "city": city,
                "remote_policy": remote_policy,
                "years_experience": years_experience,
                "expected_salary_k": expected_salary_k,
                "education_level": EDUCATION_LEVELS[index % len(EDUCATION_LEVELS)],
                "visibility": visibility,
                "private_pool_ids": private_pool_ids,
                "latest_assessment": {
                    "assessment_id": f"assessment_{index + 1:04d}",
                    "status": assessment_status,
                    "started_at": "2026-03-01T09:00:00Z",
                    "ended_at": "2026-03-01T10:00:00Z",
                    "time_budget_minutes": 60,
                },
                "candidate_vectors": {
                    "candidate_id": candidate_id,
                    "ability_vec_32": ability_vec_32,
                    "ability_vec_128": ability_vec_128,
                    "ability_vec_1024": ability_vec_1024,
                    "vec_version": DEFAULT_VEC_VERSION,
                    "support_profile": support_profile,
                    "last_certified_at": "2026-03-01T10:00:00Z",
                    "trace_id": DEFAULT_TRACE_ID,
                },
                "profile_data": {
                    "verified_skills": verified_skills,
                    "reranker_payload": _build_reranker_payload(
                        candidate_id=candidate_id,
                        display_name=display_name,
                        archetype_code=archetype["archetype_code"],
                        verified_skills=verified_skills,
                        city=city,
                        years_experience=years_experience,
                    ),
                },
                "search_keywords": list(
                    dict.fromkeys(
                        archetype["search_keywords"] + [skill.lower() for skill in verified_skills]
                    )
                ),
                "trace_id": DEFAULT_TRACE_ID,
                "version": DEFAULT_VERSION,
            }
        )
    rng.shuffle(candidates)
    return candidates


def build_mock_repository(candidate_count: int = 256, seed: int = 7) -> dict[str, Any]:
    """Create the full in-memory repository consumed by the mock RPC layer."""
    taxonomy = build_ability_taxonomy()
    return {
        "ability_taxonomy": taxonomy,
        "search_alias_map": build_search_alias_map(),
        "candidates": generate_mock_candidates(candidate_count=candidate_count, seed=seed),
    }
