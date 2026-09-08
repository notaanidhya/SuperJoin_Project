import sys
from pathlib import Path
from collections import Counter

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

def audit_reasoning():
    conn = get_connection("data/fact_layer.db")
    cursor = conn.cursor()

    print("=" * 80)
    print("PHASE 4 REASONING ENGINE AUDIT: ANOMALIES & DATA LEAKAGE CHECK")
    print("=" * 80)

    # 1. Total relationships in DB
    cursor.execute("""
        SELECT r.relationship_id, r.relationship, r.confidence, r.explanation, r.reconciliation_context, r.detected_by,
               f1.fact_id as f1_id, f1.subject as s1, f1.predicate as p1, f1.object_value as v1, f1.numeric_value as n1, f1.period as per1, f1.unit as u1, f1.page_number as pg1, d1.filename as fn1,
               f2.fact_id as f2_id, f2.subject as s2, f2.predicate as p2, f2.object_value as v2, f2.numeric_value as n2, f2.period as per2, f2.unit as u2, f2.page_number as pg2, d2.filename as fn2
        FROM relationships r
        JOIN facts f1 ON r.fact_a_id = f1.fact_id
        JOIN documents d1 ON f1.document_id = d1.document_id
        JOIN facts f2 ON r.fact_b_id = f2.fact_id
        JOIN documents d2 ON f2.document_id = d2.document_id
    """)
    rows = cursor.fetchall()

    print(f"\n[1] TOTAL RELATIONSHIPS STORED: {len(rows)}")
    type_counts = Counter(r["relationship"] for r in rows)
    for t, c in type_counts.items():
        print(f"  - {t}: {c}")

    # 2. Check for File-Level Data Leakage (Same document pairing)
    same_file_leakage = [r for r in rows if r["fn1"] == r["fn2"]]
    print(f"\n[2] CROSS-DOCUMENT FILE LEAKAGE CHECK:")
    if same_file_leakage:
        print(f"  [!] CRITICAL LEAKAGE DETECTED: {len(same_file_leakage)} relationships compare facts from the same file ({same_file_leakage[0]['fn1']})!")
    else:
        print(f"  [✓] Zero same-file leakage. All {len(rows)} relationships connect strictly distinct PDF files.")

    # 3. Check for Symmetrical / Duplicate Pairs (A-B and B-A)
    pair_keys = [tuple(sorted([r["f1_id"], r["f2_id"]])) for r in rows]
    key_counts = Counter(pair_keys)
    duplicates = [k for k, count in key_counts.items() if count > 1]
    print(f"\n[3] PAIR DEDUPLICATION & SYMMETRY CHECK:")
    if duplicates:
        print(f"  [!] ANOMALY: {len(duplicates)} pairs exist in multiple permutations!")
    else:
        print(f"  [✓] Zero duplicate pairs. All {len(rows)} fact pairs are uniquely directed.")

    # 4. Deep Anomaly Check: Audit by Relationship Type
    print("\n[4] DEEP SEMANTIC CLASSIFICATION AUDIT:")

    # A. Audit CORROBORATES
    print("\n  --- AUDIT: 'corroborates' ---")
    corrobs = [r for r in rows if r["relationship"] == "corroborates"]
    for i, c in enumerate(corrobs, 1):
        num_match = (c["n1"] == c["n2"]) if (c["n1"] is not None and c["n2"] is not None) else "N/A"
        per_match = (c["per1"] == c["per2"]) if (c["per1"] and c["per2"]) else "N/A"
        print(f"    {i}. [{c['fn1']} p.{c['pg1']}] {c['s1']} {c['p1']} = {c['v1']} ({c['per1']})")
        print(f"       [{c['fn2']} p.{c['pg2']}] {c['s2']} {c['p2']} = {c['v2']} ({c['per2']})")
        print(f"       -> Numeric Match: {num_match} | Period Match: {per_match} | Detected By: {c['detected_by']}")
        if num_match is False:
            print(f"       [!] POTENTIAL ANOMALY: Marked corroborates but numbers differ ({c['n1']} != {c['n2']})!")

    # B. Audit CONTRADICTS
    print("\n  --- AUDIT: 'contradicts' ---")
    contras = [r for r in rows if r["relationship"] == "contradicts"]
    for i, c in enumerate(contras, 1):
        print(f"    {i}. [{c['fn1']} p.{c['pg1']}] {c['s1']} {c['p1']} = {c['v1']} ({c['per1']})")
        print(f"       [{c['fn2']} p.{c['pg2']}] {c['s2']} {c['p2']} = {c['v2']} ({c['per2']})")
        print(f"       Reasoning: {c['explanation']}")
        # Check if predicate difference is actually a reconcilable metric divergence
        p1_clean = c['p1'].lower().replace('_', ' ')
        p2_clean = c['p2'].lower().replace('_', ' ')
        if p1_clean != p2_clean:
            print(f"       [!] SEMANTIC SUBTLETY: Predicates differ ('{p1_clean}' vs '{p2_clean}').")
            print(f"           Is this a true factual contradiction, or an accounting definition difference (Adjusted vs Unadjusted)?")

    # C. Audit RECONCILES
    print("\n  --- AUDIT: 'reconciles' ---")
    recons = [r for r in rows if r["relationship"] == "reconciles"]
    for i, c in enumerate(recons, 1):
        print(f"    {i}. [{c['fn1']} p.{c['pg1']}] {c['s1']} {c['p1']} = {c['v1']} ({c['per1']})")
        print(f"       [{c['fn2']} p.{c['pg2']}] {c['s2']} {c['p2']} = {c['v2']} ({c['per2']})")
        print(f"       Context: {c['reconciliation_context']}")
        if not c['reconciliation_context']:
            print(f"       [!] ANOMALY: Missing reconciliation_context for reconciled pair!")

    # D. Audit UNRELATED
    print("\n  --- AUDIT: 'unrelated' ---")
    unrels = [r for r in rows if r["relationship"] == "unrelated"]
    for i, c in enumerate(unrels, 1):
        print(f"    {i}. [{c['fn1']} p.{c['pg1']}] {c['s1']} {c['p1']} = {c['v1']} ({c['per1']})")
        print(f"       [{c['fn2']} p.{c['pg2']}] {c['s2']} {c['p2']} = {c['v2']} ({c['per2']})")
        print(f"       Reasoning: {c['explanation']}")

    conn.close()

if __name__ == "__main__":
    audit_reasoning()
