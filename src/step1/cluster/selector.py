"""
聚类选择模块 - 选 top 10% 的簇，每簇取离中心最近的 K 个点
"""

import heapq
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

from ...db import LanceVectorStore

# 链数超过该阈值时，用「单次 Lance 顺序扫表」代替「每个簇一次 WHERE IN」
_SINGLE_SCAN_MIN_CHAINS = 15_000


def parse_selection_config(clustering_config: Optional[Dict] = None) -> Tuple[float, int]:
    """
    从 ``clustering.selection`` 读取簇选择参数（供 YAML 配置）。

    Returns:
        (top_percent, max_per_cluster)
        - top_percent: 按簇大小降序取前百分之多少的簇，默认 0.1（10%）
        - max_per_cluster: 每个选中簇最多保留多少条链（距质心最近），默认 10
    """
    sel = (clustering_config or {}).get("selection") or {}
    top = float(sel.get("top_percent", 0.1))
    m = int(sel.get("max_per_cluster", 10))
    return top, m


def _nearest_k_to_center_per_cluster(
    member_cids: List[str],
    center: np.ndarray,
    k: int,
    vector_store: LanceVectorStore,
    lance_batch: int,
) -> List[Tuple[str, float]]:
    """小数据路径：按簇分批 ``IN`` 查询（簇数少、链数少时往返次数可接受）。"""
    center = center.astype(np.float32, copy=False)
    kk = min(k, len(member_cids))
    if kk <= 0:
        return []

    if len(member_cids) <= lance_batch:
        rows = vector_store.fetch_by_ids_batched(
            member_cids,
            columns=["vector"],
            batch_size=len(member_cids),
            scan_if_id_count_ge=10**12,
            verbose=False,
        )
        vecs: List[np.ndarray] = []
        cids: List[str] = []
        for cid in member_cids:
            rec = rows.get(cid)
            if rec and rec.get("vector") is not None:
                vecs.append(np.asarray(rec["vector"], dtype=np.float32))
                cids.append(cid)
        if not vecs:
            return []
        d = np.linalg.norm(np.stack(vecs, axis=0) - center, axis=1)
        n = len(d)
        take = min(kk, n)
        idx = np.argpartition(d, take - 1)[:take]
        idx = idx[np.argsort(d[idx])]
        return [(cids[i], float(d[i])) for i in idx]

    h: List[Tuple[float, str]] = []
    for i in range(0, len(member_cids), lance_batch):
        chunk = member_cids[i : i + lance_batch]
        rows = vector_store.fetch_by_ids_batched(
            chunk,
            columns=["vector"],
            batch_size=len(chunk),
            scan_if_id_count_ge=10**12,
            verbose=False,
        )
        for cid in chunk:
            rec = rows.get(cid)
            if not rec or rec.get("vector") is None:
                continue
            vec = np.asarray(rec["vector"], dtype=np.float32)
            dist = float(np.linalg.norm(vec - center))
            if len(h) < kk:
                heapq.heappush(h, (-dist, cid))
            elif dist < -h[0][0]:
                heapq.heapreplace(h, (-dist, cid))

    out = [(-neg, cid) for neg, cid in h]
    out.sort(key=lambda x: x[0])
    return [(cid, dist) for dist, cid in out]


