import sys
import json
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.showcase_service import ShowcaseService

def main():
    service = ShowcaseService()
    cases = service.get_canonical_showcases()

    print("=" * 80)
    print("SUPERJOIN FACT KNOWLEDGE LAYER: THE 4 CANONICAL SHOWCASE CASES")
    print("=" * 80)

    for c in cases:
        print(f"\n{'#' * 80}")
        print(f"CASE {c.case_number}: {c.category.upper()} — {c.title}")
        print(f"{'#' * 80}")
        print(f"Confidence: {(c.confidence * 100):.0f}% | Summary: {c.summary}\n")

        if c.category == "failure_analysis":
            d = c.diagnostics or {}
            print("[FAILURE ANALYSIS & RECOVERY METRICS]")
            for k, v in d.items():
                if isinstance(v, dict):
                    print(f"\n  * {v.get('name', k)}:")
                    for sub_k, sub_v in v.items():
                        if sub_k != "name":
                            print(f"      - {sub_k.replace('_', ' ').capitalize()}: {sub_v}")
                else:
                    print(f"  * {k}: {v}")
            print(f"\nAudit Explanation:\n  {c.explanation}")
            continue

        print(f"[FACT A]")
        print(f"  Document: {c.fact_a['document']} (Page {c.fact_a['page_number']})")
        print(f"  Claim:    {c.fact_a['subject']} -> {c.fact_a['metric']} = {c.fact_a['stated_value']} ({c.fact_a['period']})")
        print(f"  Quote:    \"{c.fact_a['verbatim_quote']}\"")
        print(f"  Grounded: {'[OK] Verified with exact character offset' if c.fact_a['grounding_verified'] else '[FAIL]'}")

        print(f"\n[FACT B]")
        print(f"  Document: {c.fact_b['document']} (Page {c.fact_b['page_number']})")
        print(f"  Claim:    {c.fact_b['subject']} -> {c.fact_b['metric']} = {c.fact_b['stated_value']} ({c.fact_b['period']})")
        print(f"  Quote:    \"{c.fact_b['verbatim_quote']}\"")
        print(f"  Grounded: {'[OK] Verified with exact character offset' if c.fact_b['grounding_verified'] else '[FAIL]'}")

        if c.reconciliation_context:
            print(f"\n[RECONCILIATION CONTEXT]")
            print(f"  {c.reconciliation_context}")

        print(f"\n[ENGINE REASONING & EXPLANATION]")
        print(f"  {c.explanation}")

    print("\n" + "=" * 80)
    print("ALL 4 SHOWCASE CASES REPRODUCED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    main()
