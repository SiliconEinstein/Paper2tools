"""
数据加载模块 - 从 TOS 加载指定期刊的 reasoning_chain.xml 文件

## 核心职责

1. **期刊筛选**: 从 domain_journals.yaml 读取目标期刊列表
2. **论文 ID 映射**: 复用 paper2tools 的 JournalMapper（已有缓存机制）
3. **ID 列表持久化**: 将筛选后的 paper_id_list 保存到本地（按领域分别保存）
4. **文件加载**: 从 TOS 读取 reasoning_chain.xml 文件
5. **思维链提取**: 解析 XML，提取每个独立的 <conclusion_reasoning> 块
6. **数据结构化**: 构建 ReasoningChain 数据结构

## 数据流（两阶段）

### 阶段 1: 构建 paper_id_list（只需执行一次）

```
domain_journals.yaml (期刊列表)
    ↓
JournalMapper.load_or_build()
    → 从本地缓存加载 paper_id → journal 映射
    → 缓存路径: data/cache/journal_mapping.json（300万条）
    ↓
JournalMapper.get_domain_paper_ids(mapping, target_journals)
    → 筛选出目标期刊的 paper_id 集合
    ↓
保存到本地: data/cache/paper_ids_{domain}.json
    → 例: data/cache/paper_ids_bioinformatics.json
    → 包含 paper_ids 列表 + 统计信息
```

### 阶段 2: 加载思维链数据（可重复执行）

```
从本地加载 paper_ids_{domain}.json
    ↓
TOS: paper_ocr/xml/{paper_id}_reasoning_chain.xml
    ↓
解析每个 <conclusion_reasoning> 块
    ↓
提取所有 <step> 节点的文本
    ↓
ReasoningChain 数据结构列表
    ↓
保存到本地缓存: data/step1_output/reasoning_chains_{domain}.jsonl
```

## 关键数据结构

### ReasoningChain
表示一个独立的思维链（对应一个 <conclusion_reasoning> 块）

```python
@dataclass
class ReasoningChain:
    paper_id: str                    # 论文 ID
    journal: str                     # 期刊名
    conclusion_id: str               # 结论 ID（XML 中的 conclusion_id 属性）
    conclusion_title: str            # 结论标题
    conclusion_text: str             # 结论文本
    steps: List[ReasoningStep]       # 推理步骤列表
    raw_xml: str                     # 原始 XML 片段（用于后续处理）
```

### ReasoningStep
表示一个推理步骤（对应一个 <step> 节点）

```python
@dataclass
class ReasoningStep:
    step_id: str                     # 步骤 ID（XML 中的 id 属性）
    text: str                        # 步骤的纯文本内容（去除所有子标签）
    raw_text: str                    # 原始文本（保留 <ref> 等标签）
    has_tool_refs: bool              # 是否已有工具引用
    has_citations: bool              # 是否有文献引用
    has_figures: bool                # 是否有图表引用
```

## 核心函数设计

### 1. load_journal_config(config_path: Path, domain: str) -> List[str]
加载期刊配置文件，返回指定领域的期刊列表

**输入**:
- config_path: domain_journals.yaml 路径
- domain: 领域名（如 "bioinformatics"）
**输出**: 期刊名列表
**逻辑**:
- 使用 yaml.safe_load() 读取配置
- 提取 config[domain]["journals"] 列表
- 返回期刊名列表

### 2. build_paper_id_list(
    journal_mapper,
    target_journals: List[str],
    domain: str,
    cache_dir: Path,
    force_rebuild: bool = False
) -> Tuple[List[str], Dict]
构建并持久化目标期刊的论文 ID 列表（只需执行一次）

**核心思想**: paper_id_list 构建成本高（需加载 300 万条映射并筛选），
但结果是稳定的——同一领域、同一期刊列表下，ID 列表不会变。
所以**第一次构建后保存到本地文件，后续直接读取**。

**输入**:
- journal_mapper: JournalMapper 实例（来自 paper2tools）
- target_journals: 目标期刊列表
- domain: 领域名
- cache_dir: 缓存目录（data/cache/）
- force_rebuild: 是否强制重建
**输出**: (paper_ids, metadata) 元组
**持久化路径**: `{cache_dir}/paper_ids_{domain}.json`
  - 例: `data/cache/paper_ids_bioinformatics.json`
  - 文件格式:
    ```json
    {
      "domain": "bioinformatics",
      "journals": ["Bioinformatics", "PLOS Computational Biology", ...],
      "created_at": "2026-04-21T15:30:00",
      "total_count": 76598,
      "per_journal_count": {"Bioinformatics": 16793, ...},
      "paper_ids": ["1234567890", "0987654321", ...]
    }
    ```

**逻辑**:
```
1. 检查本地文件是否存在
   cache_path = cache_dir / f"paper_ids_{domain}.json"
   if cache_path.exists() and not force_rebuild:
       return load_paper_id_list(cache_path)

2. 加载 paper_id → journal 全量映射
   ★ 调用 journal_mapper.load_or_build()
   - 它内部已有缓存机制（data/cache/journal_mapping.json，300万条）
   - 如果缓存存在，直接从本地 JSON 加载（秒级完成）
   - 如果缓存不存在，从 TOS batch_csv 重建（分钟级）

3. 筛选 paper_id
   paper_ids_set = journal_mapper.get_domain_paper_ids(mapping, set(target_journals))
   paper_ids = sorted(paper_ids_set)  # 排序保证稳定性

4. 统计每个期刊的论文数
   per_journal_count = {}
   for pid in paper_ids:
       journal = mapping[pid]
       per_journal_count[journal] = per_journal_count.get(journal, 0) + 1

5. 保存到本地（含统计信息）
   save_paper_id_list(cache_path, domain, target_journals, paper_ids, per_journal_count)

6. 打印统计信息
   - 总论文数
   - 每个期刊的论文数

7. 返回 (paper_ids, metadata)
```

### 3. load_paper_id_list(cache_path: Path) -> Tuple[List[str], Dict]
从本地缓存加载论文 ID 列表

**输入**: 缓存文件路径
**输出**: (paper_ids, metadata) 元组
**逻辑**:
- 读取 JSON 文件
- 提取 paper_ids 列表
- 提取 metadata（domain, journals, counts 等）
- 打印统计摘要
- 返回 (paper_ids, metadata)

### 4. save_paper_id_list(
    cache_path: Path,
    domain: str,
    journals: List[str],
    paper_ids: List[str],
    per_journal_count: Dict[str, int]
)
保存论文 ID 列表到本地

**输入**: 路径、domain名、期刊列表、paper_ids、每期刊统计
**输出**: 无（写入 JSON 文件）
**逻辑**:
- 构建 JSON 对象（含 metadata + paper_ids）
- 写入文件
- 打印保存信息

### 5. load_reasoning_chain_xml(
    tos_client,
    bucket: str,
    paper_id: str
) -> Optional[ET.Element]
从 TOS 加载单个 reasoning_chain.xml 文件

**输入**:
- tos_client: TOS SDK 客户端（tos.TosClientV2）
- bucket: TOS bucket 名（wenyon-paper）
- paper_id: 论文 ID
**输出**: lxml.etree.Element 或 None（文件不存在时）
**逻辑**:
- 构建 TOS key: `paper_ocr/xml/{paper_id}_reasoning_chain.xml`
- 使用 tos_client.get_object(bucket, key) 读取文件
- 使用 lxml.etree.fromstring() 解析 XML
- 异常处理：文件不存在、XML 格式错误
- 返回根节点 <inference_unit>

### 6. parse_reasoning_chains(
    xml_root: ET.Element,
    paper_id: str,
    journal: str
) -> List[ReasoningChain]
从 XML 根节点解析所有思维链

**输入**:
- xml_root: <inference_unit> 根节点
- paper_id: 论文 ID
- journal: 期刊名
**输出**: ReasoningChain 列表
**逻辑**:
- 遍历所有 <conclusion_reasoning> 节点
- 对每个节点：
  - 提取 conclusion_id 属性
  - 提取 <conclusion> 节点的 title 和文本
  - 调用 parse_reasoning_steps() 提取步骤列表
  - 保存原始 XML 片段（ET.tostring()）
  - 构建 ReasoningChain 对象
- 返回列表

### 7. parse_reasoning_steps(reasoning_node: ET.Element) -> List[ReasoningStep]
从 <reasoning> 节点解析所有步骤

**输入**: <reasoning> 节点
**输出**: ReasoningStep 列表
**逻辑**:
- 遍历所有 <step> 子节点
- 对每个 <step>：
  - 提取 id 属性
  - 提取纯文本内容（使用 itertext() 并去除子标签）
  - 保存原始文本（包含子标签）
  - 检测是否有 <ref type="tool">（has_tool_refs）
  - 检测是否有 <ref type="citation">（has_citations）
  - 检测是否有 <ref type="figure">（has_figures）
  - 构建 ReasoningStep 对象
- 返回列表

### 8. extract_step_text(step_node: ET.Element) -> str
提取步骤的纯文本内容

**输入**: <step> 节点
**输出**: 纯文本字符串
**逻辑**:
- 使用 step_node.itertext() 获取所有文本片段
- 拼接并规范化空白（多个空格/换行 → 单个空格）
- 去除首尾空白
- 返回纯文本

### 9. batch_load_reasoning_chains(
    paper_ids: List[str],
    paper_journal_mapping: Dict[str, str],
    tos_client,
    bucket: str,
    batch_size: int = 100,
    max_workers: int = 10,
    verbose: bool = True
) -> List[ReasoningChain]
批量加载多个论文的思维链（支持并行）

**输入**:
- paper_ids: 论文 ID 列表
- paper_journal_mapping: paper_id → journal 映射
- tos_client: TOS SDK 客户端
- bucket: TOS bucket 名
- batch_size: 批量大小（用于进度显示）
- max_workers: 并行线程数
- verbose: 是否打印进度
**输出**: ReasoningChain 列表（所有论文的所有思维链）
**逻辑**:
- 使用 ThreadPoolExecutor 并行加载
- 对每个 paper_id：
  - 调用 load_reasoning_chain_xml() 加载 XML
  - 如果加载成功，调用 parse_reasoning_chains() 解析
  - 将结果追加到总列表
  - 每处理 batch_size 个论文，打印进度
- 返回所有思维链列表
- **异常处理**: 单个文件失败不影响整体流程，记录错误日志

### 10. save_reasoning_chains(
    chains: List[ReasoningChain],
    output_path: Path
)
保存思维链数据到本地

**输入**:
- chains: ReasoningChain 列表
- output_path: 输出文件路径（JSONL 格式）
**输出**: 无
**逻辑**:
- 将 ReasoningChain 对象序列化为 JSON
- 使用 dataclasses.asdict() 转换为字典
- 保存为 JSON Lines 格式（每行一个思维链）
- 打印保存信息

### 11. load_reasoning_chains_from_cache(cache_path: Path) -> List[ReasoningChain]
从缓存加载思维链数据

**输入**: 缓存文件路径
**输出**: ReasoningChain 列表
**逻辑**:
- 读取 JSONL 文件
- 逐行反序列化为 ReasoningChain 对象
- 返回列表

## 主流程函数

### load_data_for_step1(config: Dict) -> List[ReasoningChain]
Step1 数据加载主入口

**输入**: 配置字典（从 step1_config.yaml 加载）
**输出**: ReasoningChain 列表
**逻辑**:
```python
1. 初始化 TOS 客户端和 JournalMapper
   from paper2tools.src.staged_lance.storage import LanceTosStore
   from paper2tools.src.staged_lance.journal_map import JournalMapper
   from paper2tools.src.staged_lance.config import StageConfig

   stage_config = StageConfig()  # 使用默认配置
   store = LanceTosStore(stage_config)
   journal_mapper = JournalMapper(store)

2. 加载期刊配置
   target_journals = load_journal_config(
       config['journal_config_path'],
       config['target_domain']
   )

3. 构建或加载 paper_id_list
   paper_ids, metadata = build_paper_id_list(
       journal_mapper,
       target_journals,
       config['target_domain'],
       config['cache_dir'],
       force_rebuild=config.get('force_rebuild_ids', False)
   )

4. 检查思维链缓存
   chains_cache_path = config['output_dir'] / f"reasoning_chains_{config['target_domain']}.jsonl"
   if chains_cache_path.exists() and not config.get('force_reload_chains', False):
       return load_reasoning_chains_from_cache(chains_cache_path)

5. 批量加载思维链
   # 需要 paper_id → journal 映射（用于构建 ReasoningChain）
   mapping = journal_mapper.load_or_build()

   chains = batch_load_reasoning_chains(
       paper_ids,
       mapping,
       store.get_tos_client(),
       stage_config.tos_bucket,
       batch_size=config['batch_size'],
       max_workers=config['max_workers'],
       verbose=config['verbose']
   )

6. 保存缓存
   save_reasoning_chains(chains, chains_cache_path)

7. 打印统计信息
   - 总论文数
   - 总思维链数
   - 平均每篇论文的思维链数
   - 平均每个思维链的步骤数

8. 返回结果
   return chains
```

## 配置参数（step1_config.yaml 需要新增）

```yaml
data:
  journal_config_path: "configs/domain_journals.yaml"
  target_domain: "bioinformatics"  # 从 domain_journals.yaml 中选择
  cache_dir: "data/cache"          # paper_ids 缓存目录
  output_dir: "data/step1_output"  # 思维链输出目录
  force_rebuild_ids: false         # 是否强制重建 paper_id_list
  force_reload_chains: false       # 是否强制重新加载思维链
  batch_size: 100                  # 进度显示批量大小
  max_workers: 10                  # 并行线程数
  verbose: true
```

## 错误处理策略

1. **文件不存在**: 记录警告日志，跳过该论文，继续处理
2. **XML 格式错误**: 记录错误日志，跳过该论文
3. **TOS 连接失败**: 由 TOS SDK 自动重试，失败后记录错误
4. **内存不足**: 使用流式处理，分批保存

## 性能优化

1. **两级缓存机制**:
   - **Level 1**: paper_id → journal 映射（300万条，由 JournalMapper 管理）
   - **Level 2**: paper_ids 列表（按领域，本模块管理）
   - **Level 3**: reasoning_chains 数据（JSONL 格式，本模块管理）

2. **并行加载**:
   - 使用 ThreadPoolExecutor 并行从 TOS 读取文件
   - 控制并发数（max_workers，避免 TOS 限流）

3. **内存优化**:
   - 使用 JSONL 格式保存思维链（支持流式读写）
   - 分批处理，避免内存溢出

## 统计信息

在加载完成后，打印统计信息：
- 总论文数
- 总思维链数
- 每个期刊的论文数和思维链数
- 平均每篇论文的思维链数
- 平均每个思维链的步骤数
- 加载失败的论文数和原因

## 依赖模块

### 外部依赖
- `paper2tools.src.staged_lance.storage.LanceTosStore`: TOS 操作封装
- `paper2tools.src.staged_lance.journal_map.JournalMapper`: 期刊映射
- `paper2tools.src.staged_lance.config.StageConfig`: 配置管理
- `tos`: TOS SDK
- `lxml`: XML 解析
- `yaml`: 配置文件读取

### 内部依赖
- `src/common/xml_utils.py`: XML 解析工具（可选，如果需要额外的 XML 处理）
- `src/common/config.py`: 配置管理（可选）

## 使用示例

```python
from pathlib import Path
from src.step1.data_loader import load_data_for_step1

config = {
    'journal_config_path': Path('configs/domain_journals.yaml'),
    'target_domain': 'bioinformatics',
    'cache_dir': Path('data/cache'),
    'output_dir': Path('data/step1_output'),
    'force_rebuild_ids': False,
    'force_reload_chains': False,
    'batch_size': 100,
    'max_workers': 10,
    'verbose': True
}

# 加载数据
chains = load_data_for_step1(config)

# 使用数据
for chain in chains[:5]:
    print(f"Paper: {chain.paper_id}, Journal: {chain.journal}")
    print(f"Conclusion: {chain.conclusion_title}")
    print(f"Steps: {len(chain.steps)}")
    for step in chain.steps:
        print(f"  - Step {step.step_id}: {step.text[:100]}...")
```
"""
