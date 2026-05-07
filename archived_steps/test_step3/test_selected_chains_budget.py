from src.step3.selected_chains_budget import subsample_selected_chains


def test_subsample_all_when_k_large():
    rows = [
        {"cluster_id": 1, "chain_id": f"c{i}", "paper_id": "p", "chain_text": str(i)}
        for i in range(3)
    ]
    out = subsample_selected_chains(rows, 10, seed=0)
    assert len(out) == 3


def test_subsample_reduces_with_fixed_seed():
    rows = []
    for cid in (1, 2):
        for i in range(10):
            rows.append(
                {
                    "cluster_id": cid,
                    "chain_id": f"{cid}_{i}",
                    "paper_id": "p",
                    "chain_text": str(i),
                    "distance": float(i) * 0.1,
                }
            )
    out = subsample_selected_chains(rows, 5, seed=123)
    assert len(out) == 10
    by = {}
    for r in out:
        by.setdefault(int(r["cluster_id"]), set()).add(r["chain_id"])
    assert len(by[1]) == 5 and len(by[2]) == 5
