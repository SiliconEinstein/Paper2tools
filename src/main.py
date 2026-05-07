"""
paper2tools_v2 CLI 主入口

使用示例:
    python -m src.main --step 1 --config configs/step1_config.yaml
    python -m src.main --step 2 --config configs/step2_config.yaml
"""

import argparse
import yaml
from pathlib import Path


def load_config(config_path: str) -> dict:
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def run_step1(config_path: str):
    from src.step1 import run_step1_pipeline
    config = load_config(config_path)
    run_step1_pipeline(config)


def run_step2(config_path: str):
    from src.step2 import run_step2_pipeline
    config = load_config(config_path)
    run_step2_pipeline(config)


def run_step3(config_path: str, action: str, query: str = None, top_k: int = 5, domain: str = None):
    from src.step3 import run_step3_pipeline
    config = load_config(config_path)
    run_step3_pipeline(config, action=action, query=query, top_k=top_k, domain=domain)


def main():
    parser = argparse.ArgumentParser(description="paper2tools_v2 pipeline")
    parser.add_argument("--step", choices=["1", "2", "3"], required=True)
    parser.add_argument("--config", default=None, help="Config file path")

    # Step3 specific arguments
    parser.add_argument("--action", choices=["build_index", "search"], help="Step3 action")
    parser.add_argument("--query", help="Search query (for Step3 search)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (for Step3 search)")
    parser.add_argument("--domain", help="Domain filter (for Step3 search)")

    args = parser.parse_args()

    if args.step == "1":
        config_path = args.config or "configs/step1_config.yaml"
        run_step1(config_path)
    elif args.step == "2":
        config_path = args.config or "configs/step2_config.yaml"
        run_step2(config_path)
    elif args.step == "3":
        config_path = args.config or "configs/step3_config.yaml"
        if not args.action:
            parser.error("--action is required for step 3")
        run_step3(config_path, args.action, args.query, args.top_k, args.domain)


if __name__ == "__main__":
    main()
