"""
文本工具模块 - 文本预处理和清洗

职责:
- 文本清洗（去除 HTML/XML 标签、规范化空白）
- 文本分词和去停用词
- 文本规范化（小写化、unicode 规范化）
- 文本截断（按字符数或 token 数）
- 科学术语的特殊处理（保留希腊字母、化学公式等）

关键函数:
- clean_step_text(): 清洗推理步骤文本
- normalize_text(): 文本规范化
- truncate_text(): 文本截断
- strip_xml_tags(): 去除 XML 标签
- tokenize(): 分词
"""
