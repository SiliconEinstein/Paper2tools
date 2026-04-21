"""
Step2 主流程 - 串联数据加载→工具匹配→XML增强→保存

职责:
- 加载配置文件
- 调用 data_loader 加载 reasoning_chain.xml 和工具信息
- 调用 tool_matcher 进行工具与步骤的匹配
- 调用 xml_enricher 在 XML 中注入工具引用
- 保存增强后的 XML 文件
- 打印进度信息和匹配统计

关键函数:
- run_step2_pipeline(): 主流程入口
- save_enriched_xml(): 保存增强后的 XML
"""
