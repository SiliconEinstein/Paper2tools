"""
数据加载模块 - 加载 reasoning_chain.xml 和工具信息

职责:
- 加载 reasoning_chain.xml（原始推理链）
- 加载 _tools_extract_result.json（Stage2 工具提取结果）
- 解析工具信息（tools[], ptlink[]）
- 构建工具索引（tool_id -> tool_info）
- 支持批量加载多个论文的数据

关键类/函数:
- load_reasoning_and_tools(): 加载单篇论文的数据
- batch_load_data(): 批量加载
- ToolInfo: 工具信息数据结构
- build_tool_index(): 构建工具索引
"""
