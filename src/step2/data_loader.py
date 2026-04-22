"""
数据加载模块 - 从 TOS 加载 reasoning_chain.xml 和论文 MD 文件
"""

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import tos

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _normalize_tos_endpoint(endpoint: str) -> str:
    """将 S3 格式的 endpoint 转换为 TOS SDK 格式"""
    e = (endpoint or "").strip()
    if e.startswith("tos-s3-"):
        return "tos-" + e[len("tos-s3-"):]
    return e


def _get_tos_client(config: dict) -> tos.TosClientV2:
    endpoint = _normalize_tos_endpoint(
        os.getenv("TOS_ENDPOINT", config.get("endpoint", "tos-cn-beijing.volces.com"))
    )
    return tos.TosClientV2(
        os.getenv("TOS_ACCESS_KEY", config.get("access_key", "")),
        os.getenv("TOS_SECRET_KEY", config.get("secret_key", "")),
        endpoint,
        os.getenv("TOS_REGION", config.get("region", "cn-beijing")),
    )


_tos_tls = threading.local()


def get_tos_client(config: dict) -> tos.TosClientV2:
    client = getattr(_tos_tls, "client", None)
    if client is None:
        client = _get_tos_client(config)
        _tos_tls.client = client
    return client


def normalize_paper_id(paper_id: str) -> str:
    """将 paper_id 中的特殊字符转为文件系统安全格式"""
    return paper_id.replace("/", "%2F")


@dataclass
class PaperData:
    paper_id: str
    reasoning_xml: str
    paper_md: str


def download_text(client: tos.TosClientV2, bucket: str, key: str) -> str:
    obj = client.get_object(bucket, key)
    return obj.read().decode("utf-8")


def load_paper_data(paper_id: str, tos_config: dict) -> Optional[PaperData]:
    """加载单篇论文的 reasoning_chain.xml 和 MD 文件"""
    client = get_tos_client(tos_config)
    bucket = tos_config["bucket"]
    fs_id = normalize_paper_id(paper_id)

    xml_key = f"{tos_config['xml_source_prefix']}{fs_id}_reasoning_chain.xml"
    md_key_candidates = [
        f"{tos_config['md_prefix']}{fs_id}.md",
        f"{tos_config['md_prefix']}{paper_id}.md",
    ]

    try:
        reasoning_xml = download_text(client, bucket, xml_key)
    except Exception as e:
        print(f"[Step2] Failed to load XML for {paper_id}: {e}")
        return None

    paper_md = None
    for md_key in md_key_candidates:
        try:
            paper_md = download_text(client, bucket, md_key)
            break
        except Exception:
            continue

    if paper_md is None:
        print(f"[Step2] Failed to load MD for {paper_id}")
        return None

    return PaperData(paper_id=paper_id, reasoning_xml=reasoning_xml, paper_md=paper_md)


def list_paper_ids(tos_config: dict, limit: Optional[int] = None) -> List[str]:
    """列举 TOS 上所有有 reasoning_chain.xml 的 paper_id"""
    client = get_tos_client(tos_config)
    bucket = tos_config["bucket"]
    prefix = tos_config["xml_source_prefix"]
    suffix = "_reasoning_chain.xml"

    paper_ids = []
    marker = ""
    while True:
        result = client.list_objects(bucket, prefix=prefix, marker=marker, max_keys=1000)
        for item in getattr(result, "contents", None) or []:
            key = item.key
            if not key.endswith(suffix):
                continue
            base = key.split("/")[-1]
            pid = base[: -len(suffix)]
            if pid:
                paper_ids.append(pid)
                if limit and len(paper_ids) >= limit:
                    return paper_ids
        if not result.is_truncated:
            break
        marker = result.next_marker

    return paper_ids


def output_key(paper_id: str, tos_config: dict) -> str:
    fs_id = normalize_paper_id(paper_id)
    return f"{tos_config['output_prefix']}{fs_id}_reasoning_chain_refine.xml"


def output_exists(paper_id: str, tos_config: dict) -> bool:
    client = get_tos_client(tos_config)
    return client.does_object_exist(tos_config["bucket"], output_key(paper_id, tos_config))


def upload_xml(paper_id: str, xml_text: str, tos_config: dict) -> str:
    client = get_tos_client(tos_config)
    key = output_key(paper_id, tos_config)
    client.put_object(tos_config["bucket"], key, content=xml_text.encode("utf-8"))
    return key
