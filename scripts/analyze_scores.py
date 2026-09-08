import sys
import numpy as np
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection
from app.services.fact_store import FactStore

def analyze_scores():
    store = FactStore("data/fact_layer.db")
    conn = get_connection("data/fact_layer.db")
    cursor = conn.cursor()

    cursor.execute("SELECT document_id, filename FROM documents")
    docs = cursor.fetchall()
    doc_map = {d["document_id"]: d["filename"] for d in docs}

    # Gather candidate pairs across all distinct documents
    all_pairs = []
    seen = set()

    for d in docs:
        doc_id = d["document_id"]
        # run with lower threshold to inspect the full spectrum down to 0.50
        pairs = store.find_candidate_pairs(target_doc_id=doc_id, top_k_per_fact=3, threshold=0.50)
        for f1, f2, score in pairs:
            # Ensure different physical files
            if doc_map.get(f1.document_id) == doc_map.get(f2.document_id):
                continue
            key = tuple(sorted([f1.fact_id, f2.fact_id]))
            if key in seen:
                continue
            seen.add(key)
            all_pairs.append((f1, f2, score))

    scores = [s for _, _, s in all_pairs]
    scores_arr = np.array(scores)

    print("=" * 80)
    print("SIMILARITY SCORES & CONFIDENCE DISTRIBUTION ANALYSIS")
    print("=" * 80)

    print(f"\n[1] CANDIDATE PAIR SIMILARITY SCORES (Total Unique Cross-Doc Pairs >= 0.50: {len(scores)})")
    print(f"  - Min Score:    {scores_arr.min():.4f}")
    print(f"  - Max Score:    {scores_arr.max():.4f}")
    print(f"  - Mean Score:   {scores_arr.mean():.4f}")
    print(f"  - Median (p50): {np.percentile(scores_arr, 50):.4f}")
    print(f"  - 75th %ile:    {np.percentile(scores_arr, 75):.4f}")
    print(f"  - 90th %ile:    {np.percentile(scores_arr, 90):.4f}")
    print(f"  - 95th %ile:    {np.percentile(scores_arr, 95):.4f}")

    # Buckets
    b_90 = sum(1 for s in scores if s >= 0.90)
    b_80 = sum(1 for s in scores if 0.80 <= s < 0.90)
    b_70 = sum(1 for s in scores if 0.70 <= s < 0.80)
    b_60 = sum(1 for s in scores if 0.60 <= s < 0.70)
    b_50 = sum(1 for s in scores if 0.50 <= s < 0.60)

    print("\n[2] SCORE BRACKET DISTRIBUTION:")
    print(f"  - [0.90 - 1.00] (Near Identical Claims):       {b_90:4d} pairs ({b_90/len(scores)*100:.1f}%)")
    print(f"  - [0.80 - 0.89] (High Semantic Equivalence):   {b_80:4d} pairs ({b_80/len(scores)*100:.1f}%)")
    print(f"  - [0.70 - 0.79] (Strong Contextual Overlap):    {b_70:4d} pairs ({b_70/len(scores)*100:.1f}%)")
    print(f"  - [0.60 - 0.69] (Moderate Semantic Relatedness):{b_60:4d} pairs ({b_60/len(scores)*100:.1f}%)")
    print(f"  - [0.50 - 0.59] (Broad Domain Overlap / Noise): {b_50:4d} pairs ({b_50/len(scores)*100:.1f}%)")

    # Sample representatives from each bracket
    print("\n[3] REPRESENTATIVE PAIRS BY BRACKET:")

    def print_sample(bracket_name, min_s, max_s):
        sample = [(f1, f2, s) for f1, f2, s in all_pairs if min_s <= s < max_s]
        if sample:
            f1, f2, s = sample[0]
            fn1 = doc_map.get(f1.document_id, "Doc 1")
            fn2 = doc_map.get(f2.document_id, "Doc 2")
            print(f"\n  Bracket {bracket_name} (Score: {s:.3f}):")
            print(f"    Doc A ({fn1} p.{f1.page_number}): [{f1.subject}] {f1.predicate} = {f1.object_value} ({f1.period or 'N/A'})")
            print(f"    Doc B ({fn2} p.{f2.page_number}): [{f2.subject}] {f2.predicate} = {f2.object_value} ({f2.period or 'N/A'})")

    print_sample("[0.90 - 1.00]", 0.90, 1.01)
    print_sample("[0.80 - 0.89]", 0.80, 0.90)
    print_sample("[0.70 - 0.79]", 0.70, 0.80)
    print_sample("[0.60 - 0.69]", 0.60, 0.70)
    print_sample("[0.50 - 0.59]", 0.50, 0.60)

    # 4. Fact Extractor Confidence Scores
    cursor.execute("SELECT confidence FROM facts")
    confidences = [r["confidence"] for r in cursor.fetchall()]
    conf_arr = np.array(confidences)
    print("\n[4] FACT EXTRACTION CONFIDENCE SCORES (830 Facts):")
    print(f"  - Min Confidence:    {conf_arr.min():.2f}")
    print(f"  - Max Confidence:    {conf_arr.max():.2f}")
    print(f"  - Mean Confidence:   {conf_arr.mean():.4f}")
    print(f"  - Facts with conf=1.0: {sum(1 for c in confidences if c == 1.0)} ({sum(1 for c in confidences if c == 1.0)/len(confidences)*100:.1f}%)")

    # 5. Grounding Verified Stats
    cursor.execute("SELECT grounding_verified, count(*) as cnt FROM facts GROUP BY grounding_verified")
    g_stats = {r["grounding_verified"]: r["cnt"] for r in cursor.fetchall()}
    print("\n[5] GROUNDING VERIFICATION STATUS:")
    print(f"  - Verified Grounded:   {g_stats.get(1, 0)} ({g_stats.get(1, 0)/len(confidences)*100:.1f}%)")
    print(f"  - Unverified Residual: {g_stats.get(0, 0)} ({g_stats.get(0, 0)/len(confidences)*100:.1f}%)")

    conn.close()

if __name__ == "__main__":
    analyze_scores()
