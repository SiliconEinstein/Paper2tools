"""
数据加载模块 - 加载 Step2 输出的增强数据

职责:
- 加载 reasoning_chain.enriched.xml（Step2 输出）
- 加载 _tools_extract_result.json（工具信息）
- 解析增强后的 XML 中的工具引用
- 构建完整的数据结构（步骤+工具+工具链）
- 支持批量加载多个论文的数据

关键类/函数:
- load_enriched_data(): 加载单篇论文的增强数据
- batch_load_enriched_data(): 批量加载
- EnrichedPaperData: 增强数据结构
"""
