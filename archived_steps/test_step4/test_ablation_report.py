"""消融对比报告（无 LLM）。"""

import json
from pathlib import Path

from src.step4.ablation_report import build_ablation_report_markdown, write_ablation_report


def test_build_ablation_report_markdown(tmp_path: Path):
    sub = tmp_path / "10_vs_5"
    sub.mkdir()
    summary = {
        "kind": "ablation_aligned",
        "n_aligned": 2,
        "n_comparisons_ok": 2,
        "n_comparisons_failed": 0,
        "baseline_wins": 1,
        "variant_wins": 1,
        "ties": 0,
        "baseline_root": "/b",
        "variant_root": "/v",
        "baseline_tag": "w10",
        "variant_tag": "w5",
        "only_baseline_cluster_ids": [],
        "only_variant_cluster_ids": [],
    }
    (sub / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    lines = [
        {"cluster_id": 1, "better": "A", "confidence": "high", "reason": "r1"},
        {"cluster_id": 2, "better": "B", "confidence": "low", "reason": "r2"},
    ]
    with open(sub / "comparisons.jsonl", "w", encoding="utf-8") as f:
        for row in lines:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    agg = {
        "baseline_dir": "/b",
        "variant_5_dir": "/v",
        "variant_1_dir": None,
        "comparisons": {"10_vs_5": summary},
    }
    (tmp_path / "aggregate_summary.json").write_text(
        json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md, js = build_ablation_report_markdown(tmp_path, agg)
    assert "10_vs_5" in md
    assert "baseline 胜" in md or "baseline" in md
    assert js["arms"]["10_vs_5"]["n_ok"] == 2


def test_write_ablation_report_roundtrip(tmp_path: Path):
    sub = tmp_path / "10_vs_1"
    sub.mkdir()
    summary = {
        "skipped": True,
        "n_aligned": 0,
        "baseline_root": "/b",
        "variant_root": "/v",
    }
    (sub / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (sub / "comparisons.jsonl").write_text("", encoding="utf-8")
    agg = {
        "baseline_dir": "/b",
        "variant_5_dir": None,
        "variant_1_dir": "/v1",
        "comparisons": {"10_vs_1": summary},
    }
    (tmp_path / "aggregate_summary.json").write_text(json.dumps(agg), encoding="utf-8")

    md_p, js_p = write_ablation_report(tmp_path)
    assert md_p.is_file() and js_p.is_file()
    assert "10_vs_1" in md_p.read_text(encoding="utf-8")
