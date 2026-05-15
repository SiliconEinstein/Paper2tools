#!/usr/bin/env python3
"""Rewrite research_questions_50_samples/*.json to the compact evaluation schema."""

from __future__ import annotations

import json
import re
from pathlib import Path

SAMPLES_DIR = Path("/personal/paper2tools_v2/data/research_questions_50_samples")
DATA_ROOT = Path("/personal/paper2tools_v2/data")
PREFIX_FULL = "研究问题完整表述："


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk / max(len(text), 1)


def latin_ratio(text: str) -> float:
    if not text:
        return 0.0
    lat = len(re.findall(r"[A-Za-z]", text))
    return lat / max(len(text), 1)


def strip_full_prefix(s: str) -> str:
    s = (s or "").strip()
    if s.startswith(PREFIX_FULL):
        return s[len(PREFIX_FULL) :].strip()
    return s


def looks_english(text: str) -> bool:
    if len(text) < 40:
        return False
    return latin_ratio(text) >= 0.38 and cjk_ratio(text) < 0.12


def good_enough_english(text: str | None) -> bool:
    """Looser gate for LaTeX-heavy scientific snippets extracted from XML."""
    if not text or len(text) < 35:
        return False
    if cjk_ratio(text) > 0.12:
        return False
    return looks_english(text) or (
        len(text) >= 50 and latin_ratio(text) >= 0.22
    )


def domain_data_dir(domain: str) -> str:
    d = (domain or "").strip()
    if d.lower() == "superconductivity":
        return "Superconductivity"
    return d


