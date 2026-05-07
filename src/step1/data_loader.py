"""
数据加载模块 - 从 TOS 加载指定期刊的 reasoning_chain.xml 文件
"""

import json
import yaml
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING
from datetime import datetime
from lxml import etree
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

if TYPE_CHECKING:
    from src.staged_lance.journal_map import JournalMapper
    from src.staged_lance.storage import LanceTosStore


@dataclass
class ReasoningStep:
    """推理步骤"""
    step_id: str
    text: str
    raw_text: str
    has_citations: bool
    has_figures: bool


@dataclass
class ReasoningChain:
    """思维链"""
    paper_id: str
    journal: str
    conclusion_id: str
    conclusion_title: str
    conclusion_text: str
    steps: List[ReasoningStep]
    raw_xml: str



def load_journal_config(config_path: Path, domain: str) -> List[str]:
    """加载期刊配置文件，返回指定领域的期刊列表"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if domain not in config:
        raise ValueError(f"Domain '{domain}' not found in config. Available: {list(config.keys())}")

    journals = config[domain].get("journals", [])
    if not journals:
        raise ValueError(f"No journals found for domain '{domain}'")

    return journals


def save_paper_id_list(
    cache_path: Path,
    domain: str,
    journals: List[str],
    paper_ids: List[str],
    per_journal_count: Dict[str, int]
) -> None:
    """保存 paper_id 列表到本地"""
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "domain": domain,
        "journals": journals,
        "created_at": datetime.now().isoformat(),
        "total_count": len(paper_ids),
        "per_journal_count": per_journal_count,
        "paper_ids": paper_ids
    }

    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(paper_ids)} paper IDs to {cache_path}")


def load_paper_id_list_from_cache(cache_path: Path) -> Tuple[List[str], Dict]:
    """从本地缓存加载 paper_id 列表"""
    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    paper_ids = data["paper_ids"]
    metadata = {k: v for k, v in data.items() if k != "paper_ids"}

    print(f"Loaded {len(paper_ids)} paper IDs from cache: {cache_path}")
    print(f"  Domain: {metadata['domain']}")
    print(f"  Created: {metadata['created_at']}")

    return paper_ids, metadata


def build_paper_id_list(
    journal_mapper,
    target_journals: List[str],
    domain: str,
    cache_dir: Path,
    force_rebuild: bool = False
) -> Tuple[List[str], Dict]:
    """构建并持久化目标期刊的论文 ID 列表"""
    cache_path = cache_dir / f"paper_ids_{domain}.json"

    # 检查缓存
    if cache_path.exists() and not force_rebuild:
        print(f"Found cached paper_id list: {cache_path}")
        return load_paper_id_list_from_cache(cache_path)

    print(f"Building paper_id list for domain '{domain}'...")
    print(f"Target journals: {target_journals}")

    # 加载全量映射（内部有缓存机制）
    print("Loading journal mapping...")
    mapping = journal_mapper.load_or_build()
    print(f"Loaded {len(mapping)} paper-journal mappings")

    # 筛选目标期刊的论文
    print("Filtering papers by journals...")
    paper_ids_set = journal_mapper.get_domain_paper_ids(mapping, set(target_journals))
    paper_ids = sorted(paper_ids_set)

    # 统计每个期刊的论文数
    per_journal_count = {}
    for pid in paper_ids:
        journal = mapping[pid]
        per_journal_count[journal] = per_journal_count.get(journal, 0) + 1

    # 保存到本地
    save_paper_id_list(cache_path, domain, target_journals, paper_ids, per_journal_count)

    # 打印统计
    print(f"\nPaper ID list built successfully:")
    print(f"  Total papers: {len(paper_ids)}")
    print(f"  Per-journal breakdown:")
    for journal, count in sorted(per_journal_count.items(), key=lambda x: -x[1]):
        print(f"    - {journal}: {count}")

    metadata = {
        "domain": domain,
        "journals": target_journals,
        "created_at": datetime.now().isoformat(),
        "total_count": len(paper_ids),
        "per_journal_count": per_journal_count
    }

    return paper_ids, metadata


def parse_reasoning_chain_xml(xml_content: str, paper_id: str, journal: str) -> List[ReasoningChain]:
    """解析 reasoning_chain.xml，提取所有思维链"""
    try:
        root = etree.fromstring(xml_content.encode('utf-8'))
    except Exception as e:
        print(f"Failed to parse XML for paper {paper_id}: {e}")
        return []

    chains = []

    # 遍历所有 <conclusion_reasoning> 块
    for cr_elem in root.findall('.//conclusion_reasoning'):
        conclusion_id = cr_elem.get('conclusion_id', 'unknown')
        conclusion_title = cr_elem.get('conclusion_title', '')
        conclusion_text_elem = cr_elem.find('conclusion_text')
        conclusion_text = conclusion_text_elem.text if conclusion_text_elem is not None else ''

        # 提取所有 <step> 节点
        steps = []
        for step_elem in cr_elem.findall('.//step'):
            step_id = step_elem.get('id', 'unknown')

            # 原始文本（保留标签）
            raw_text = etree.tostring(step_elem, encoding='unicode', method='xml')

            # 纯文本（去除所有标签）
            text = ''.join(step_elem.itertext()).strip()

            # 检查引用类型
            has_citations = len(step_elem.findall('.//ref[@type="citation"]')) > 0
            has_figures = len(step_elem.findall('.//ref[@type="figure"]')) > 0

            steps.append(ReasoningStep(
                step_id=step_id,
                text=text,
                raw_text=raw_text,
                has_citations=has_citations,
                has_figures=has_figures
            ))

        if steps:  # 只保留有步骤的思维链
            chains.append(ReasoningChain(
                paper_id=paper_id,
                journal=journal,
                conclusion_id=conclusion_id,
                conclusion_title=conclusion_title,
                conclusion_text=conclusion_text,
                steps=steps,
                raw_xml=etree.tostring(cr_elem, encoding='unicode', method='xml')
            ))

    return chains


def load_reasoning_chains_from_tos(
    paper_ids: List[str],
    journal_mapping: Dict[str, str],
    tos_store,
    max_workers: int = 10,
    verbose: bool = True
) -> List[ReasoningChain]:
    """从 TOS 并行加载 reasoning_chain.xml 文件"""
    all_chains = []
    papers_with_chains = 0

    def load_single_paper(paper_id: str) -> List[ReasoningChain]:
        """加载单篇论文的思维链；无 XML 或失败时静默返回空列表"""
        try:
            xml_content = tos_store.download_reasoning_xml(paper_id)

            if xml_content is None or not xml_content.strip():
                return []

            journal = journal_mapping.get(paper_id, "Unknown")
            chains = parse_reasoning_chain_xml(xml_content, paper_id, journal)
            return chains
        except Exception:
            return []

    print(f"Loading reasoning chains from TOS (max_workers={max_workers})...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(load_single_paper, pid): pid for pid in paper_ids}

        if verbose:
            futures_iter = tqdm(as_completed(futures), total=len(paper_ids), desc="Loading papers")
        else:
            futures_iter = as_completed(futures)

        for future in futures_iter:
            chains = future.result()
            if chains:
                papers_with_chains += 1
            all_chains.extend(chains)

    n_skip = len(paper_ids) - papers_with_chains
    print(f"\n加载完成:")
    print(f"  请求论文数: {len(paper_ids)}")
    print(f"  成功加载（至少 1 条思维链）: {papers_with_chains}")
    print(f"  跳过（无 XML / 空内容 / 下载或解析失败）: {n_skip}")
    print(f"  思维链条总数: {len(all_chains)}")

    if all_chains:
        total_steps = sum(len(chain.steps) for chain in all_chains)
        avg_steps = total_steps / len(all_chains)
        print(f"  思维步骤总数: {total_steps}")
        print(f"  每条链平均步骤数: {avg_steps:.2f}")

    return all_chains


def save_reasoning_chains_to_jsonl(chains: List[ReasoningChain], output_path: Path) -> None:
    """保存思维链到 JSONL 文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for chain in chains:
            # 转换为字典（dataclass → dict）
            chain_dict = asdict(chain)
            f.write(json.dumps(chain_dict, ensure_ascii=False) + '\n')

    print(f"Saved {len(chains)} reasoning chains to {output_path}")


