"""
工作流提取模块 - 从单篇论文的增强数据中提取 workflow 实例

职责:
- 从增强后的 reasoning_chain.xml 中提取工具使用序列
- 从 ptlink 中提取工具链（prereq + compute）
- 构建 workflow 实例（工具序列 + 研究问题 + 上下文）
- 支持多种 workflow 表示（线性链、DAG、树）
- 计算 workflow 的特征向量（用于后续聚合）

关键类/函数:
- WorkflowExtractor: 工作流提取器类
- extract_from_ptlink(): 从 ptlink 提取工具链
- extract_from_enriched_xml(): 从增强 XML 提取
- WorkflowInstance: workflow 实例数据结构
- compute_workflow_signature(): 计算 workflow 签名
"""
