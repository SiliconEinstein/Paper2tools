"""
全局配置模块 - 配置管理

职责:
- 加载 YAML 配置文件
- 提供默认配置值
- 配置验证
- 支持环境变量覆盖
- 路径解析（相对路径 -> 绝对路径）

关键类/函数:
- Config: 配置类（支持 dict-like 访问）
- load_config(): 加载 YAML 配置文件
- get_default_config(): 获取默认配置
- validate_config(): 验证配置合法性
"""
