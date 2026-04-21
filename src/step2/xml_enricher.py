"""
XML 增强模块 - 在 reasoning_chain.xml 中注入工具引用

职责:
- 解析原始 reasoning_chain.xml
- 在匹配的 <step> 节点中插入 <ref type="tool" tool_id="TX">tool_name</ref>
- 在 <conclusion_reasoning> 末尾添加 <tools> 节点（汇总该结论用到的工具）
- 保持 XML 格式和缩进
- 验证增强后的 XML 格式正确性

关键类/函数:
- XMLEnricher: XML 增强器类
- enrich_step(): 为单个步骤注入工具引用
- add_tools_section(): 添加 <tools> 汇总节点
- validate_enriched_xml(): 验证 XML 格式
"""
