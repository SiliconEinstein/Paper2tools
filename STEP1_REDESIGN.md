# Step1 重新设计方案

## 1. 向量化元数据增强

### 1.1 Schema 修改

在 `CHAIN_EMBEDDING_SCHEMA` 中新增字段：

```python
# 文件路径（完整路径，用于后续检索和加载）
pa.field("xml_path", pa.string()),  # 如: "tos://paper_ocr/xml/1234567890_c1.xml"
pa.field("md_path", pa.string()),   # 如: "tos://paper_ocr/md/1234567890.md"
```

### 1.2 路径生成规则

在 `vectorizer.py` 的 `vectorize_reasoning_chains()` 中：

```python
metadata = {
    "paper_id": chain.paper_id,
    "journal": chain.journal,
    "domain": domain,
    "conclusion_id": chain.conclusion_id,
    "xml_path": f"tos://paper_ocr/xml/{chain.paper_id}_{chain.conclusion_id}.xml",
    "md_path": f"tos://paper_ocr/md/{chain.paper_id}.md",
    # ... 其他字段
}
```

**注意**：路径前缀 `tos://paper_ocr/` 应该从配置文件读取，支持不同的存储后端。

---

## 2. 聚类结果存储重新设计

### 2.1 新建 Lance 表：`cluster_metadata`

**Schema**：

```python
CLUSTER_METADATA_SCHEMA = pa.schema([
    # 主键：全局唯一的聚类ID
    # 格式: {domain}_{cluster_idx}
    # 例: "bioinformatics_0", "materials_science_42"
    pa.field("global_cluster_id", pa.string()),
    
    # 领域信息
    pa.field("domain", pa.string()),
    pa.field("local_cluster_id", pa.int32()),  # 领域内的局部ID
    
    # 聚类统计
    pa.field("num_chains", pa.int32()),        # 包含的思维链数量
    pa.field("num_papers", pa.int32()),        # 包含的论文数量
    
    # 聚类成员（路径列表）
    pa.field("chain_xml_paths", pa.list_(pa.string())),  # 所有思维链的XML路径
    pa.field("paper_ids", pa.list_(pa.string())),        # 去重后的paper_id列表
    pa.field("paper_md_paths", pa.list_(pa.string())),   # 对应的MD文件路径
    
    # 聚类质心
    pa.field("centroid", pa.list_(pa.float32())),
    
    # 聚类质量指标
    pa.field("avg_intra_similarity", pa.float32()),  # 簇内平均相似度
    pa.field("min_intra_similarity", pa.float32()),  # 簇内最小相似度
    
    # 聚类参数（用于增量更新）
    pa.field("min_pair_sim_threshold", pa.float32()),  # 创建时使用的阈值
    
    # 时间戳
    pa.field("created_at", pa.timestamp('us')),
    pa.field("last_updated", pa.timestamp('us')),
])
```

### 2.2 聚类流程修改

#### 2.2.1 初始聚类

```python
def cluster_and_save_to_lance(
    vector_store: LanceVectorStore,
    cluster_store: LanceVectorStore,  # 新增：聚类元数据表
    domain: str,
    min_pair_sim: float = 0.6,
    max_size: int = 300,
    auto_evolve: bool = True
):
    # 1. 从 vector_store 读取该领域的所有向量
    vectors, metadata = vector_store.get_by_domain(domain)
    
    # 2. 执行 agglomerative 聚类
    labels, n_clusters = agglomerative_clustering(
        vectors, 
        min_pair_sim=min_pair_sim,
        max_size=max_size
    )
    
    # 3. 检查是否需要自动进化阈值
    if auto_evolve:
        large_clusters = sum(1 for label in range(n_clusters) 
                            if (labels == label).sum() > max_size)
        if large_clusters / n_clusters > 0.6:  # 超过60%的簇过大
            new_threshold = min_pair_sim + 0.02
            print(f"Auto-evolving threshold: {min_pair_sim} → {new_threshold}")
            return cluster_and_save_to_lance(
                vector_store, cluster_store, domain,
                min_pair_sim=new_threshold,
                max_size=max_size,
                auto_evolve=True
            )
    
    # 4. 构建聚类元数据并保存到 cluster_store
    for cluster_id in range(n_clusters):
        mask = (labels == cluster_id)
        cluster_metadata = build_cluster_metadata(
            domain=domain,
            local_cluster_id=cluster_id,
            vectors=vectors[mask],
            metadata=[metadata[i] for i in np.where(mask)[0]],
            min_pair_sim=min_pair_sim
        )
        cluster_store.add_record(cluster_metadata)
    
    # 5. 更新 vector_store 中的 cluster_id 字段
    update_cluster_labels(vector_store, domain, labels)
    
    return labels, n_clusters
```

#### 2.2.2 增量更新

