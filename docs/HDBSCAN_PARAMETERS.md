# HDBSCAN 参数设置指南

## 核心参数

### 1. `min_cluster_size` (最小簇大小)

**含义**：一个簇至少需要包含多少个样本才能被认为是有效簇。

**影响**：
- **值越大**：簇越少，每个簇更大，更保守（只保留大的、明显的簇）
- **值越小**：簇越多，能发现更细粒度的模式，但可能产生很多小簇

**推荐设置**：
```python
# 数据量 < 1000
min_cluster_size = 5-10

# 数据量 1000-10000
min_cluster_size = 10-50

# 数据量 > 10000
min_cluster_size = 50-100
```

**超导领域（1000篇论文）**：
- 初始值：`min_cluster_size = 15`
- 理由：1000篇论文，预期有 20-50 个方法类别，每个类别平均 20-50 篇

### 2. `min_samples` (最小样本数)

**含义**：一个点的邻域内至少需要多少个样本，才能被认为是核心点（core point）。

**影响**：
- **值越大**：对噪声更鲁棒，但可能将边缘样本标记为噪声
- **值越小**：更敏感，能捕获更多边缘样本，但可能将噪声纳入簇中

**推荐设置**：
```python
# 保守策略（噪声容忍度低）
min_samples = min_cluster_size

# 平衡策略（推荐）
min_samples = max(5, min_cluster_size // 3)

# 激进策略（尽量少噪声点）
min_samples = 3-5
```

**超导领域**：
- 初始值：`min_samples = 5`
- 理由：向量空间中，5个邻居足以判断密度

### 3. `metric` (距离度量)

**含义**：计算样本间距离的方法。

**常用选项**：
- `'euclidean'`（默认）：欧氏距离，适合大多数场景
- `'cosine'`：余弦距离，**推荐用于文本向量**
- `'manhattan'`：曼哈顿距离

**超导领域**：
- 使用 `'cosine'`
- 理由：思维链向量是文本 embedding，余弦距离更能反映语义相似度

### 4. `cluster_selection_epsilon` (簇选择阈值)

**含义**：距离阈值，小于此值的簇会被合并。

**影响**：
- **值越大**：簇越少（更多合并）
- **值越小**：簇越多（更少合并）
- **默认 0.0**：不强制合并

**推荐设置**：
```python
# 不设置（让算法自动决定）
cluster_selection_epsilon = 0.0

# 如果簇太多太碎，可以设置
cluster_selection_epsilon = 0.1-0.3  # 对于 cosine 距离
```

### 5. `cluster_selection_method` (簇选择方法)

**含义**：如何从层次结构中选择簇。

**选项**：
- `'eom'`（默认，Excess of Mass）：选择"质量过剩"最大的簇，更保守
- `'leaf'`：选择叶子节点作为簇，更激进，簇更多更小

**推荐**：
- 默认 `'eom'`，除非你想要更多细粒度的簇

## 超导领域推荐配置

```python
HDBSCANClustering(
    min_cluster_size=15,        # 1000篇论文，预期20-50个簇
    min_samples=5,              # 5个邻居判断密度
    metric='cosine',            # 文本向量用余弦距离
    cluster_selection_epsilon=0.0,  # 不强制合并
    cluster_selection_method='eom'  # 保守选择
)
```

## 调优策略

### 问题 1：簇太少（< 10个）

**症状**：大量样本被标记为噪声（label=-1）

**解决**：
1. 降低 `min_cluster_size`（15 → 10 → 5）
2. 降低 `min_samples`（5 → 3）
3. 改用 `cluster_selection_method='leaf'`

### 问题 2：簇太多太碎（> 100个）

**症状**：很多小簇（size < 10），语义相似的被分开

**解决**：
1. 增大 `min_cluster_size`（15 → 30 → 50）
2. 设置 `cluster_selection_epsilon=0.2`（合并相近簇）

### 问题 3：噪声点太多（> 20%）

**症状**：大量样本 label=-1

**解决**：
1. 降低 `min_samples`（5 → 3）
2. 降低 `min_cluster_size`
3. 检查向量质量（是否有异常值）

### 问题 4：新方法被合并到旧簇

**症状**：明显不同的方法被归为一类

**解决**：
1. 降低 `cluster_selection_epsilon`（0.2 → 0.0）
2. 改用 `cluster_selection_method='leaf'`
3. 检查向量区分度（可能需要更好的 embedding 模型）

## 评估指标

```python
# 1. 簇数量
n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
print(f"发现 {n_clusters} 个簇")

# 2. 噪声比例
noise_ratio = (labels == -1).sum() / len(labels)
print(f"噪声点比例: {noise_ratio:.1%}")

# 3. 簇大小分布
cluster_sizes = pd.Series(labels[labels != -1]).value_counts()
print(f"簇大小: min={cluster_sizes.min()}, max={cluster_sizes.max()}, median={cluster_sizes.median()}")

# 4. Silhouette Score（轮廓系数）
from sklearn.metrics import silhouette_score
score = silhouette_score(vectors[labels != -1], labels[labels != -1], metric='cosine')
print(f"Silhouette Score: {score:.3f}")  # 越接近1越好
```

## 与 K-means 对比

| 维度 | K-means | HDBSCAN |
|------|---------|---------|
| 簇数量 | 固定（需预设k） | 自动发现 |
| 噪声处理 | 强制分配 | 标记为噪声 |
| 簇形状 | 球形 | 任意形状 |
| 新方法 | 强制合并 | 可标记为噪声或新簇 |
| 速度 | 快（O(nk)） | 慢（O(n²)） |
| 适用场景 | 已知类别数 | 探索性分析 |

**结论**：HDBSCAN 更适合你的需求（不知道有多少类方法，不想强制合并新方法）。