def clean_xml_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_problem_from_xml(xml: str) -> str | None:
    m = re.search(r"<problem\b[^>]*>(.*?)</problem>", xml, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    t = clean_xml_text(m.group(1))
    return t if len(t) >= 60 else None


def extract_conclusion_from_xml(xml: str, conclusion_id: str) -> str | None:
    cid = conclusion_id.strip()
    if not cid:
        return None
    for m in re.finditer(
        rf'<conclusion_reasoning\b[^>]*\bconclusion_id="{re.escape(cid)}"[^>]*>(.*?)</conclusion_reasoning>',
        xml,
        re.DOTALL,
    ):
        inner = m.group(1)
        cm = re.search(
            rf'<conclusion\b[^>]*\bid="{re.escape(cid)}"[^>]*>(.*?)</conclusion>',
            inner,
            re.DOTALL,
        )
        if cm:
            t = clean_xml_text(cm.group(1))
            if len(t) >= 40:
                return t
    return None


def candidate_xml_paths(domain: str, cluster_id: object, paper_id: str, conclusion_id: str) -> list[Path]:
    sub = domain_data_dir(domain)
    rel = Path(f"cluster_{cluster_id}") / "xml" / f"{paper_id}_{conclusion_id}.xml"
    roots = [DATA_ROOT / sub / "workflows", DATA_ROOT / sub / "workflows_top50"]
    return [root / rel for root in roots]


def english_from_anchor_xml(sample: dict) -> str | None:
    ids_ = sample.get("ids") or {}
    domain = str(ids_.get("domain") or "")
    cluster_id = ids_.get("cluster_id")
    labels = sample.get("labels") or []
    if cluster_id is None or not labels:
        return None
    first = labels[0]
    pid = str(first.get("paper_id") or "").strip()
    cid = str(first.get("conclusion_id") or "").strip()
    if not pid or not cid:
        return None
    xml_path: Path | None = None
    for p in candidate_xml_paths(domain, cluster_id, pid, cid):
        if p.is_file():
            xml_path = p
            break
    if xml_path is None:
        return None
    xml = xml_path.read_text(encoding="utf-8", errors="replace")
    prob = extract_problem_from_xml(xml)
    if prob and good_enough_english(prob):
        return prob
    conc = extract_conclusion_from_xml(xml, cid)
    if conc and good_enough_english(conc):
        return conc
    if prob:
        return prob
    return conc


def ensure_english_statement(sample: dict, legacy: dict | None = None) -> str:
    """Prefer legacy English fields; otherwise XML anchor; else empty."""
    if legacy:
        raw = strip_full_prefix(legacy.get("research_problem_full_zh") or "")
        if looks_english(raw):
            return raw
        rq = (legacy.get("research_question_zh") or "").strip()
        if looks_english(rq):
            return rq
    cur = (sample.get("research_question_en") or "").strip()
    if looks_english(cur):
        return cur
    from_xml = english_from_anchor_xml(sample)
    if from_xml:
        return from_xml
    if legacy:
        raw = strip_full_prefix(legacy.get("research_problem_full_zh") or "")
        if len(raw) >= 40:
            return raw
        if len(rq := (legacy.get("research_question_zh") or "").strip()) >= 40:
            return rq
    return cur if latin_ratio(cur) >= 0.45 else ""


def english_problem_statement(obj: dict) -> str:
    raw = strip_full_prefix(obj.get("research_problem_full_zh") or "")
    if looks_english(raw):
        return raw
    rq = (obj.get("research_question_zh") or "").strip()
    if looks_english(rq):
        return rq
    if len(raw) >= 40 and latin_ratio(raw) >= 0.3:
        return raw
    if len(rq) >= 40 and latin_ratio(rq) >= 0.45 and cjk_ratio(rq) < 0.2:
        return rq
    return ""


def chinese_question(obj: dict) -> str:
    rq = (obj.get("research_question_zh") or "").strip()
    if cjk_ratio(rq) >= 0.18:
        return rq
    focus = (obj.get("research_focus_zh") or "该簇核心主题").strip()
    terms = obj.get("key_terms") or []
    if isinstance(terms, str):
        terms = [terms]
    terms = [str(t).strip() for t in terms if str(t).strip()][:6]
    tail = "、".join(terms) if terms else "相关证据与结论"
    return f"围绕「{focus}」，结合簇内思维链，需要在「{tail}」等方向上澄清机理、定量关系、验证边界与主要争议点。"


def normalize_labels(obj: dict) -> list[dict[str, str]]:
    chains = obj.get("related_chains") or []
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for c in chains:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("chain_id") or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        pid = str(c.get("paper_id") or "").strip()
        conc = str(c.get("conclusion_id") or "").strip()
        if not pid and "_" in cid:
            pid, _, rest = cid.partition("_")
            conc = rest or conc
        out.append(
            {
                "chain_id": cid,
                "paper_id": pid,
                "conclusion_id": conc,
            }
        )
    return out


def build_ids(obj: dict) -> dict[str, object]:
    return {
        "sample_id": obj.get("sample_id", ""),
        "domain": obj.get("domain", ""),
        "cluster_id": obj.get("cluster_id"),
    }


def migrate_one(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))

    if (
        "related_chains" not in obj
        and isinstance(obj.get("ids"), dict)
        and isinstance(obj.get("labels"), list)
    ):
        key_terms = obj.get("key_terms") or []
        if not isinstance(key_terms, list):
            key_terms = [key_terms]
        key_terms = [str(x).strip() for x in key_terms if str(x).strip()]
        labels = [dict(x) for x in obj["labels"] if isinstance(x, dict)]
        sample = {
            "ids": dict(obj["ids"]),
            "research_question_zh": (obj.get("research_question_zh") or "").strip(),
            "research_question_en": (obj.get("research_question_en") or "").strip(),
            "key_terms": key_terms,
            "labels": labels,
        }
        sample["research_question_en"] = ensure_english_statement(sample, legacy=None)
        sample["counts"] = {
            "labels": len(sample["labels"]),
            "key_terms": len(sample["key_terms"]),
        }
        return sample

    labels = normalize_labels(obj)
    key_terms = obj.get("key_terms") or []
    if not isinstance(key_terms, list):
        key_terms = [key_terms]
    key_terms = [str(x).strip() for x in key_terms if str(x).strip()]

    sample = {
        "ids": build_ids(obj),
        "research_question_zh": chinese_question(obj),
        "research_question_en": english_problem_statement(obj),
        "key_terms": key_terms,
        "labels": labels,
        "counts": {
            "labels": len(labels),
            "key_terms": len(key_terms),
        },
    }
    sample["research_question_en"] = ensure_english_statement(sample, legacy=obj)
    return sample


def main() -> None:
    files = sorted(SAMPLES_DIR.glob("*.json"))
    if len(files) != 50:
        raise SystemExit(f"expected 50 json files, found {len(files)} under {SAMPLES_DIR}")
    for path in files:
        new_obj = migrate_one(path)
        path.write_text(
            json.dumps(new_obj, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"rewrote {len(files)} files in {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
