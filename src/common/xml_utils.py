"""
XML 工具模块 - 统一的 XML 解析/序列化接口

职责:
- 解析 reasoning_chain.xml 格式的 XML 文件
- 提取 <step>, <conclusion>, <tools> 等节点
- XML 节点的增/删/改操作
- XML 序列化（保持格式和缩进）
- XML 验证（结构合法性检查）

关键函数:
- parse_reasoning_xml(): 解析 reasoning_chain XML
- extract_steps(): 提取所有 <step> 节点
- extract_conclusions(): 提取所有 <conclusion> 节点
- serialize_xml(): XML 序列化
- get_step_text(): 获取步骤的纯文本内容（去除子标签）
"""
