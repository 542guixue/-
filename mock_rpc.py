from __future__ import annotations

"""Mock RPC layer for the layered hybrid search pipeline.

This module deliberately mirrors the shape of RPC-style search helpers without
connecting to a real database. All recall calls return *light* rows only.
Heavy reranker payloads are fetched through a separate whitelist API after RRF.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping, Sequence

from app.mock_data import build_mock_repository


class MockRpcError(RuntimeError):
    """Raised when a mock RPC call receives invalid input."""


@dataclass
class MockRpcAudit:
    payload_fetch_count: int = 0
    payload_fetch_candidate_ids: list[str] = field(default_factory=list)
    call_order: list[str] = field(default_factory=list)


@dataclass
class LightCandidateRow:
    candidate_id: str
    display_name: str
    city: str
    years_experience: float
    score: float
    matched_ability_ids: list[str]
    matched_verified_skills: list[str]

    def to_stage_row(self, score_field: str) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "display_name": self.display_name,
            "city": self.city,
            "years_experience": self.years_experience,
            score_field: round(self.score, 6),
            "matched_ability_ids": self.matched_ability_ids,
            "matched_verified_skills": self.matched_verified_skills,
        }


class MockRpcClient:
    def __init__(self, repository: Mapping[str, Any] | None = None) -> None:
        self.repository = dict(repository or build_mock_repository())
        self.candidates: list[dict[str, Any]] = list(self.repository["candidates"])
        self.alias_map: dict[str, list[str]] = dict(self.repository["search_alias_map"])
        self.audit = MockRpcAudit()

    @staticmethod
    def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            raise MockRpcError("vector dimension mismatch")
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for lhs, rhs in zip(left, right):
            dot += lhs * rhs
            left_norm += lhs * lhs
            right_norm += rhs * rhs
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / math.sqrt(left_norm * right_norm)

    def filter_candidates(self, filters: Mapping[str, Any] | None = None) -> list[str]:
        """Apply the hard filter gate before any vector recall."""
        self.audit.call_order.append("filter_gate")
        filters = dict(filters or {})
        candidate_ids: list[str] = []

        for candidate in self.candidates:
            latest_status = candidate["latest_assessment"]["status"]
            if latest_status != "CERTIFIED":
                continue

            if filters.get("city") and candidate["city"] != filters["city"]:
                continue

            if filters.get("remote_policy"):
                requested = filters["remote_policy"]
                if candidate["remote_policy"] != requested:
                    continue

            if filters.get("min_years_experience") is not None:
                if candidate["years_experience"] < float(filters["min_years_experience"]):
                    continue

            if filters.get("max_expected_salary_k") is not None:
                if candidate["expected_salary_k"] > int(filters["max_expected_salary_k"]):
                    continue

            if filters.get("education_level"):
                if candidate["education_level"] != filters["education_level"]:
                    continue

            if filters.get("visibility"):
                if candidate["visibility"] != filters["visibility"]:
                    continue

            private_pool_id = filters.get("private_pool_id")
            if private_pool_id:
                if private_pool_id not in candidate["private_pool_ids"]:
                    continue

            candidate_ids.append(candidate["candidate_id"])
        return candidate_ids

    def _candidate_lookup(self, candidate_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        candidate_id_set = set(candidate_ids)
        return {
            candidate["candidate_id"]: candidate
            for candidate in self.candidates
            if candidate["candidate_id"] in candidate_id_set
        }

    def _light_row(
        self,
        candidate: Mapping[str, Any],
        score: float,
        requirement_profile: Mapping[str, Any],
    ) -> LightCandidateRow:
        active_ids = set(candidate["candidate_vectors"]["support_profile"]["verified_ability_ids"])
        target_ids = set(requirement_profile["ability_weights"].keys())
        matched_ability_ids = sorted(active_ids & target_ids)
        verified_skills = set(candidate["profile_data"]["verified_skills"])
        matched_verified_skills = sorted(
            skill
            for skill in verified_skills
            if skill.lower() in {tag.lower() for tag in requirement_profile["extracted_tags"]}
        )
        return LightCandidateRow(
            candidate_id=str(candidate["candidate_id"]),
            display_name=str(candidate["display_name"]),
            city=str(candidate["city"]),
            years_experience=float(candidate["years_experience"]),
            score=float(score),
            matched_ability_ids=matched_ability_ids,
            matched_verified_skills=matched_verified_skills,
        )

    def _rank_by_vector(
        self,
        vector_field: str,
        score_field: str,
        candidate_ids: Sequence[str],
        target_vector: Sequence[float],
        requirement_profile: Mapping[str, Any],
        limit: int,
        must_have_boost: bool = False,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise MockRpcError("limit must be positive")

        candidate_lookup = self._candidate_lookup(candidate_ids)
        rows: list[LightCandidateRow] = []
        must_have_ids = set(requirement_profile.get("must_have_abilities", []))

        for candidate_id in candidate_ids:
            candidate = candidate_lookup.get(candidate_id)
            if candidate is None:
                continue
            candidate_vector = candidate["candidate_vectors"][vector_field]
            score = self._cosine_similarity(target_vector, candidate_vector)
            if must_have_boost and must_have_ids:
                active_ids = set(candidate["candidate_vectors"]["support_profile"]["verified_ability_ids"])
                hit_count = len(active_ids & must_have_ids)
                missing_count = len(must_have_ids - active_ids)
                if missing_count:
                    score *= max(0.20, 1.0 - 0.28 * missing_count)
                if hit_count:
                    score += min(0.12, 0.03 * hit_count)
            rows.append(self._light_row(candidate, score, requirement_profile))

        rows.sort(key=lambda row: (-row.score, row.candidate_id))
        return [row.to_stage_row(score_field) for row in rows[:limit]]

    def search_candidates_by_vec32(
        self,
        requirement_profile: Mapping[str, Any],
        candidate_ids: Sequence[str],
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.audit.call_order.append("vec32")
        return self._rank_by_vector(
            vector_field="ability_vec_32",
            score_field="score_32",
            candidate_ids=candidate_ids,
            target_vector=requirement_profile["target_vec_32"],
            requirement_profile=requirement_profile,
            limit=limit,
        )

    def search_candidates_by_vec128(
        self,
        requirement_profile: Mapping[str, Any],
        candidate_ids: Sequence[str],
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        self.audit.call_order.append("vec128")
        return self._rank_by_vector(
            vector_field="ability_vec_128",
            score_field="score_128",
            candidate_ids=candidate_ids,
            target_vector=requirement_profile["target_vec_128"],
            requirement_profile=requirement_profile,
            limit=limit,
        )

    def search_candidates_by_vec1024(
        self,
        requirement_profile: Mapping[str, Any],
        candidate_ids: Sequence[str],
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        self.audit.call_order.append("vec1024")
        return self._rank_by_vector(
            vector_field="ability_vec_1024",
            score_field="score_1024",
            candidate_ids=candidate_ids,
            target_vector=requirement_profile["target_vec_1024"],
            requirement_profile=requirement_profile,
            limit=limit,
            must_have_boost=True,
        )

    def search_candidates_by_sparse_sidecar(
        self,
        requirement_profile: Mapping[str, Any],
        candidate_ids: Sequence[str],
        exclude_candidate_ids: Iterable[str] | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """Sidecar sparse recall based on verified_skills/search_keywords only.

        This method intentionally excludes already-dense shortlists by default so
        sparse recall behaves as a补漏 sidecar instead of the dominant ranking path.
        """
        self.audit.call_order.append("sparse_sidecar")
        exclude_set = set(exclude_candidate_ids or [])
        candidate_lookup = self._candidate_lookup(candidate_ids)
        extracted_terms = {tag.lower() for tag in requirement_profile["extracted_tags"]}
        query_tokens = set(str(requirement_profile["query_text_clean"]).lower().split())
        rows: list[LightCandidateRow] = []

        for candidate_id in candidate_ids:
            if candidate_id in exclude_set:
                continue
            candidate = candidate_lookup.get(candidate_id)
            if candidate is None:
                continue
            verified_skills = {skill.lower() for skill in candidate["profile_data"]["verified_skills"]}
            search_keywords = {keyword.lower() for keyword in candidate.get("search_keywords", [])}
            matched_terms = (verified_skills | search_keywords) & (extracted_terms | query_tokens)
            if not matched_terms:
                continue
            score = len(matched_terms) / max(1, len(extracted_terms | query_tokens))
            rows.append(self._light_row(candidate, score, requirement_profile))

        rows.sort(key=lambda row: (-row.score, row.candidate_id))
        return [row.to_stage_row("score_sparse") for row in rows[:limit]]

    def fetch_reranker_payloads(self, candidate_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Fetch heavy payloads only after RRF shortlist creation."""
        self.audit.call_order.append("fetch_reranker_payloads")
        self.audit.payload_fetch_count += 1
        self.audit.payload_fetch_candidate_ids = list(candidate_ids)
        candidate_lookup = self._candidate_lookup(candidate_ids)
        payloads: dict[str, dict[str, Any]] = {}
        for candidate_id in candidate_ids:
            candidate = candidate_lookup.get(candidate_id)
            if candidate is None:
                continue
            payloads[candidate_id] = {
                "candidate_id": candidate_id,
                "display_name": candidate["display_name"],
                "city": candidate["city"],
                "years_experience": candidate["years_experience"],
                "verified_skills": list(candidate["profile_data"]["verified_skills"]),
                "reranker_payload": candidate["profile_data"]["reranker_payload"],
                "support_profile": dict(candidate["candidate_vectors"]["support_profile"]),
            }
        return payloads

    def get_light_candidates(self, candidate_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        candidate_lookup = self._candidate_lookup(candidate_ids)
        return {
            candidate_id: {
                "candidate_id": candidate["candidate_id"],
                "display_name": candidate["display_name"],
                "city": candidate["city"],
                "years_experience": candidate["years_experience"],
                "remote_policy": candidate["remote_policy"],
                "expected_salary_k": candidate["expected_salary_k"],
                "visibility": candidate["visibility"],
            }
            for candidate_id, candidate in candidate_lookup.items()
        }
