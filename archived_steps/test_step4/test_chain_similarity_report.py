"""chain_similarity 报告生成（纯数据，无 I/O）。"""

from src.step4.chain_similarity_report import build_chain_similarity_report_bundle


def test_build_report_bundle():
    vector_records = [
        {
            "cluster_id": 1,
            "n_chains_in_selection": 3,
            "n_chains_with_vector": 3,
            "pairwise_cosine": {"mean": 0.9, "median": 0.91, "min": 0.85, "max": 0.95, "n_pairs": 3},
        },
        {
            "cluster_id": 2,
            "n_chains_in_selection": 2,
            "n_chains_with_vector": 2,
            "pairwise_cosine": {"mean": 0.5, "median": 0.5, "min": 0.5, "max": 0.5, "n_pairs": 1},
        },
    ]
    llm_rows = [
        {
            "cluster_id": 1,
            "research_question_alignment": "high",
            "reasoning_path_similarity": "medium",
            "overall_chain_similarity": "high",
            "confidence": "high",
            "rationale_zh": "测试理由",
        }
    ]
    md, js = build_chain_similarity_report_bundle(vector_records, llm_rows, {"n_clusters": 2})
    assert "# 思维链相似度评估报告" in md
    assert "cluster_id" in md
    assert js["vector_aggregate"]["n_clusters"] == 2
    assert js["llm_aggregate"]["n_llm_ok"] == 1
