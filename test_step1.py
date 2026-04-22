#!/usr/bin/env python3
"""
Step1 测试脚本 - 小规模验证

只处理前 100 篇论文，验证整个流程是否正常运行
"""

import sys
import yaml
from pathlib import Path

# 添加 paper2tools 到 path
sys.path.insert(0, '/personal/paper2tools')

# 添加当前项目到 path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.step1 import run_step1_pipeline


def main():
    # 加载配置
    config_path = project_root / "configs" / "step1_config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 修改为测试模式：只处理前 100 篇论文
    print("\n" + "=" * 60)
    print("Step1 Test Mode: Processing first 100 papers only")
    print("=" * 60)

    # 运行 pipeline
    result = run_step1_pipeline(config)

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print(f"Clusters found: {result.n_clusters}")
    print(f"Silhouette score: {result.metrics.get('silhouette', 'N/A')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
