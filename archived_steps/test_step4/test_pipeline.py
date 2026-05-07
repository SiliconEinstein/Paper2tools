"""Step4 单元测试（不调用真实 LLM）"""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from src.step4.pipeline import (
    _aggregate,
    _choose_pairs,
    _parse_compare_response,
    load_workflow_entries,
)


def test_choose_pairs_sampled():
    p = _choose_pairs(10, "sampled", 15, seed=1)
    assert len(p) == 15
    assert len({tuple(x) for x in p}) == 15
    for i, j in p:
        assert i < j


def test_choose_pairs_small_exhaustive():
    p = _choose_pairs(4, "exhaustive", 100, seed=0)
    assert len(p) == 6


def test_parse_compare_response():
    raw = '{"better": "B", "confidence": "high", "dimensions": {}, "reason": "测试"}'
    d = _parse_compare_response(raw)
    assert d["better"] == "B"


def test_aggregate():
    results = [
        {"file_a": "a.json", "file_b": "b.json", "better": "A"},
        {"file_a": "a.json", "file_b": "c.json", "better": "tie"},
        {"file_a": "b.json", "file_b": "c.json", "better": "B"},
    ]
    r = _aggregate(results)
    assert r[0]["file"] == "a.json"
    assert r[0]["wins"] >= 1


def test_load_workflow_entries_dir(tmp_path):
    sub = tmp_path / "workflows"
    sub.mkdir()
    (sub / "cluster_1.json").write_text(
        json.dumps({"workflow_id": "w1", "title": "t", "description": "d", "steps": []}),
        encoding="utf-8",
    )
    ent = load_workflow_entries(tmp_path)
    assert len(ent) == 1
    assert ent[0][0] == "workflows/cluster_1.json"


def test_run_step4_pipeline_async_skips_when_one_wf(tmp_path):
    from src.step4.pipeline import run_step4_pipeline_async

    sub = tmp_path / "wf" / "workflows"
    sub.mkdir(parents=True)
    (sub / "only.json").write_text("{}", encoding="utf-8")
    config = {
        "data": {"workflows_dir": str(tmp_path / "wf"), "output_dir": str(tmp_path / "out")},
        "llm": {"provider": "gpt5_mini"},
        "runtime": {"verbose": False},
        "prompt": {"template_path": "prompts/step4_compare_workflows.md"},
        "chain_similarity": {"enabled": False},
    }
    with patch("src.step4.pipeline._load_prompt_template", return_value="x"):
        r = asyncio.run(run_step4_pipeline_async(config))
    assert r.get("skipped") is True
    assert (tmp_path / "out" / "summary.json").exists()
