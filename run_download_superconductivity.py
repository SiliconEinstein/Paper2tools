#!/usr/bin/env python3
"""
为 Superconductivity 数据集下载选中论文的 md 和 xml 文件
"""
import json
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.step1.workflow_file_organizer import run_workflow_file_organizer

def main():
    print("=== 下载 Superconductivity 数据集文件 ===\n")

    # 输入路径
    selected_chains_path = Path("data/Superconductivity/step1_output_agglomerative_v2/selected_chains.json")
    output_base_dir = Path("data/Superconductivity/workflows")

    # 检查输入文件
    if not selected_chains_path.exists():
        print(f"错误: 找不到 {selected_chains_path}")
        return

    # 读取选中的链
    with open(selected_chains_path, 'r', encoding='utf-8') as f:
        selected_chains = json.load(f)

    print(f"[1/2] 读取到 {len(selected_chains)} 条选中的推理链")

    # 统计论文数量
    paper_ids = set(chain['paper_id'] for chain in selected_chains)
    print(f"      涉及 {len(paper_ids)} 篇论文")

    # 统计聚类数量
    cluster_ids = set(chain['cluster_id'] for chain in selected_chains)
    print(f"      涉及 {len(cluster_ids)} 个聚类")

    # TOS 配置
    tos_config = {
        "xml_source_prefix": "paper_ocr/xml/",
        "md_prefix": "paper_ocr/md/"
    }

    print(f"\n[2/2] 开始下载文件到 {output_base_dir}")
    print("      使用 10 个并发线程...")

    # 调用下载器
    all_stats = run_workflow_file_organizer(
        selected_chains_path=selected_chains_path,
        output_base_dir=output_base_dir,
        tos_config=tos_config,
        max_workers=10,
        verbose=True
    )

    # 汇总统计
    total_xml_success = sum(s["xml_success"] for s in all_stats.values())
    total_md_success = sum(s["md_success"] for s in all_stats.values())
    total_chains = sum(s["total_chains"] for s in all_stats.values())
    total_papers = sum(s["total_papers"] for s in all_stats.values())
    total_xml_failed = total_chains - total_xml_success
    total_md_failed = total_papers - total_md_success

    print("\n" + "="*60)
    print("下载完成统计:")
    print(f"  总聚类数: {len(all_stats)}")
    print(f"  总推理链: {total_chains}")
    print(f"  总论文数: {total_papers}")
    print(f"  XML 下载成功: {total_xml_success}/{total_chains}")
    print(f"  XML 下载失败: {total_xml_failed}")
    print(f"  MD 下载成功: {total_md_success}/{total_papers}")
    print(f"  MD 下载失败: {total_md_failed}")
    print("="*60)

    if total_xml_failed > 0 or total_md_failed > 0:
        print("\n⚠ 部分文件下载失败，请检查日志")
    else:
        print("\n✓ 所有文件下载成功！")

if __name__ == "__main__":
    main()
