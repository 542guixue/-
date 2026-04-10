from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.search_pipeline import reciprocal_rank_fusion


def test_rrf_fusion_prefers_multi_stage_consistency() -> None:
    fused = reciprocal_rank_fusion(
        stage_results={
            "vec32": [
                {"candidate_id": "candidate_a", "score_32": 0.91},
                {"candidate_id": "candidate_b", "score_32": 0.89},
            ],
            "vec128": [
                {"candidate_id": "candidate_b", "score_128": 0.95},
                {"candidate_id": "candidate_a", "score_128": 0.70},
            ],
            "vec1024": [
                {"candidate_id": "candidate_b", "score_1024": 0.98},
            ],
            "sparse_sidecar": [
                {"candidate_id": "candidate_c", "score_sparse": 1.00},
            ],
        }
    )

    assert [row["candidate_id"] for row in fused[:3]] == [
        "candidate_b",
        "candidate_a",
        "candidate_c",
    ]
    assert fused[0]["score_rrf"] > fused[1]["score_rrf"] > fused[2]["score_rrf"]


def test_rrf_sparse_sidecar_is_supplement_not_master_path() -> None:
    fused = reciprocal_rank_fusion(
        stage_results={
            "vec32": [
                {"candidate_id": "dense_only", "score_32": 0.90},
                {"candidate_id": "balanced", "score_32": 0.88},
            ],
            "vec128": [
                {"candidate_id": "balanced", "score_128": 0.92},
                {"candidate_id": "dense_only", "score_128": 0.82},
            ],
            "vec1024": [
                {"candidate_id": "balanced", "score_1024": 0.94},
            ],
            "sparse_sidecar": [
                {"candidate_id": "sparse_only", "score_sparse": 1.00},
            ],
        }
    )

    ranked_ids = [row["candidate_id"] for row in fused[:3]]
    assert ranked_ids[0] == "balanced"
    assert ranked_ids[-1] == "sparse_only"
    assert fused[0]["score_rrf"] > fused[-1]["score_rrf"]