def _nearest_k_via_single_lance_scan(
    vector_store: LanceVectorStore,
    chain_to_label: Dict[str, int],
    top_cluster_ids: Set[int],
    centers: np.ndarray,
    k_per_cluster: Dict[int, int],
    page_size: int,
    verbose: bool,
) -> Dict[int, List[Tuple[str, float]]]:
    """
    **一次**顺序分页读全表 ``(id, vector)``，对属于 top 簇的行用每簇一个 **k 堆** 维护距质心最近的 K 条。

    避免 ~「top 簇个数」次 Lance ``WHERE IN`` 串行往返（此前主要耗时来源）。
    """
    centers_f32 = centers.astype(np.float32, copy=False)
    heaps: Dict[int, List[Tuple[float, str]]] = {c: [] for c in top_cluster_ids}
    id_field = vector_store.id_field
    rows_total = 0
    page_n = 0
    if verbose:
        print("  正在读取 Lance 第 1 页（若表很大，此处会阻塞较久）…", flush=True)

    for ar in vector_store.iter_embedding_pages(page_size):
        page_n += 1
        n = len(ar)
        rows_total += n
        id_col = ar.column(id_field)
        vec_col = ar.column("vector")
        for j in range(n):
            sr = str(id_col[j].as_py())
            lab = chain_to_label.get(sr)
            if lab is None or lab < 0 or lab not in top_cluster_ids:
                continue
            vec_py = vec_col[j].as_py()
            if vec_py is None:
                continue
            vec = np.asarray(vec_py, dtype=np.float32)
            dist = float(np.linalg.norm(vec - centers_f32[lab]))
            kk = k_per_cluster[lab]
            h = heaps[lab]
            if len(h) < kk:
                heapq.heappush(h, (-dist, sr))
            elif dist < -h[0][0]:
                heapq.heapreplace(h, (-dist, sr))
        if verbose:
            print(f"  ... Lance scan: page {page_n}, rows_scanned≈{rows_total}", flush=True)

    out: Dict[int, List[Tuple[str, float]]] = {}
    for c in top_cluster_ids:
        h = heaps[c]
        items = sorted(((-neg, xid) for neg, xid in h), key=lambda t: t[0])
        out[c] = [(xid, d) for d, xid in items]
    return out