def load_reasoning_chains_from_jsonl(input_path: Path) -> List[ReasoningChain]:
    """从 JSONL 文件加载思维链"""
    chains = []

    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            chain_dict = json.loads(line)
            # 重建 dataclass 对象
            steps = [ReasoningStep(**s) for s in chain_dict['steps']]
            chain = ReasoningChain(
                paper_id=chain_dict['paper_id'],
                journal=chain_dict['journal'],
                conclusion_id=chain_dict['conclusion_id'],
                conclusion_title=chain_dict['conclusion_title'],
                conclusion_text=chain_dict['conclusion_text'],
                steps=steps,
                raw_xml=chain_dict['raw_xml']
            )
            chains.append(chain)

    print(f"Loaded {len(chains)} reasoning chains from {input_path}")
    return chains


def load_random_sample_from_tos(
    sample_size: int,
    tos_store,
    cache_dir: Path,
    max_workers: int = 10,
    verbose: bool = True
) -> List[ReasoningChain]:
    """从TOS随机采样论文"""
    import random

    cache_path = cache_dir / f"random_sample_{sample_size}.json"

    # 检查缓存
    if cache_path.exists():
        print(f"Found cached random sample: {cache_path}")
        with open(cache_path, 'r') as f:
            data = json.load(f)
        paper_ids = data["paper_ids"]
        print(f"Loaded {len(paper_ids)} paper IDs from cache")
    else:
        # 列举所有XML文件
        print("Listing all reasoning_chain.xml files from TOS...")
        prefix = "paper_ocr/xml/"
        all_keys = []

        try:
            for key in tos_store.list_tos_objects(prefix=prefix):
                if key.endswith("_reasoning_chain.xml"):
                    paper_id = key.split('/')[-1].replace('_reasoning_chain.xml', '')
                    all_keys.append(paper_id)
        except Exception as e:
            print(f"Error listing TOS objects: {e}")
            return []

        print(f"Found {len(all_keys)} total papers with reasoning_chain.xml")

        # 随机采样
        if len(all_keys) > sample_size:
            paper_ids = random.sample(all_keys, sample_size)
        else:
            paper_ids = all_keys
            print(f"Warning: only {len(all_keys)} papers available, less than requested {sample_size}")

        # 保存缓存
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump({
                "sample_size": sample_size,
                "total_available": len(all_keys),
                "created_at": datetime.now().isoformat(),
                "paper_ids": paper_ids
            }, f, indent=2)
        print(f"Saved random sample to {cache_path}")

    # 加载思维链
    print(f"\nLoading {len(paper_ids)} reasoning chains from TOS...")
    chains = load_reasoning_chains_from_tos(
        paper_ids=paper_ids,
        journal_mapping={},  # 随机采样不需要journal信息
        tos_store=tos_store,
        max_workers=max_workers,
        verbose=verbose
    )

    return chains


