#!/usr/bin/env python3
"""
按「每簇 K 条思维链」子采样 selected_chains.json，再跑 Step3，输出到独立目录。

典型用法（与「每簇 10 条」池子对比）：
  # 全量 10 条/簇（不下采样，与 selected_chains 一致）
  python run_step3_chain_budget.py --chains-per-cluster 10 --output-dir data/step3_output/workflow_10

  # 从每簇最多 10 条中随机抽 5 条
  python run_step3_chain_budget.py --chains-per-cluster 5 --seed 42 --output-dir data/step3_output/workflow_5

  # 随机抽 1 条
  python run_step3_chain_budget.py --chains-per-cluster 1 --seed 42 --output-dir data/step3_output/k1

工作目录应为 paper2tools_v2 根目录。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)


def main() -> None:
    ap = argparse.ArgumentParser(description="Step3：按簇预算 K 条链生成 workflow")
    ap.add_argument(
        "--chains-per-cluster",
        type=int,
        required=True,
        help="每簇使用的思维链条数上限；若簇内条数≤K 则全用，否则随机抽 K（seed 可复现）",
    )
    ap.add_argument("--seed", type=int, default=42, help="下采样随机种子")
    ap.add_argument(
        "--selected-chains",
        type=Path,
        default=Path("data/step1_output/selected_chains.json"),
        help="Step1c 输出的 selected_chains.json",
    )
    ap.add_argument(
        "--filtered-output",
        type=Path,
        default=None,
        help="子采样后的 JSON 路径；默认写入 data/step1_output/selected_chains_budget_K{K}_s{seed}.json",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Step3 输出目录，如 data/step3_budget/k5",
    )
    ap.add_argument(
        "--step3-config",
        type=Path,
        default=Path("configs/step3_config.yaml"),
        help="Step3 YAML 配置（会覆盖 input_path / output_dir）",
    )
    ap.add_argument(
        "--step2-enriched-dir",
        type=Path,
        default=None,
        help="覆盖配置中的 step2_enriched_dir；默认用 step3 yaml 内值",
    )
    args = ap.parse_args()

    if args.chains_per_cluster < 1:
        raise SystemExit("--chains-per-cluster 须 >= 1")

    sel = args.selected_chains
    if not sel.is_file():
        raise SystemExit(f"找不到 selected_chains: {sel}")

    with open(sel, encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise SystemExit("selected_chains.json 顶层应为数组")

    from src.step3.selected_chains_budget import subsample_selected_chains

    out_rows = subsample_selected_chains(rows, args.chains_per_cluster, args.seed)

    if args.filtered_output:
        filt_path = args.filtered_output
    else:
        filt_path = Path(
            f"data/step1_output/selected_chains_budget_k{args.chains_per_cluster}_s{args.seed}.json"
        )
    filt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(filt_path, "w", encoding="utf-8") as f:
        json.dump(out_rows, f, ensure_ascii=False, indent=2)

    meta = {
        "source_selected_chains": str(sel.resolve()),
        "filtered_path": str(filt_path.resolve()),
        "chains_per_cluster": args.chains_per_cluster,
        "seed": args.seed,
        "n_rows_source": len(rows),
        "n_rows_filtered": len(out_rows),
    }
    meta_path = filt_path.with_suffix(".meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"子采样完成: {len(out_rows)} 行 → {filt_path}", flush=True)
    print(f"元数据: {meta_path}", flush=True)

    with open(args.step3_config, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config.setdefault("data", {})
    config["data"]["input_path"] = str(filt_path.resolve())
    config["data"]["output_dir"] = str(args.output_dir.resolve())
    if args.step2_enriched_dir is not None:
        config["data"]["step2_enriched_dir"] = str(args.step2_enriched_dir)

    from src.step3.pipeline import run_step3_pipeline_async

    asyncio.run(run_step3_pipeline_async(config))
    print(f"Step3 结束，输出: {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