```python
def incremental_clustering(
    vector_store: LanceVectorStore,
    cluster_store: LanceVectorStore,
    domain: str,
    new_paper_ids: List[str]
):
    """
    增量添加新论文到现有聚类
    
    策略：
    1. 为新论文生成向量（已在 vectorize_reasoning_chains 中完成）
    2. 对每条新思维链，找到最相似的现有聚类质心
    3. 如果相似度 >= min_pair_sim，加入该聚类
    4. 否则，创建新聚类
    """
    # 1. 获取新论文的所有思维链
    new_chains = vector_store.get_by_paper_ids(new_paper_ids, domain=domain)
    
    # 2. 获取现有聚类的质心
    existing_clusters = cluster_store.get_by_domain(domain)
    centroids = np.array([c["centroid"] for c in existing_clusters])
    thresholds = [c["min_pair_sim_threshold"] for c in existing_clusters]
    
    # 3. 为每条新链分配聚类
    for chain in new_chains:
        vector = chain["vector"]
        similarities = cosine_similarity(vector, centroids)
        best_idx = np.argmax(similarities)
        best_sim = similarities[best_idx]
        
        if best_sim >= thresholds[best_idx]:
            # 加入现有聚类
            cluster_id = existing_clusters[best_idx]["global_cluster_id"]
            assign_to_cluster(vector_store, cluster_store, chain, cluster_id)
        else:
            # 创建新聚类
            new_cluster_id = create_new_cluster(cluster_store, domain, chain)
            assign_to_cluster(vector_store, cluster_store, chain, new_cluster_id)
    
    # 4. 重新计算受影响聚类的质心和统计信息
    update_cluster_statistics(cluster_store, domain)
```

### 2.3 辅助函数

```python
def build_cluster_metadata(
    domain: str,
    local_cluster_id: int,
    vectors: np.ndarray,
    metadata: List[Dict],
    min_pair_sim: float
) -> Dict:
    """构建单个聚类的元数据"""
    from datetime import datetime
    
    # 提取路径和paper_id
    chain_xml_paths = [m["xml_path"] for m in metadata]
    paper_ids = list(set(m["paper_id"] for m in metadata))
    paper_md_paths = list(set(m["md_path"] for m in metadata))
    
    # 计算质心
    centroid = vectors.mean(axis=0)
    
    # 计算簇内相似度
    normalized = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    sim_matrix = normalized @ normalized.T
    avg_sim = sim_matrix.mean()
    min_sim = sim_matrix.min()
    
    return {
        "global_cluster_id": f"{domain}_{local_cluster_id}",
        "domain": domain,
        "local_cluster_id": local_cluster_id,
        "num_chains": len(metadata),
        "num_papers": len(paper_ids),
        "chain_xml_paths": chain_xml_paths,
        "paper_ids": paper_ids,
        "paper_md_paths": paper_md_paths,
        "centroid": centroid.tolist(),
        "avg_intra_similarity": float(avg_sim),
        "min_intra_similarity": float(min_sim),
        "min_pair_sim_threshold": min_pair_sim,
        "created_at": datetime.now(),
        "last_updated": datetime.now(),
    }
```

---

## 3. 配置文件修改

在 `step1_config.yaml` 中新增：

```yaml
# 聚类参数
clustering:
  algorithm: "agglomerative"
  agglomerative:
    min_pair_sim: 0.6          # 初始阈值
    max_size: 300              # 每个簇最大论文数
    auto_evolve: true          # 自动进化阈值
    evolve_threshold: 0.6      # 触发进化的大簇比例
    evolve_step: 0.02          # 每次进化的阈值增量
  
  # 聚类结果存储
  cluster_metadata_table: "cluster_metadata"
  
# 文件路径配置
paths:
  tos_prefix: "tos://paper_ocr"  # TOS 存储前缀
  xml_subdir: "xml"
  md_subdir: "md"
```

---

## 4. 实现优先级

### Phase 1: 基础功能（必须）
1. ✅ 修改 `schema.py`：新增 `xml_path`, `md_path` 字段
2. ✅ 修改 `vectorizer.py`：生成路径元数据
3. ✅ 新建 `CLUSTER_METADATA_SCHEMA`
4. ✅ 实现 `cluster_and_save_to_lance()` 基础版本（无自动进化）

### Phase 2: 自动进化（重要）
5. ✅ 实现阈值自动进化逻辑
6. ✅ 添加聚类质量监控

### Phase 3: 增量更新（重要）
7. ✅ 实现 `incremental_clustering()`
8. ✅ 实现质心更新和统计刷新

### Phase 4: 优化（可选）
9. ⏸ 大规模数据的两阶段聚类优化
10. ⏸ 聚类可视化和分析工具

---

## 5. 向后兼容性

- 保留现有的 JSON 输出格式（用于调试）
- 新增 Lance 表作为主要存储
- 提供迁移脚本：JSON → Lance

---

## 6. 测试计划

1. **单元测试**：
   - 路径生成正确性
   - 聚类元数据构建
   - 阈值进化逻辑

2. **集成测试**：
   - 完整 pipeline：向量化 → 聚类 → 保存
   - 增量更新：新增论文 → 分配聚类

3. **性能测试**：
   - 5万条链的聚类时间
   - 增量更新 1000 条链的时间

---

## 7. 迁移路径

对于已有数据：

```python
def migrate_existing_clusters_to_lance(
    old_json_path: Path,
    vector_store: LanceVectorStore,
    cluster_store: LanceVectorStore,
    domain: str
):
    """将现有 JSON 格式的聚类结果迁移到 Lance 表"""
    import json
    
    with open(old_json_path) as f:
        old_data = json.load(f)
    
    for cluster_id, chain_ids in old_data["clusters"].items():
        # 从 vector_store 获取这些链的元数据
        chains = vector_store.get_by_ids(chain_ids)
        vectors = np.array([c["vector"] for c in chains])
        metadata = [c["metadata"] for c in chains]
        
        # 构建并保存聚类元数据
        cluster_meta = build_cluster_metadata(
            domain=domain,
            local_cluster_id=int(cluster_id),
            vectors=vectors,
            metadata=metadata,
            min_pair_sim=0.6  # 使用默认值
        )
        cluster_store.add_record(cluster_meta)
```
