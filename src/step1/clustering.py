"""
聚类算法模块 - 对向量进行语义聚类

职责:
- 封装多种聚类算法（K-means, DBSCAN, Hierarchical, HDBSCAN）
- 提供自动选择最优 k 值的方法（肘部法、轮廓系数）
- 聚类结果的评估指标计算
- 聚类标签的语义解释（可选，基于 LLM）

关键类/函数:
- ClusteringAlgorithm (基类): 定义统一接口
- KMeansClustering: K-means 聚类
- DBSCANClustering: DBSCAN 密度聚类
- HierarchicalClustering: 层次聚类
- evaluate_clustering(): 计算聚类质量指标
- find_optimal_k(): 自动搜索最优聚类数
"""
