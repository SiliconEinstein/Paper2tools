#!/usr/bin/env python3
"""
完整流水线脚本 - 用 multiprocessing 并行运行期刊测试 + 随机50k测试
每个测试独立进程，完成 Step1 → Step2 → Step3 全流程
"""

import asyncio
import json
import sys
import traceback
import yaml
import multiprocessing
from pathlib import Path
from datetime import datetime


def log(msg: str, test_name: str = "MAIN"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{test_name}] {msg}", flush=True)


def run_step1(config_path: str, test_name: str):
    """运行 Step1: 向量化与聚类"""
    log("Starting Step1: Vectorization & Clustering", test_name)
    from src.step1.pipeline import run_step1_pipeline_async
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    result = asyncio.run(run_step1_pipeline_async(config))
    log(f"Step1 completed: {result.n_clusters} clusters", test_name)
    return result


def run_step2(config_path: str, test_name: str, selected_paper_ids: list, output_dir: Path):
    """运行 Step2: 工具信息注入"""
    log(f"Starting Step2: Tool Extraction for {len(selected_paper_ids)} papers", test_name)
    from src.step2.batch_processor import process_paper_batch
    from src.step2.tool_extractor import _load_prompt_template
    from src.models.llm_providers import gpt5_mini_completion

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    tos_config = config['tos']
    prompt_template = _load_prompt_template(config['prompt']['template_path'])

    result = asyncio.run(process_paper_batch(
        paper_ids=selected_paper_ids,
        tos_config=tos_config,
        llm_fn=gpt5_mini_completion,
        prompt_template=prompt_template,
        output_dir=output_dir,
        verbose=True
    ))

    log(f"Step2 completed: {result.get('success', 0)}/{result.get('total', 0)} papers", test_name)
    return result


def run_step3(config_path: str, test_name: str, step2_output_dir: Path, step3_output_dir: Path):
    """运行 Step3: Workflow 提取"""
    log("Starting Step3: Workflow Extraction", test_name)
    from src.step3 import run_step3_pipeline

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    config['data']['input_path'] = str(step2_output_dir)
    config['data']['output_dir'] = str(step3_output_dir)

    workflows = run_step3_pipeline(config)
    log(f"Step3 completed: {len(workflows)} workflows extracted", test_name)
    return workflows


def run_single_test(test_name: str, step1_config: str, step2_config: str, step3_config: str,
                    step2_output_dir: str, step3_output_dir: str,
                    cluster_labels_dir: str, lance_db_dir: str):
    """运行单个测试的完整流程（独立进程）"""
    # 重定向子进程输出到主日志
    sys.stdout = open("logs/full_pipeline.log", "a", buffering=1)
    sys.stderr = sys.stdout

    log(f"========== Starting Test: {test_name} ==========", test_name)

    try:
        # Step1
        step1_result = run_step1(step1_config, test_name)

        # 选择 top 10% 簇
        from src.step1.cluster_selector import select_top_clusters

        cluster_labels_path = Path(cluster_labels_dir) / "cluster_labels.json"
        selected_paper_ids = select_top_clusters(
            cluster_labels_path=cluster_labels_path,
            lance_db_path=Path(lance_db_dir),
            top_percent=0.1,
            max_chains_per_cluster=10,
            verbose=True
        )
        log(f"Selected {len(selected_paper_ids)} papers for Step2", test_name)

        # 保存选中的 paper_ids
        s2out = Path(step2_output_dir)
        s2out.mkdir(parents=True, exist_ok=True)
        with open(s2out / "selected_paper_ids.json", 'w') as f:
            json.dump(selected_paper_ids, f, indent=2)

        # Step2
        run_step2(step2_config, test_name, selected_paper_ids, s2out)

        # Step3
        run_step3(step3_config, test_name, s2out, Path(step3_output_dir))

        log(f"========== Test {test_name} COMPLETED ==========", test_name)

    except Exception as e:
        log(f"========== Test {test_name} FAILED: {e} ==========", test_name)
        traceback.print_exc()


def generate_visualization():
    """生成可视化对比图"""
    log("Generating visualization...", "VIZ")
    try:
        from src.step1.visualizer import plot_cluster_comparison, plot_single_cluster

        journal_dir = Path("data/step1_output")
        random_dir = Path("data/step1_output_random50k")

        if (journal_dir / "cluster_labels.json").exists() and (random_dir / "cluster_labels.json").exists():
            plot_cluster_comparison(
                journal_dir=journal_dir,
                random_dir=random_dir,
                output_path=Path("data/step1_output/cluster_comparison.png")
            )

        if (journal_dir / "cluster_labels.json").exists():
            plot_single_cluster(
                output_dir=journal_dir,
                lance_db_dir=Path("data/lance_db"),
                output_path=journal_dir / "pca_journal.png",
                title="Bioinformatics Journals"
            )

        if (random_dir / "cluster_labels.json").exists():
            plot_single_cluster(
                output_dir=random_dir,
                lance_db_dir=Path("data/lance_db_random50k"),
                output_path=random_dir / "pca_random50k.png",
                title="Random 50k Papers"
            )

        log("Visualization completed", "VIZ")
    except Exception as e:
        log(f"Visualization failed: {e}", "VIZ")
        traceback.print_exc()


def main():
    log("========== Full Pipeline Started ==========")

    # 创建输出目录
    for d in ["data/step1_output", "data/step1_output_random50k",
              "data/step2_output", "data/step2_output_random50k",
              "data/step3_output", "data/step3_output_random50k"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # 串行运行两个测试（避免内存爆炸）
    log("Running Random50k_Test first (smaller dataset)...")
    p_random = multiprocessing.Process(
        target=run_single_test,
        args=(
            "Random50k_Test",
            "configs/step1_random50k_config.yaml",
            "configs/step2_config.yaml",
            "configs/step3_config.yaml",
            "data/step2_output_random50k",
            "data/step3_output_random50k",
            "data/step1_output_random50k",
            "data/lance_db_random50k",
        )
    )
    p_random.start()
    log(f"Random50k_Test PID: {p_random.pid}")
    p_random.join()
    log(f"Random50k_Test exited with code {p_random.exitcode}")

    log("\nRunning Journal_Test (full dataset)...")
    p_journal = multiprocessing.Process(
        target=run_single_test,
        args=(
            "Journal_Test",
            "configs/step1_config.yaml",
            "configs/step2_config.yaml",
            "configs/step3_config.yaml",
            "data/step2_output",
            "data/step3_output",
            "data/step1_output",
            "data/lance_db",
        )
    )
    p_journal.start()
    log(f"Journal_Test PID: {p_journal.pid}")
    p_journal.join()
    log(f"Journal_Test exited with code {p_journal.exitcode}")

    # 生成可视化
    generate_visualization()

    log("========== Full Pipeline Completed ==========")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    try:
        main()
    except KeyboardInterrupt:
        log("Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"Pipeline failed: {e}")
        traceback.print_exc()
        sys.exit(1)
