from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mock_data import build_mock_repository
from app.mock_rpc import MockRpcClient
from app.search_pipeline import parse_hr_query, run_search_pipeline


def test_query_parser_outputs_three_layer_targets_and_stable_fields() -> None:
    result = parse_hr_query("需要一个Golang Redis后端，能处理分布式锁和死锁")

    assert result.extracted_tags
    assert result.must_have_abilities
    assert len(result.target_vec_32) == 32
    assert len(result.target_vec_128) == 128
    assert len(result.target_vec_1024) == 1024
    assert "ability_0002" in result.must_have_abilities
    assert "ability_0003" in result.must_have_abilities


def test_search_pipeline_respects_layered_recall_and_payload_fetch_order() -> None:
    rpc_client = MockRpcClient(build_mock_repository(candidate_count=256, seed=7))
    response = run_search_pipeline(
        "需要一个能在高并发下处理 Redis 分布式锁和死锁的 Golang 后端",
        rpc_client=rpc_client,
        top_k=5,
        rerank_top_n=10,
    )

    assert response["status"] == "COMPLETED"
    assert response["recall_plan"]["stage_counts"]["vec32"] == 200
    assert response["recall_plan"]["stage_counts"]["vec128"] == 80
    assert response["recall_plan"]["stage_counts"]["vec1024"] == 40
    assert response["recall_plan"]["payload_fetch_count"] == 1
    assert response["recall_plan"]["call_order"][:5] == [
        "filter_gate",
        "vec32",
        "vec128",
        "vec1024",
        "sparse_sidecar",
    ]
    assert response["recall_plan"]["call_order"][5] == "fetch_reranker_payloads"
    assert 1 <= len(response["recall_plan"]["payload_fetch_candidate_ids"]) <= 10
    assert len(response["results"]) == 5


def test_search_pipeline_filter_gate_and_must_have_behavior() -> None:
    rpc_client = MockRpcClient(build_mock_repository(candidate_count=256, seed=9))
    response = run_search_pipeline(
        "招聘 Golang Redis 后端，最好会 PostgreSQL，处理分布式锁",
        filters={"city": "上海", "remote_policy": "onsite", "min_years_experience": 3},
        rpc_client=rpc_client,
        top_k=3,
        rerank_top_n=8,
    )

    assert response["status"] == "COMPLETED"
    assert response["recall_plan"]["stage_counts"]["filtered"] > 0

    for row in response["results"]:
        assert row["city"] == "上海"
        assert row["years_experience"] >= 3
        verified = {skill.lower() for skill in row["verified_skills"]}
        assert "golang" in verified
        assert "redis" in verified
        assert row["score_rrf"] >= 0
        assert row["score_rerank"] >= 0
        assert row["final_score"] >= 0
        assert "missing_must_have_abilities" in row["explanations"]
