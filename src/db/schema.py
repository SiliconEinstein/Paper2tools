"""
PyArrow Schema 定义 - 独立于 lancedb，避免循环依赖

## 设计原则

1. **独立性**: 此文件不导入 lancedb，只依赖 pyarrow
   - 原因: 在多进程环境下，lancedb 可能有导入问题
   - 参考: paper2tools v1 的 src/db/schema.py 设计

2. **完整性**: 每个 schema 都包含所有必需字段
   - 主键字段（id）
   - 向量字段（vector）
   - 元数据字段（paper_id, journal, etc.）

3. **类型安全**: 使用 PyArrow 的强类型系统
   - string: 文本字段
   - int32/int64: 整数字段
   - float32: 向量元素（节省空间）
   - bool_: 布尔标志
   - timestamp: 时间戳
   - list_(pa.float32()): 向量数组

## Schema 列表

- STEP_EMBEDDING_SCHEMA: Step1 推理步骤的 embedding 向量
- CLUSTER_CENTER_SCHEMA: 聚类中心向量
- PROGRESS_TRACKER_SCHEMA: 论文处理进度追踪
- TOOL_MATCH_SCHEMA: Step2 工具匹配结果
"""

import pyarrow as pa


# ============================================================================
# Step1: 推理步骤 Embedding 向量存储
# ============================================================================

CHAIN_EMBEDDING_SCHEMA = pa.schema([
    # 主键：唯一标识一条思维链
    # 格式: {paper_id}_{conclusion_id}
    # 例: "1234567890_c1"
    pa.field("chain_id", pa.string()),

    # 论文元数据
    pa.field("paper_id", pa.string()),
    pa.field("journal", pa.string()),           # 原始期刊名（细粒度，必填）
    pa.field("domain", pa.string()),            # 领域标签（粗粒度，可选，允许空字符串）
    pa.field("conclusion_id", pa.string()),
    pa.field("conclusion_title", pa.string()),

    # 文件路径（完整路径，用于后续检索和加载）
    pa.field("xml_path", pa.string()),          # 如: "tos://paper_ocr/xml/1234567890_c1.xml"
    pa.field("md_path", pa.string()),           # 如: "tos://paper_ocr/md/1234567890.md"

    # 思维链完整文本（所有 step 拼接）
    pa.field("chain_text", pa.string()),

    # Embedding 向量
    # 维度: 512 (DashScope text-embedding-v4) 或 1536 (text-embedding-v1)
    pa.field("vector", pa.list_(pa.float32())),

    # 聚类标签（初始为 -1，表示未聚类）
    # 注意：cluster_id 是领域内的局部 ID，不同领域可以有相同的 cluster_id
    pa.field("cluster_id", pa.int32()),

    # 思维链统计信息
    pa.field("num_steps", pa.int32()),          # 步骤数量
    pa.field("has_citations", pa.bool_()),      # 是否有文献引用
    pa.field("has_figures", pa.bool_()),        # 是否有图表引用
])

# 保留旧名称作为别名，向后兼容
STEP_EMBEDDING_SCHEMA = CHAIN_EMBEDDING_SCHEMA


# ============================================================================
# Step1: 聚类元数据存储（新增）
# ============================================================================

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


# ============================================================================
# Step1: 聚类中心存储
# ============================================================================

CLUSTER_CENTER_SCHEMA = pa.schema([
    # 聚类 ID（从 0 开始）
    pa.field("cluster_id", pa.int32()),

    # 聚类中心向量（质心）
    pa.field("center_vector", pa.list_(pa.float32())),

    # 聚类统计信息
    pa.field("size", pa.int32()),               # 聚类包含的步骤数
    pa.field("avg_distance", pa.float32()),     # 平均距离（紧密度）

    # 聚类语义标签（可选，由 LLM 生成）
    pa.field("label", pa.string()),
    pa.field("description", pa.string()),       # 聚类描述

    # 代表性样本（最接近中心的 3 个 step_id）
    pa.field("representative_samples", pa.list_(pa.string())),
])


# ============================================================================
# 进度追踪表
# ============================================================================

PROGRESS_TRACKER_SCHEMA = pa.schema([
    # 论文 ID（主键）
    pa.field("paper_id", pa.string()),

    # 各阶段完成状态
    pa.field("step1_completed", pa.bool_()),
    pa.field("step2_completed", pa.bool_()),
    pa.field("step3_completed", pa.bool_()),

    # 统计信息
    pa.field("num_conclusions", pa.int32()),    # 结论数
    pa.field("num_steps", pa.int32()),          # 推理步骤数
    pa.field("num_tools_matched", pa.int32()),  # 匹配到的工具数

    # 时间戳
    pa.field("created_at", pa.timestamp('us')),
    pa.field("last_updated", pa.timestamp('us')),

    # 错误信息（如果处理失败）
    pa.field("error_message", pa.string()),
])


