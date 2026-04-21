"""
向量化模块 - 将文本转换为向量表示

职责:
- 封装多种 embedding 模型（OpenAI embedding, sentence-transformers, 本地模型等）
- 提供统一的接口: text -> vector
- 支持批量向量化（带进度条）
- 向量缓存（避免重复计算）

关键类/函数:
- Vectorizer (基类): 定义统一接口
- OpenAIVectorizer: 调用 OpenAI embedding API
- SentenceTransformerVectorizer: 使用 sentence-transformers 本地模型
- batch_vectorize(): 批量向量化入口
"""
