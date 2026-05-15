# Workflower 性能优化方案

## 问题诊断

当前处理单个 cluster 耗时 10-20 分钟，处理 92 个 cluster 需要 13.5-27 小时。

### 瓶颈识别

| 阶段 | 当前耗时 | 瓶颈 |
|------|---------|------|
| Phase 1 元数据提取 | 1-2 分钟 | 逐文件读取 + 正则匹配 |
| Phase 2 深度提取 | 5-10 分钟 | 串行 LLM 调用（13 篇论文） |
| Phase 3 LaTeX 生成 | 3-5 分钟 | 单次生成大文档 + 编译 |
| **总计** | **10-20 分钟** | |

## 优化策略

### 1. Phase 1 优化：批量元数据提取

**当前**：
```python
for md_file in md_files:
    with open(md_file) as f:
        lines = [f.readline() for _ in range(100)]
    # 正则匹配提取
```

**优化后**：
```python
# 一次性批量读取所有 MD 文件头部
import subprocess
result = subprocess.run(
    ['head', '-50'] + [str(f) for f in md_files],
    capture_output=True, text=True
)
# 批量解析
```

**预期提升**：1-2 分钟 → 10-20 秒

### 2. Phase 2 优化：并行提取 + 缓存

**当前**：串行处理 13 篇论文，每篇调用 1 次 LLM

**优化方案 A**：批量提取（推荐）
```python
# 将 13 篇论文的 chain_text 合并为一个 prompt
prompt = f"""
从以下 13 篇论文的推理链中提取信息：

Paper 1 (Zhang_2023):
{chain_text_1}

Paper 2 (Liu_2022):
{chain_text_2}

...

对每篇论文输出：
- algorithm_layer: [...]
- implementation_layer: {...}
- gaps_noted: [...]
"""
# 一次 LLM 调用返回所有论文的提取结果
```

**优化方案 B**：并行调用（备选）
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(extract_paper, chain) for chain in a_chains]
    results = [f.result() for f in futures]
```

**预期提升**：5-10 分钟 → 1-2 分钟（方案 A）或 2-4 分钟（方案 B）

### 3. Phase 3 优化：分段生成 + 跳过编译

**当前**：一次性生成完整 LaTeX（8-15 页）

**优化后**：
1. **分段生成**：引言 → 各阶段 → 结论，逐段生成并拼接
2. **跳过 PDF 编译**：只生成 .tex 文件，用户需要时再编译
3. **决策树并行**：在生成 LaTeX 的同时渲染决策树

```python
# 并行执行
import asyncio

async def phase3():
    tasks = [
        generate_latex_sections(),  # 分段生成
        render_decision_tree(),      # 并行渲染
    ]
    await asyncio.gather(*tasks)
    
    # 跳过 xelatex 编译（可选）
    # compile_pdf()  # 用户手动执行
```

**预期提升**：3-5 分钟 → 1-2 分钟

### 4. 全局优化：增量处理 + 断点续传

**问题**：处理 92 个 cluster 时，中断后需要重新开始

**方案**：
```python
# 在 workflow_tasks.json 中记录每个 cluster 的阶段完成状态
{
  "cluster_105": {
    "phase1_done": true,
    "phase2_done": false,  # 中断点
    "phase3_done": false
  }
}

# 恢复时跳过已完成阶段
if task['phase1_done']:
    print("Phase 1 already done, skipping...")
else:
    run_phase1()
```

### 5. 质量 vs 速度权衡

**快速模式**（推荐用于批量处理）：
- Phase 2 使用批量提取（方案 A）
- Phase 3 跳过 PDF 编译
- 只生成 .tex 和 .png，用户需要时再编译 PDF

**完整模式**（用于单个 cluster 精细化）：
- Phase 2 逐篇深度提取
- Phase 3 完整编译 PDF
- 包含所有质量检查

## 实施优先级

| 优化项 | 预期提升 | 实施难度 | 优先级 |
|--------|---------|---------|--------|
| Phase 2 批量提取 | 5-10 分钟 → 1-2 分钟 | 中 | **P0** |
| Phase 3 跳过编译 | 节省 30-60 秒 | 低 | **P0** |
| Phase 1 批量读取 | 1-2 分钟 → 10-20 秒 | 低 | P1 |
| 增量处理 | 避免重复工作 | 中 | P1 |
| Phase 3 分段生成 | 1-2 分钟节省 | 高 | P2 |

## 预期效果

**优化前**：10-20 分钟/cluster × 92 = 15-30 小时

**优化后（P0 项）**：
- Phase 1: 1-2 分钟
- Phase 2: 1-2 分钟（批量提取）
- Phase 3: 1-2 分钟（跳过编译）
- **总计**: 3-6 分钟/cluster × 92 = **4.6-9.2 小时**

**优化后（P0+P1 项）**：
- Phase 1: 10-20 秒
- Phase 2: 1-2 分钟
- Phase 3: 1-2 分钟
- **总计**: 2-4 分钟/cluster × 92 = **3-6 小时**

## 实施建议

1. **立即实施 P0 优化**：Phase 2 批量提取 + Phase 3 跳过编译
2. **测试单个 cluster**：验证质量不下降
3. **批量处理剩余 81 个 cluster**
4. **后续按需编译 PDF**：用户需要时运行 `xelatex review_cluster_N.tex`
