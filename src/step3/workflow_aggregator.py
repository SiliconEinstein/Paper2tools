"""
工作流聚合模块 - 跨论文聚合相似的 workflow

职责:
- 基于工具链签名（工具组成+顺序）聚合 workflow
- 计算 workflow 之间的相似度
- 合并相似的 workflow 实例
- 生成 workflow 的代表性描述（基于多个实例）
- 统计每个 workflow 的出现频率、适用场景

关键类/函数:
- WorkflowAggregator: 工作流聚合器类
- compute_similarity(): 计算两个 workflow 的相似度
- aggregate_workflows(): 聚合相似 workflow
- generate_workflow_description(): 生成代表性描述
- WorkflowLibrary: workflow 库数据结构
"""
