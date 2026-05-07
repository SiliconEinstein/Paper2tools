"""
运行 workflow 文件组织器 - 按新的目录结构下载和组织文件
"""

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.step1.workflow_file_organizer import run_workflow_file_organizer


def main():
    # 配置路径
    step2_config_path = Path("configs/step2_config.yaml")
    selected_chains_path = Path("data/step1_output/selected_chains.json")
    output_base_dir = Path("data/workflows")

    # 加载 Step2 配置获取 TOS 信息
    with open(step2_config_path, encoding="utf-8") as f:
        step2_config = yaml.safe_load(f)

    tos_config = step2_config.get("tos", {})
    if not tos_config:
        print("✗ 未配置 TOS，无法下载文件")
        return

    # 运行文件组织器
    stats = run_workflow_file_organizer(
        selected_chains_path=selected_chains_path,
        output_base_dir=output_base_dir,
        tos_config=tos_config,
        max_workers=10,
        verbose=True,
    )

    # 保存统计信息
    import json
    stats_path = output_base_dir / "download_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 统计信息已保存到: {stats_path}")


if __name__ == "__main__":
    main()
