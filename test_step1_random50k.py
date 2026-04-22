#!/usr/bin/env python3
"""
Step1 测试脚本 - 随机5万条数据
"""

import sys
import yaml
from pathlib import Path

sys.path.insert(0, '/personal/paper2tools')
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.step1 import run_step1_pipeline


def main():
    config_path = project_root / "configs" / "step1_random50k_config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    print("\n" + "=" * 60)
    print("Step1 Random 50K Test")
    print("=" * 60)

    result = run_step1_pipeline(config)

    print("\n" + "=" * 60)
    print("Random 50K test completed!")
    print(f"Clusters: {result.n_clusters}")
    print(f"Silhouette: {result.metrics.get('silhouette', 'N/A')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