# ============================================================================
# Step2: 工具匹配结果存储
# ============================================================================

TOOL_MATCH_SCHEMA = pa.schema([
    # 匹配 ID（主键）
    # 格式: {step_id}_{tool_id}
    pa.field("match_id", pa.string()),

    # 关联的步骤和工具
    pa.field("step_id", pa.string()),
    pa.field("tool_id", pa.string()),
    pa.field("tool_name", pa.string()),

    # 匹配置信度（0-1）
    pa.field("confidence", pa.float32()),

    # 匹配方法
    # 枚举值: "exact_match", "fuzzy_match", "semantic_match", "llm_match"
    pa.field("match_method", pa.string()),

    # 匹配上下文（用于调试）
    pa.field("matched_text_span", pa.string()),  # 匹配到的文本片段
])


# ============================================================================
# Step3: Workflow Embedding 向量存储
# ============================================================================

WORKFLOW_EMBEDDING_SCHEMA = pa.schema([
    # 主键：全局唯一的 workflow ID
    # 格式: {domain}_{cluster_id}
    # 例: "bioinformatics_cluster_6", "Superconductivity_cluster_60"
    pa.field("workflow_id", pa.string()),

    # 聚类信息
    pa.field("cluster_id", pa.string()),       # "cluster_6"
    pa.field("domain", pa.string()),           # "bioinformatics"

    # Workflow 基本信息
    pa.field("workflow_name", pa.string()),
    pa.field("workflow_name_en", pa.string()),
    pa.field("problem_description", pa.string()),
    pa.field("problem_description_en", pa.string()),

    # Embedding 向量（problem_description 的向量）
    pa.field("vector", pa.list_(pa.float32(), list_size=1024)),

    # 检索字段
    pa.field("keywords", pa.list_(pa.string())),
    pa.field("keywords_en", pa.list_(pa.string())),
    pa.field("input_types", pa.list_(pa.string())),
    pa.field("output_types", pa.list_(pa.string())),
    pa.field("key_methods", pa.string()),      # JSON string: [{"name": "...", "frequency": 0.8}, ...]
    pa.field("main_stages", pa.list_(pa.string())),

    # 统计信息
    pa.field("num_papers", pa.int32()),
    pa.field("num_chains", pa.int32()),
    pa.field("avg_intra_similarity", pa.float32()),

    # 元数据
    pa.field("creation_date", pa.string()),
    pa.field("workflow_dir", pa.string()),     # 完整路径
])


# ============================================================================
# 辅助函数
# ============================================================================

def get_schema_by_name(schema_name: str) -> pa.Schema:
    """
    根据名称获取 schema

    Args:
        schema_name: schema 名称（如 "step_embedding"）

    Returns:
        PyArrow Schema 对象

    Raises:
        ValueError: 如果 schema 名称不存在
    """
    schemas = {
        "step_embedding": STEP_EMBEDDING_SCHEMA,
        "chain_embedding": CHAIN_EMBEDDING_SCHEMA,
        "cluster_metadata": CLUSTER_METADATA_SCHEMA,
        "cluster_center": CLUSTER_CENTER_SCHEMA,
        "progress_tracker": PROGRESS_TRACKER_SCHEMA,
        "tool_match": TOOL_MATCH_SCHEMA,
        "workflow_embedding": WORKFLOW_EMBEDDING_SCHEMA,
    }

    if schema_name not in schemas:
        raise ValueError(
            f"Unknown schema name: {schema_name}. "
            f"Available: {list(schemas.keys())}"
        )

    return schemas[schema_name]


def validate_data_against_schema(data: dict, schema: pa.Schema) -> bool:
    """
    验证数据是否符合 schema

    Args:
        data: 数据字典
        schema: PyArrow Schema

    Returns:
        True 如果数据符合 schema

    Raises:
        ValueError: 如果数据不符合 schema（缺少字段、类型不匹配等）
    """
    schema_fields = {field.name for field in schema}
    data_fields = set(data.keys())

    # 检查缺少的必需字段
    missing_fields = schema_fields - data_fields
    if missing_fields:
        raise ValueError(f"Missing required fields: {missing_fields}")

    # 检查多余的字段（警告，不报错）
    extra_fields = data_fields - schema_fields
    if extra_fields:
        import warnings
        warnings.warn(f"Extra fields will be ignored: {extra_fields}")

    return True
