"""
工具匹配模块 - 将工具与推理步骤关联

职责:
- 基于文本匹配（工具名出现在步骤文本中）
- 基于语义相似度（向量相似度匹配）
- 基于 ptlink 中的 evidence 字段（工具链证据匹配）
- 支持多种匹配策略组合
- 计算匹配置信度

关键类/函数:
- ToolMatcher (基类): 定义统一接口
- TextBasedMatcher: 基于文本匹配
- SemanticMatcher: 基于语义相似度
- EvidenceBasedMatcher: 基于 ptlink evidence
- HybridMatcher: 组合多种策略
- match_tools_to_steps(): 主匹配函数
"""
