"""
Step1 主入口: CLI 命令行接口

功能:
- 解析命令行参数
- 根据参数选择运行 Step1/Step2/Step3 或全流程
- 加载对应的配置文件
- 调用相应的 pipeline

使用示例:
    python -m src.main --step 1 --config configs/step1_config.yaml
    python -m src.main --step all  # 运行全部步骤
"""
