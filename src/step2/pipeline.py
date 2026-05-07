"""
Step2 主流程 - 从聚类到 Workflow 提取
"""

from pathlib import Path
from typing import Dict, List

from .cluster_loader import load_cluster_metadata, load_cluster_chains
from .workflow_dir_builder import build_workflow_directory
from .task_generator import generate_task_script, generate_task_manifest
from ..db import LanceVectorStore
from ..db.schema import CLUSTER_METADATA_SCHEMA


def run_step2_pipeline(config: Dict) -> Dict:
    """
    Step2 主流程入口

    Args:
        config: 配置字典（从 step2_config.yaml 加载）

    Returns:
        Dict: 执行结果摘要
    """
    print("\n" + "=" * 60, flush=True)
    print("Step2 Pipeline: Workflow Directory Preparation", flush=True)
    print("=" * 60, flush=True)

    # 1. 初始化存储
    print("\n[1/5] Initializing storage...", flush=True)
    lance_db_dir = Path(config["data"]["lance_db_dir"])

    vector_store = LanceVectorStore(
        db_path=lance_db_dir,
        table_name="chain_embeddings"
    )

    cluster_store = LanceVectorStore(
        db_path=lance_db_dir,
        table_name=config["data"].get("cluster_metadata_table", "cluster_metadata"),
        schema=CLUSTER_METADATA_SCHEMA
    )

    print("  ✓ Storage initialized", flush=True)

    # 2. 加载聚类元数据
    print("\n[2/5] Loading cluster metadata...", flush=True)
    domain = config["cluster_selection"]["domain"]

    cluster_metadata = load_cluster_metadata(
        cluster_store=cluster_store,
        domain=domain,
        cluster_ids=config["cluster_selection"].get("cluster_ids"),
        min_chains=config["cluster_selection"].get("min_chains"),
        max_chains=config["cluster_selection"].get("max_chains"),
        min_intra_similarity=config["cluster_selection"].get("min_intra_similarity")
    )

    print(f"  ✓ Loaded {len(cluster_metadata)} clusters", flush=True)

    if not cluster_metadata:
        print("\n⚠ No clusters match the selection criteria. Exiting.", flush=True)
        cluster_store.close()
        vector_store.close()
        return {
            "domain": domain,
            "clusters_processed": 0,
            "total_chains": 0,
            "total_papers": 0
        }

    # 3. 为每个聚类构建 Workflow 目录
    print("\n[3/5] Building workflow directories...", flush=True)

    output_base_dir = Path(config["data"]["output_dir"].format(domain=domain))
    output_base_dir.mkdir(parents=True, exist_ok=True)

    workflow_dirs = []
    total_chains = 0
    total_papers = 0

    for i, cluster_meta in enumerate(cluster_metadata, 1):
        cluster_id = cluster_meta["local_cluster_id"]

        print(f"\n  [{i}/{len(cluster_metadata)}] Cluster {cluster_id}...", flush=True)

        # 加载该聚类的所有链
        chains = load_cluster_chains(
            vector_store=vector_store,
            domain=domain,
            cluster_id=cluster_id
        )

        # 构建目录
        workflow_dir = build_workflow_directory(
            cluster_meta=cluster_meta,
            chains=chains,
            output_dir=output_base_dir,
            tos_config=config["file_download"],
            max_workers=config["file_download"].get("max_workers", 10),
            verbose=config.get("runtime", {}).get("verbose", True)
        )

        workflow_dirs.append(workflow_dir)
        total_chains += len(chains)
        total_papers += cluster_meta["num_papers"]

    print(f"\n  ✓ Built {len(workflow_dirs)} workflow directories", flush=True)

    # 4. 生成任务脚本
    print("\n[4/5] Generating task scripts...", flush=True)

    task_config = config.get("task_generation", {})
    mode = task_config.get("mode", "sequential")
    script_name = task_config.get("output_script", "run_workflows.sh")

    script_path = output_base_dir / script_name
    generate_task_script(
        workflow_dirs=workflow_dirs,
        cluster_metadata=cluster_metadata,
        output_path=script_path,
        mode=mode
    )

    print(f"  ✓ Generated task script: {script_path}", flush=True)

    # 生成任务清单
    manifest_path = output_base_dir / "workflow_tasks.json"
    generate_task_manifest(
        workflow_dirs=workflow_dirs,
        cluster_metadata=cluster_metadata,
        output_path=manifest_path
    )

    print(f"  ✓ Generated task manifest: {manifest_path}", flush=True)

    # 5. 清理
    print("\n[5/5] Cleaning up...", flush=True)
    cluster_store.close()
    vector_store.close()
    print("  ✓ Storage closed", flush=True)

    # 6. 打印使用说明
    print("\n" + "=" * 60, flush=True)
    print("Step2 Pipeline Complete!", flush=True)
    print("=" * 60, flush=True)
    print(f"\nWorkflow directories prepared:")
    print(f"  Domain: {domain}")
    print(f"  Clusters: {len(workflow_dirs)}")
    print(f"  Total chains: {total_chains}")
    print(f"  Total papers: {total_papers}")
    print(f"  Output: {output_base_dir}")
    print(f"\nNext steps:")
    print(f"  1. Review the task manifest: {manifest_path}")
    print(f"  2. Run the task script: {script_path}")
    print(f"  3. For each cluster, open Claude Code and invoke Workflower:")
    print(f"     - Navigate to the cluster directory")
    print(f"     - Run: /workflower-v2")
    print(f"     - Or prompt: 提取 cluster_N 的工作流并生成综述")
    print("=" * 60 + "\n", flush=True)

    return {
        "domain": domain,
        "clusters_processed": len(workflow_dirs),
        "total_chains": total_chains,
        "total_papers": total_papers,
        "output_dir": str(output_base_dir),
        "task_script": str(script_path),
        "task_manifest": str(manifest_path)
    }
