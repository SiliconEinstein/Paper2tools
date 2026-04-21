"""
Step1 主流程 - 串联数据加载→向量化→聚类→保存

职责:
- 加载配置文件
- 调用 data_loader 加载推理步骤
- 调用 vectorizer 进行向量化
- 调用 clustering 进行聚类
- 保存结果（向量、聚类标签、分析报告）
- 打印进度信息

关键函数:
- run_step1_pipeline(): 主流程入口
- save_results(): 保存聚类结果
"""
