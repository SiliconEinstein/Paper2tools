"""
Step3 检索器 - 多路召回 + 重排序
"""

import json
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict

from .utils import extract_keywords, detect_data_types, detect_methods
from ..db import LanceVectorStore
from ..db.schema import WORKFLOW_EMBEDDING_SCHEMA


class WorkflowRetriever:
    """Workflow 检索器"""

    def __init__(self, index_dir: Path, embedder, config: Dict):
        """
        初始化检索器

        Args:
            index_dir: 索引目录
            embedder: embedding 模型
            config: 检索配置
        """
        self.index_dir = Path(index_dir)
        self.embedder = embedder
        self.config = config

        # 加载向量索引（传入正确的 schema）
        self.vector_store = LanceVectorStore(
            db_path=self.index_dir,
            table_name="workflow_embeddings",
            schema=WORKFLOW_EMBEDDING_SCHEMA
        )

        # 加载倒排索引
        with open(self.index_dir / "keyword_inverted_index.json", 'r', encoding='utf-8') as f:
            self.keyword_index = json.load(f)

        with open(self.index_dir / "type_index.json", 'r', encoding='utf-8') as f:
            self.type_index = json.load(f)

        with open(self.index_dir / "method_index.json", 'r', encoding='utf-8') as f:
            self.method_index = json.load(f)

        # 加载 workflow 注册表
        with open(self.index_dir / "workflow_registry.json", 'r', encoding='utf-8') as f:
            self.workflow_registry = json.load(f)

        # 停用词
        self.stopwords = set(self.config.get("keyword_extraction", {}).get("stopwords", []))

    def retrieve(self, query: str, top_k: int = 5, domain: str = None) -> List[Dict]:
        """
        检索相关 workflows

        Args:
            query: 查询文本
            top_k: 返回结果数量
            domain: 限定领域（可选）

        Returns:
            检索结果列表
        """
        recall_top_k = self.config.get("recall_top_k", 20)

        # 1. 多路召回
        candidates_semantic = self._semantic_search(query, k=recall_top_k)
        candidates_keyword = self._keyword_search(query, k=recall_top_k)
        candidates_io = self._io_type_search(query, k=recall_top_k)
        candidates_method = self._method_search(query, k=recall_top_k)

        # 2. 合并候选集
        all_candidates = self._merge_candidates([
            candidates_semantic,
            candidates_keyword,
            candidates_io,
            candidates_method
        ])

        # 3. 重排序
        ranked = self._rerank(query, all_candidates)

        # 4. 过滤 domain
        if domain:
            ranked = [w for w in ranked if w["workflow_meta"]["domain"] == domain]

        return ranked[:top_k]

    def _semantic_search(self, query: str, k: int) -> List[Dict]:
        """语义向量检索"""
        import asyncio
        import numpy as np

        async def get_embedding():
            vectors = await self.embedder._call_api_batch([query])
            return vectors[0]

        query_embedding = asyncio.run(get_embedding())

        # 转换为 numpy array（LanceVectorStore.search 需要）
        if isinstance(query_embedding, list):
            query_embedding = np.array(query_embedding, dtype=np.float32)

        results = self.vector_store.search(query_embedding, top_k=k)

        candidates = []
        for r in results:
            candidates.append({
                "workflow_id": r["id"],  # LanceVectorStore.search returns "id" field
                "score": 1 - r["distance"],
                "source": "semantic"
            })

        return candidates

    def _keyword_search(self, query: str, k: int) -> List[Dict]:
        """关键词匹配检索"""
        query_keywords = extract_keywords(query, stopwords=self.stopwords)

        if not query_keywords:
            return []

        workflow_scores = defaultdict(float)
        for keyword in query_keywords:
            if keyword in self.keyword_index:
                for workflow_id in self.keyword_index[keyword]:
                    workflow_scores[workflow_id] += 1.0

        # 归一化
        for wid in workflow_scores:
            workflow_scores[wid] /= len(query_keywords)

        # 排序
        sorted_workflows = sorted(workflow_scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {"workflow_id": wid, "score": score, "source": "keyword"}
            for wid, score in sorted_workflows[:k]
        ]

    def _io_type_search(self, query: str, k: int) -> List[Dict]:
        """输入输出类型匹配检索"""
        patterns = self.config.get("data_type_patterns", [])
        query_types = detect_data_types(query, patterns)

        if not query_types:
            return []

        workflow_scores = defaultdict(float)
        for dtype in query_types:
            if dtype in self.type_index:
                for workflow_id in self.type_index[dtype]:
                    workflow_scores[workflow_id] += 1.0

        # 归一化
        for wid in workflow_scores:
            workflow_scores[wid] /= len(query_types)

        sorted_workflows = sorted(workflow_scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {"workflow_id": wid, "score": score, "source": "io_type"}
            for wid, score in sorted_workflows[:k]
        ]

    def _method_search(self, query: str, k: int) -> List[Dict]:
        """方法名匹配检索"""
        patterns = self.config.get("method_patterns", [])
        query_methods = detect_methods(query, patterns)

        if not query_methods:
            return []

        workflow_scores = defaultdict(float)
        for method in query_methods:
            if method in self.method_index:
                for workflow_id in self.method_index[method]:
                    workflow_scores[workflow_id] += 1.0

        # 归一化
        for wid in workflow_scores:
            workflow_scores[wid] /= len(query_methods)

        sorted_workflows = sorted(workflow_scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {"workflow_id": wid, "score": score, "source": "method"}
            for wid, score in sorted_workflows[:k]
        ]

    def _merge_candidates(self, candidate_lists: List[List[Dict]]) -> List[Dict]:
        """合并多路候选集"""
        all_candidates = []
        seen = set()

        for candidates in candidate_lists:
            for candidate in candidates:
                wid = candidate["workflow_id"]
                if wid not in seen:
                    all_candidates.append(candidate)
                    seen.add(wid)

        return all_candidates

    def _rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """重排序"""
        weights = self.config.get("weights", {
            "semantic": 0.4,
            "keyword": 0.2,
            "io_type": 0.2,
            "method": 0.1,
            "quality": 0.1
        })

        # 融合多路得分
        workflow_scores = defaultdict(lambda: {
            "semantic": 0,
            "keyword": 0,
            "io_type": 0,
            "method": 0
        })

        for candidate in candidates:
            wid = candidate["workflow_id"]
            source = candidate["source"]
            workflow_scores[wid][source] = max(
                workflow_scores[wid][source],
                candidate["score"]
            )

        # 计算综合得分
        final_scores = []
        for wid, scores in workflow_scores.items():
            if wid not in self.workflow_registry:
                continue

            workflow_meta = self.workflow_registry[wid]

            # 加权融合
            combined_score = sum(
                scores[k] * weights.get(k, 0)
                for k in ["semantic", "keyword", "io_type", "method"]
            )

            # 质量加权
            quality_score = workflow_meta.get("statistics", {}).get("avg_intra_similarity", 0.5)
            combined_score += weights.get("quality", 0.1) * quality_score

            final_scores.append({
                "workflow_id": wid,
                "score": combined_score,
                "workflow_meta": workflow_meta,
                "match_details": scores
            })

        # 排序
        final_scores.sort(key=lambda x: x["score"], reverse=True)

        return final_scores

    def close(self):
        """关闭资源"""
        self.vector_store.close()