def select_top_clusters(
    vector_store: LanceVectorStore,
    centers: np.ndarray,
    labels: np.ndarray,
    chain_ids: List[str],
    top_percent: float = 0.1,
    max_per_cluster: int = 10,
    verbose: bool = True,
    lance_batch: int = 2500,
    scan_page_size: int = 32768,
) -> Dict:
    """
    选 top N% 簇（按大小），每簇取离中心最近的 K 个点。

    Lance 优化：当链总数 ≥ ``_SINGLE_SCAN_MIN_CHAINS`` 时，**单次顺序扫表**
    ``(chain_id, vector)`` + 每簇 **k 容量堆**；否则仍用按簇 ``IN`` 查询（小库更快）。
    """
    cluster_members = defaultdict(list)
    for i, label in enumerate(labels):
        if label >= 0:
            cluster_members[int(label)].append(i)

    sorted_clusters = sorted(cluster_members.items(), key=lambda x: -len(x[1]))
    n_top = max(1, int(len(sorted_clusters) * top_percent))
    top_clusters = sorted_clusters[:n_top]

    cluster_member_map: Dict[int, List[str]] = {}
    for cluster_id, member_indices in top_clusters:
        cluster_member_map[cluster_id] = [chain_ids[i] for i in member_indices]

    if verbose:
        total_clusters = len(sorted_clusters)
        print(f"\n=== Cluster Selection ===")
        print(f"Total clusters: {total_clusters}")
        print(f"Top {top_percent*100:.0f}%: {n_top} clusters")
        sizes = [len(m) for m in cluster_member_map.values()]
        print(f"Size range: {min(sizes)} ~ {max(sizes)}")
        print(f"Total members in top clusters: {sum(sizes)}")

    top_cluster_ids = set(cluster_member_map.keys())
    k_per_cluster = {
        cid: min(max_per_cluster, len(mems))
        for cid, mems in cluster_member_map.items()
    }

    selected_chain_ids: List[Dict] = []
    cluster_stats: List[Dict] = []

    if len(chain_ids) >= _SINGLE_SCAN_MIN_CHAINS:
        if verbose:
            print(
                f"Lance: single sequential scan (page={scan_page_size}) + "
                f"{len(top_cluster_ids)} k-heaps (avoid ~{len(top_cluster_ids)} separate IN queries)",
                flush=True,
            )
            print(
                f"  正在构建 chain_id→簇标签 索引（{len(chain_ids)} 条），随后读 Lance 可能数分钟才有第一页日志…",
                flush=True,
            )
        lab_flat = np.asarray(labels).ravel()
        chain_to_lab = dict(
            zip(map(str, chain_ids), map(int, lab_flat))
        )
        if verbose:
            print(f"  索引构建完成，开始顺序读向量表", flush=True)
        nearest_by_cluster = _nearest_k_via_single_lance_scan(
            vector_store,
            chain_to_lab,
            top_cluster_ids,
            centers,
            k_per_cluster,
            page_size=scan_page_size,
            verbose=verbose,
        )
        for cluster_id, member_cids in cluster_member_map.items():
            nearest = nearest_by_cluster.get(cluster_id, [])
            for cid, dist in nearest:
                selected_chain_ids.append({
                    "chain_id": cid,
                    "cluster_id": cluster_id,
                    "distance": dist,
                })
            cluster_stats.append({
                "cluster_id": cluster_id,
                "size": len(member_cids),
                "selected_count": len(nearest),
            })
    else:
        if verbose:
            print(
                f"Per-cluster Lance IN (chains<{ _SINGLE_SCAN_MIN_CHAINS }): "
                f"batch≤{lance_batch}, argpartition / k-heap",
                flush=True,
            )
        n_map = len(cluster_member_map)
        log_every = 1 if n_map <= 200 else max(1, n_map // 25)
        for cluster_idx, (cluster_id, member_cids) in enumerate(cluster_member_map.items(), 1):
            center = centers[cluster_id]
            k = k_per_cluster[cluster_id]
            if verbose and (n_map <= 200 or cluster_idx <= 3):
                print(
                    f"  → cluster {cluster_idx}/{n_map} id={cluster_id}, "
                    f"{len(member_cids)} members: querying Lance…",
                    flush=True,
                )
            nearest = _nearest_k_to_center_per_cluster(
                member_cids, center, k, vector_store, lance_batch=lance_batch
            )
            for cid, dist in nearest:
                selected_chain_ids.append({
                    "chain_id": cid,
                    "cluster_id": cluster_id,
                    "distance": dist,
                })
            cluster_stats.append({
                "cluster_id": cluster_id,
                "size": len(member_cids),
                "selected_count": len(nearest),
            })
            if verbose and (cluster_idx == 1 or cluster_idx % log_every == 0):
                print(
                    f"  ✓ cluster {cluster_idx}/{n_map} id={cluster_id}: "
                    f"picked {len(nearest)}/{k} nearest",
                    flush=True,
                )

    if verbose:
        print(f"Fetching metadata for {len(selected_chain_ids)} selected chains...")

    final_chain_ids = [item["chain_id"] for item in selected_chain_ids]
    meta_rows = vector_store.fetch_by_ids_batched(
        final_chain_ids,
        columns=["paper_id", "chain_text"],
        batch_size=2500,
        scan_if_id_count_ge=10**12,
        verbose=verbose,
    )

    selected_chains = []
    for item in selected_chain_ids:
        cid = item["chain_id"]
        rec = meta_rows.get(cid, {})
        selected_chains.append({
            "chain_id": cid,
            "cluster_id": item["cluster_id"],
            "distance": item["distance"],
            "paper_id": rec.get("paper_id", ""),
            "chain_text": rec.get("chain_text", ""),
        })

    if verbose:
        print(f"Selected {len(selected_chains)} chains from {n_top} clusters")
        unique_papers = len(set(c["paper_id"] for c in selected_chains if c["paper_id"]))
        print(f"Unique papers: {unique_papers}")

    return {
        "selected_chains": selected_chains,
        "cluster_stats": cluster_stats,
        "summary": {
            "n_clusters_total": len(sorted_clusters),
            "n_clusters_selected": n_top,
            "n_chains_selected": len(selected_chains),
        }
    }


def save_selection(result: Dict, output_dir: Path) -> None:
    """保存选择结果"""
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "selected_chains.json", 'w', encoding='utf-8') as f:
        json.dump(result["selected_chains"], f, ensure_ascii=False, indent=2)

    with open(output_dir / "selection_stats.json", 'w', encoding='utf-8') as f:
        json.dump({
            "summary": result["summary"],
            "cluster_stats": result["cluster_stats"],
        }, f, indent=2)

    paper_ids = sorted(set(c["paper_id"] for c in result["selected_chains"] if c.get("paper_id")))
    with open(output_dir / "selected_paper_ids.json", 'w', encoding='utf-8') as f:
        json.dump({"count": len(paper_ids), "paper_ids": paper_ids}, f, indent=2)

    print(f"Saved selection to {output_dir}: {len(result['selected_chains'])} chains, {len(paper_ids)} papers")
