import sys
import argparse
from pathlib import Path

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
from app.models.relationship import RelationshipType
from app.services.fact_store import FactStore
from app.services.relationship_engine import RelationshipEngine

def main():
    parser = argparse.ArgumentParser(description="Cross-Document Reasoning Engine Runner")
    parser.add_argument("--threshold", type=float, default=0.72, help="Minimum cosine similarity for pairing (default: 0.72)")
    parser.add_argument("--max-pairs", type=int, default=30, help="Maximum candidate pairs to evaluate (default: 30)")
    parser.add_argument("--db-path", type=str, default="data/fact_layer.db", help="Path to SQLite database")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = str(project_root / args.db_path)

    store = FactStore(db_path=db_path)
    engine = RelationshipEngine()

    print("=" * 80)
    print("CROSS-DOCUMENT REASONING ENGINE")
    print(f"Database:        {db_path}")
    print(f"Similarity Cutoff: >= {args.threshold} | Max Pairs: {args.max_pairs}")
    print("=" * 80)

    # 1. Fetch documents
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT document_id, filename FROM documents")
    docs = cursor.fetchall()
    doc_map = {d["document_id"]: d["filename"] for d in docs}
    conn.close()

    # 2. Gather candidate pairs across documents
    candidates = []
    seen = set()

    for d in docs:
        doc_id = d["document_id"]
        pairs = store.find_candidate_pairs(target_doc_id=doc_id, top_k_per_fact=2, threshold=args.threshold)
        for f1, f2, score in pairs:
            if doc_map.get(f1.document_id) == doc_map.get(f2.document_id):
                continue
            key = tuple(sorted([f1.fact_id, f2.fact_id]))
            if key in seen:
                continue
            seen.add(key)
            candidates.append((f1, f2, score))

    # Sort by similarity score descending
    candidates.sort(key=lambda x: x[2], reverse=True)
    candidates_to_eval = candidates[:args.max_pairs]

    print(f"\nDiscovered {len(candidates)} unique cross-document candidate pairs (>= {args.threshold}).")
    print(f"Evaluating top {len(candidates_to_eval)} pairs through the Reasoning Engine...\n")

    relationships = []
    corroborations = []
    reconciliations = []
    contradictions = []
    unrelated = []

    for idx, (f1, f2, score) in enumerate(candidates_to_eval, 1):
        doc_a_name = doc_map.get(f1.document_id, "Doc A")
        doc_b_name = doc_map.get(f2.document_id, "Doc B")

        rel = engine.classify_pair(f1, f2, doc_a_name=doc_a_name, doc_b_name=doc_b_name)
        store.save_relationship(rel)
        relationships.append((rel, f1, f2, doc_a_name, doc_b_name, score))

        tag = rel.relationship.value.upper()
        print(f"[{idx}/{len(candidates_to_eval)}] {tag} (conf: {rel.confidence:.2f}, by: {rel.detected_by}, sim: {score:.3f})")
        print(f"  Fact A ({doc_a_name} p.{f1.page_number}): [{f1.subject}] {f1.predicate} = {f1.object_value} ({f1.period or 'N/A'})")
        print(f"  Fact B ({doc_b_name} p.{f2.page_number}): [{f2.subject}] {f2.predicate} = {f2.object_value} ({f2.period or 'N/A'})")
        print(f"  Reasoning: {rel.explanation}")
        if rel.reconciliation_context:
            print(f"  Reconciliation Context: {rel.reconciliation_context}")
        print()

        if rel.relationship == RelationshipType.CORROBORATES:
            corroborations.append((rel, f1, f2, doc_a_name, doc_b_name))
        elif rel.relationship == RelationshipType.RECONCILES:
            reconciliations.append((rel, f1, f2, doc_a_name, doc_b_name))
        elif rel.relationship == RelationshipType.CONTRADICTS:
            contradictions.append((rel, f1, f2, doc_a_name, doc_b_name))
        else:
            unrelated.append((rel, f1, f2, doc_a_name, doc_b_name))

    print("=" * 80)
    print("REASONING ENGINE SUMMARY")
    print("=" * 80)
    print(f"Total Evaluated:   {len(candidates_to_eval)}")
    print(f"  - Corroborates:  {len(corroborations)}")
    print(f"  - Reconciles:    {len(reconciliations)}")
    print(f"  - Contradicts:   {len(contradictions)}")
    print(f"  - Unrelated:     {len(unrelated)}")

    # Total in database
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT relationship, count(*) as cnt FROM relationships GROUP BY relationship")
    print("\nTotal Relationships Persisted in SQLite:")
    for r in cursor.fetchall():
        print(f"  - {r['relationship']}: {r['cnt']}")
    conn.close()
    print("=" * 80)

if __name__ == "__main__":
    main()
