"""
Step1 聚类选择结果（selected_chains.json）→ 按 cluster_id 分组，每组一条 Step3 输入。

每组对应一个 workflow（与「每簇一个 workflow」的产品逻辑一致）。
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _is_selected_chain_record(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if "cluster_id" not in row:
        return False
    return "chain_text" in row or "chain_id" in row


def _normalize_cluster_id(raw: Any) -> int:
    if isinstance(raw, bool):
        raise ValueError("invalid cluster_id")
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"unsupported cluster_id: {raw!r}") from e


def _chain_id_conclusion_suffix(chain_id: str, paper_id: str) -> str:
    """chain_id 一般为 `{paper_id}_{conclusion_id}`，与 refine XML 里 conclusion_reasoning/@conclusion_id 对齐。"""
    if not chain_id or not paper_id:
        return ""
    prefix = f"{paper_id}_"
    if str(chain_id).startswith(prefix):
        return str(chain_id)[len(prefix) :]
    return ""


def _refine_body_from_xml_string(
    xml_content: str,
    paper_id: str,
    chain_id: str,
    paper_full_text_cache: Dict[str, str],
    source_label: str,
    fb: str,
) -> str:
    """从已读入的 refine XML 字符串解析正文（与本地文件逻辑一致）。"""
    from src.step3.step2_loader import (
        load_enriched_xml_as_text_from_string,
        try_extract_conclusion_from_refine_xml_string,
    )

    suffix = _chain_id_conclusion_suffix(chain_id, paper_id)
    if suffix:
        chunk = try_extract_conclusion_from_refine_xml_string(
            xml_content, suffix, source_label=source_label
        )
        if chunk and chunk.strip():
            return chunk.strip()
    if paper_id in paper_full_text_cache:
        cached = paper_full_text_cache[paper_id]
        return cached.strip() if cached.strip() else fb
    full = load_enriched_xml_as_text_from_string(xml_content, source_label=source_label)
    if full.strip():
        paper_full_text_cache[paper_id] = full
        return full.strip()
    return fb


def _member_chain_body_for_step3(
    m: Dict[str, Any],
    step2_enriched_dir: Optional[Path],
    paper_full_text_cache: Dict[str, str],
    step2_enrich_tos: Optional[Dict[str, Any]] = None,
) -> str:
    """单条样本正文：优先 TOS 或本地 Step2 refine XML（含工具），否则 Step1 chain_text。"""
    fb = (m.get("chain_text") or "").strip()
    paper_id = str(m.get("paper_id") or "")
    chain_id = str(m.get("chain_id") or "")
    if not paper_id:
        return fb

    if step2_enrich_tos:
        try:
            from src.step2.data_loader import (
                _tos_bucket,
                download_text,
                get_tos_client,
                output_key,
            )
        except Exception:
            step2_enrich_tos = None  # type: ignore
        if step2_enrich_tos:
            key = output_key(paper_id, step2_enrich_tos)
            label = f"tos:{key}"
            try:
                client = get_tos_client(step2_enrich_tos)
                xml_content = download_text(client, _tos_bucket(step2_enrich_tos), key)
            except Exception as e:
                if step2_enriched_dir and step2_enriched_dir.is_dir():
                    pass
                else:
                    return fb
            else:
                return _refine_body_from_xml_string(
                    xml_content,
                    paper_id,
                    chain_id,
                    paper_full_text_cache,
                    label,
                    fb,
                )

    if not step2_enriched_dir or not step2_enriched_dir.is_dir():
        return fb
    from src.step2.data_loader import normalize_paper_id
    from src.step3.step2_loader import (
        load_enriched_xml_as_text,
        try_extract_conclusion_from_refine_xml,
    )

    xp = step2_enriched_dir / f"{normalize_paper_id(paper_id)}_reasoning_chain_refine.xml"
    if not xp.is_file():
        return fb
    suffix = _chain_id_conclusion_suffix(chain_id, paper_id)
    if suffix:
        chunk = try_extract_conclusion_from_refine_xml(xp, suffix)
        if chunk and chunk.strip():
            return chunk.strip()
    if paper_id in paper_full_text_cache:
        cached = paper_full_text_cache[paper_id]
        return cached.strip() if cached.strip() else fb
    full = load_enriched_xml_as_text(xp)
    if full.strip():
        paper_full_text_cache[paper_id] = full
        return full.strip()
    return fb


def _build_cluster_prompt(
    cluster_id: int,
    members: List[Dict[str, Any]],
    step2_enriched_dir: Optional[Path] = None,
    step2_enrich_tos: Optional[Dict[str, Any]] = None,
) -> str:
    """将同一簇的多条链拼成一段文本，供 LLM 归纳为一个 workflow。"""
    lines = [
        f"【聚类簇 ID】cluster_id = {cluster_id}",
        "",
        "以下条目均属于同一向量聚类簇（语义相近的思维链）。每条来自不同论文，已标注 paper_id、chain_id 便于溯源。",
        "正文优先取自 Step2 的 reasoning_chain_refine.xml（TOS 或本地目录，含工具引用与 <tools> 摘要）；若无法获取或无法匹配 conclusion，则回退为 Step1 的 chain_text。",
        "请综合这些思维链中的共同方法论与流程，归纳为一个统一、可复用的工作流（workflow）。",
        "若某些步骤仅在个别样本中出现，可概括到合适的一般化步骤中。",
        "",
    ]
    paper_cache: Dict[str, str] = {}
    for i, m in enumerate(members, 1):
        pid = m.get("paper_id") or ""
        cid = m.get("chain_id") or ""
        dist = m.get("distance")
        body = _member_chain_body_for_step3(
            m, step2_enriched_dir, paper_cache, step2_enrich_tos
        )
        lines.append(f"### 样本 {i}")
        lines.append(f"- paper_id: {pid}")
        lines.append(f"- chain_id: {cid}")
        if dist is not None:
            lines.append(f"- distance_to_center: {dist}")
        lines.append("- 思维链正文:")
        lines.append(body if body else "（无正文）")
        lines.append("")
    return "\n".join(lines)


def try_build_cluster_inputs_from_json(
    path: Path,
    step2_enriched_dir: Optional[Path] = None,
    step2_enrich_tos: Optional[Dict[str, Any]] = None,
) -> Optional[List[Tuple[str, str, Dict[str, Any]]]]:
    """
    若 path 为 Step1 输出的 selected_chains.json 形态，则按簇返回多组输入；
    否则返回 None（由调用方按普通 JSON 单文件处理）。

    Args:
        path: selected_chains.json
        step2_enriched_dir: 若给定且为目录，则簇内每条样本优先从
            ``{normalize_paper_id(paper_id)}_reasoning_chain_refine.xml`` 中按 ``conclusion_id``
            匹配 ``chain_id`` 在 ``paper_id_`` 之后的后缀；否则回退 ``chain_text``。
        step2_enrich_tos: 若给定（与 Step2 相同的 ``tos`` 配置 dict），则优先从 TOS
            ``output_prefix`` 下按 ``output_key(paper_id)`` 下载 refine XML；失败时可再尝试本地目录。

    Returns:
        [(prompt_text, source_id, provenance), ...]，每个元组对应一个簇、一次 workflow 提取。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, list) or not data:
        return None
    if not _is_selected_chain_record(data[0]):
        return None

    by_cluster: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in data:
        if not _is_selected_chain_record(row):
            continue
        try:
            cid = _normalize_cluster_id(row.get("cluster_id"))
        except (ValueError, TypeError):
            continue
        by_cluster[cid].append(row)

    if not by_cluster:
        return None

    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for cluster_id in sorted(by_cluster.keys()):
        members = by_cluster[cluster_id]
        members.sort(key=lambda m: (m.get("distance") is None, m.get("distance") or 0.0))
        text = _build_cluster_prompt(
            cluster_id, members, step2_enriched_dir, step2_enrich_tos
        )
        source_id = f"cluster_{cluster_id}"
        provenance: Dict[str, Any] = {
            "cluster_id": cluster_id,
            "n_chains": len(members),
            "members": [
                {
                    "paper_id": m.get("paper_id", ""),
                    "chain_id": m.get("chain_id", ""),
                    "distance": m.get("distance"),
                }
                for m in members
            ],
        }
        out.append((text, source_id, provenance))

    return out if out else None
