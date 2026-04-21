"""
JSON 工具模块 - JSON 读写和 schema 验证

职责:
- 读写 _tools_extract_result.json 格式的 JSON 文件
- JSON Schema 验证（确保工具数据格式正确）
- 提取 tools[], ptlink[], par[] 等结构
- 安全的 JSON 解析（处理格式异常）

关键函数:
- load_tool_json(): 加载工具 JSON 文件
- extract_tools(): 提取 tools 列表
- extract_ptlinks(): 提取 ptlink 列表
- validate_tool_schema(): JSON Schema 验证
- safe_json_load(): 安全的 JSON 加载
"""
