#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
INPUT_JSON="${1:-$REPO_ROOT/examples/sample_hr_query.json}"

if [[ ! -f "$INPUT_JSON" ]]; then
  echo "input file not found: $INPUT_JSON" >&2
  exit 1
fi

python3 - "$REPO_ROOT" "$INPUT_JSON" <<'PY'
import json
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1]).resolve()
input_path = pathlib.Path(sys.argv[2]).resolve()
sys.path.insert(0, str(repo_root))

from app.mock_data import build_mock_repository
from app.mock_rpc import MockRpcClient
from app.search_pipeline import run_search_pipeline

payload = json.loads(input_path.read_text(encoding="utf-8"))
rpc_client = MockRpcClient(build_mock_repository(candidate_count=256, seed=9))

response = run_search_pipeline(
    payload["query_text"],
    filters=payload.get("filters"),
    top_k=int(payload.get("top_k", 3)),
    rerank_top_n=int(payload.get("rerank_top_n", 12)),
    rpc_client=rpc_client,
    trace_id=payload.get("trace_id"),
    version=payload.get("version", "session5.mock.v1"),
)

print(json.dumps(response, ensure_ascii=False, indent=2))
PY