def load_data_for_step1(config: Dict) -> List[ReasoningChain]:
    """Step1 数据加载主入口"""
    import sys
    if '/personal/paper2tools/src' not in sys.path:
        sys.path.insert(0, '/personal/paper2tools/src')

    from staged_lance.storage import LanceTosStore
    from staged_lance.journal_map import JournalMapper
    from staged_lance.config import StageConfig

    # 检查是否为随机采样模式
    mode = config.get('mode', 'journal')

    if mode == 'random_sample':
        print(f"\n=== Step1 Data Loading (Random Sample) ===")
        sample_size = config['sample_size']
        print(f"Sample size: {sample_size}")

        stage_config = StageConfig()
        tos_store = LanceTosStore(stage_config)
        cache_dir = Path(config['cache_dir'])

        chains = load_random_sample_from_tos(
            sample_size=sample_size,
            tos_store=tos_store,
            cache_dir=cache_dir,
            max_workers=config.get('max_workers', 10),
            verbose=config.get('verbose', True)
        )

        # 保存到JSONL
        output_dir = Path(config['output_dir'])
        chains_cache_path = output_dir / f"reasoning_chains_random{sample_size}.jsonl"
        if not chains_cache_path.exists():
            save_reasoning_chains_to_jsonl(chains, chains_cache_path)

        return chains

    # 原有的期刊模式
    # 1. 加载期刊配置
    journal_config_path = Path(config['journal_config_path'])
    target_domain = config['target_domain']
    journals = load_journal_config(journal_config_path, target_domain)

    print(f"\n=== Step1 Data Loading ===")
    print(f"Domain: {target_domain}")
    print(f"Journals ({len(journals)}): {journals}")

    cache_dir = Path(config['cache_dir'])
    paper_ids_cache = cache_dir / f"paper_ids_{target_domain}.json"

    # 2. 检查 paper_ids 缓存是否存在
    if paper_ids_cache.exists() and not config.get('force_rebuild_ids', False):
        print(f"\n✓ Found cached paper_id list: {paper_ids_cache}")
        paper_ids, metadata = load_paper_id_list_from_cache(paper_ids_cache)
        print(f"  Loaded {len(paper_ids)} paper IDs from cache")

        # 跳过 JournalMapper 初始化，直接加载思维链
        output_dir = Path(config['output_dir'])
        chains_cache_path = output_dir / f"reasoning_chains_{target_domain}.jsonl"

        if chains_cache_path.exists() and not config.get('force_reload_chains', False):
            print(f"\n✓ Found cached reasoning chains: {chains_cache_path}")
            return load_reasoning_chains_from_jsonl(chains_cache_path)

        # 需要从 TOS 加载思维链，但不需要 journal_mapping
        print(f"\nLoading reasoning chains from TOS (without journal mapping)...")
        stage_config = StageConfig()
        tos_store = LanceTosStore(stage_config)

        chains = load_reasoning_chains_from_tos(
            paper_ids=paper_ids,
            journal_mapping={},  # 空映射，load_reasoning_chains_from_tos 会用 paper_id 推断 journal
            tos_store=tos_store,
            max_workers=config.get('max_workers', 10),
            verbose=config.get('verbose', True)
        )

        # 保存到本地缓存
        save_reasoning_chains_to_jsonl(chains, chains_cache_path)
        return chains

    # 3. 如果没有缓存，需要初始化 TOS store 和 JournalMapper
    print(f"\nNo paper_ids cache found, building from journal mapping...")
    stage_config = StageConfig()
    tos_store = LanceTosStore(stage_config)
    journal_mapper = JournalMapper(tos_store, cache_path=cache_dir / "journal_mapping.json")

    # 4. 构建/加载 paper_id 列表
    paper_ids, metadata = build_paper_id_list(
        journal_mapper=journal_mapper,
        target_journals=journals,
        domain=target_domain,
        cache_dir=cache_dir,
        force_rebuild=config.get('force_rebuild_ids', False)
    )

    # 5. 检查是否有缓存的思维链数据
    output_dir = Path(config['output_dir'])
    chains_cache_path = output_dir / f"reasoning_chains_{target_domain}.jsonl"

    if chains_cache_path.exists() and not config.get('force_reload_chains', False):
        print(f"\nFound cached reasoning chains: {chains_cache_path}")
        return load_reasoning_chains_from_jsonl(chains_cache_path)

    # 6. 从 TOS 加载思维链
    print(f"\nLoading reasoning chains from TOS...")
    mapping = journal_mapper.load_or_build()

    chains = load_reasoning_chains_from_tos(
        paper_ids=paper_ids,
        journal_mapping=mapping,
        tos_store=tos_store,
        max_workers=config.get('max_workers', 10),
        verbose=config.get('verbose', True)
    )

    # 7. 保存到本地缓存
    save_reasoning_chains_to_jsonl(chains, chains_cache_path)

    return chains
