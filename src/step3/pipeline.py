"""
Step3 主流程 - 串联数据加载→workflow提取→聚合→保存

职责:
- 加载配置文件
- 调用 data_loader 加载 Step2 输出的增强数据
- 调用 workflow_extractor 逐篇提取 workflow 实例
- 调用 workflow_aggregator 跨论文聚合
- 保存 workflow 库和统计信息
- 打印进度信息和聚合统计

关键函数:
- run_step3_pipeline(): 主流程入口
- save_workflow_library(): 保存 workflow 库
"""
