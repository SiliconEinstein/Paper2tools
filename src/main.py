"""
paper2tools_v2 CLI 主入口

使用示例:
    python -m src.main --step 1 --config configs/step1_config.yaml
    python -m src.main --step all
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
    from src.step2 import run_step2_pipeline, load_config as load_step2_config
    config = load_step2_config(config_path)
    run_step2_pipeline(config)


def run_step3(config_path: str):
    from src.step3 import run_step3_pipeline
    config = load_config(config_path)
    run_step3_pipeline(config)


def main():
    parser = argparse.ArgumentParser(description="paper2tools_v2 pipeline")
    parser.add_argument("--step", choices=["1", "2", "3", "all"], required=True)
    parser.add_argument("--config", default=None, help="Config file path")
    args = parser.parse_args()

    if args.step == "1":
        config_path = args.config or "configs/step1_config.yaml"
        run_step1(config_path)
    elif args.step == "2":
        config_path = args.config or "configs/step2_config.yaml"
        run_step2(config_path)
    elif args.step == "3":
        config_path = args.config or "configs/step3_config.yaml"
        run_step3(config_path)
    elif args.step == "all":
        run_step1(args.config or "configs/step1_config.yaml")
        run_step2(args.config or "configs/step2_config.yaml")
        run_step3(args.config or "configs/step3_config.yaml")


if __name__ == "__main__":
    main()
