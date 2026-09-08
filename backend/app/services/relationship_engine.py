import logging
import re
from typing import Optional, List, Tuple, Dict
from app.models.fact import ExtractedFact
from app.models.relationship import RelationshipType, RawRelationshipResponse, FactRelationship
from app.services.llm_client import GeminiClient

from app.config import settings

logger = logging.getLogger(__name__)

REASONING_SYSTEM_INSTRUCTION = (
    "You are an expert financial and macroeconomic data auditor. Your role is to analyze pairs of factual claims "
    "extracted from different authoritative documents (e.g. earnings presentations, annual reports, economic surveys) "
    "and determine their precise factual relationship.\n\n"
    "CLASSIFICATION RULES:\n"
    "1. 'corroborates': Both documents verify and agree on the same claim, metric, and value for the same entity and time period.\n"
    "2. 'contradicts': Genuine factual conflict or institutional forecast divergence. The two documents make incompatible claims "
    "about the exact same metric, entity, and period (e.g. conflicting figures under the exact same definition, or authoritative "
    "institutions issuing conflicting forecasts for the same metric and period such as RBI vs IMF real GDP growth projections).\n"
    "3. 'reconciles': An apparent discrepancy that is resolved by context or definition. Examples:\n"
    "   - Metric Definition & Scope: e.g. Adjusted EBITDA vs standard EBITDA, Service EBITDA vs Total EBITDA, Operating Profit vs PAT. "
    "Variations in metric definitions MUST be classified as 'reconciles', NEVER 'contradicts'.\n"
    "   - Temporal Scope: e.g. Full Year (FY24) vs Single Quarter (Q4 FY24).\n"
    "   - Reporting Scope: e.g. Specific Business Segment (TL / Express Parcel) vs Total Consolidated Company.\n"
    "   - Unit & Scale: e.g. INR Crore vs INR Million (with rounding), % margin vs absolute value.\n"
    "   - Accounting / Basis: e.g. Standalone vs Consolidated, Restated vs Original.\n"
    "   *CRITICAL: If 'reconciles', you MUST populate reconciliation_context explaining the exact cause of difference.*\n"
    "4. 'unrelated': The facts describe different metrics, different entities, or parallel operational attributes that cannot be directly compared."
)

class RelationshipEngine:
    """Reasoning engine to evaluate, classify, and reconcile cross-document fact pairs."""

    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient(model=settings.gemini_reasoning_model)

    def classify_pair(
        self, 
        fact_a: ExtractedFact, 
        fact_b: ExtractedFact, 
        doc_a_name: str = "Document A", 
        doc_b_name: str = "Document B"
    ) -> FactRelationship:
        """Classifies the relationship between two facts using fast-path heuristics or LLM reasoning."""

        # Stage 1: Fast-Path Rule Heuristic (Identical Metric & Value)
        heuristic_rel = self._check_fast_path(fact_a, fact_b)
        if heuristic_rel:
            return heuristic_rel

        # Stage 2: LLM Contextual Reasoning
        prompt = (
            f"Analyze the relationship between Fact A and Fact B below:\n\n"
            f"[FACT A]\n"
            f"Document: {doc_a_name} (Page {fact_a.page_number})\n"
            f"Subject: {fact_a.subject}\n"
            f"Metric (Predicate): {fact_a.predicate}\n"
            f"Stated Value: {fact_a.object_value} (Parsed numeric: {fact_a.numeric_value}, Unit: {fact_a.unit})\n"
            f"Period: {fact_a.period or 'Unspecified'} | Scope: {fact_a.scope or 'Unspecified'}\n"
            f"Evidence Quote: \"{fact_a.verbatim_quote}\"\n\n"
            f"[FACT B]\n"
            f"Document: {doc_b_name} (Page {fact_b.page_number})\n"
            f"Subject: {fact_b.subject}\n"
            f"Metric (Predicate): {fact_b.predicate}\n"
            f"Stated Value: {fact_b.object_value} (Parsed numeric: {fact_b.numeric_value}, Unit: {fact_b.unit})\n"
            f"Period: {fact_b.period or 'Unspecified'} | Scope: {fact_b.scope or 'Unspecified'}\n"
            f"Evidence Quote: \"{fact_b.verbatim_quote}\"\n\n"
            f"Determine whether they corroborate, contradict, reconcile, or are unrelated."
        )

        try:
            res: RawRelationshipResponse = self.client.generate_structured(
                prompt=prompt,
                response_schema=RawRelationshipResponse,
                system_instruction=REASONING_SYSTEM_INSTRUCTION
            )
            return FactRelationship(
                fact_a_id=fact_a.fact_id,
                fact_b_id=fact_b.fact_id,
                relationship=res.relationship,
                confidence=res.confidence,
                explanation=res.explanation,
                reconciliation_context=res.reconciliation_context,
                detected_by="llm_reasoning"
            )
        except Exception as e:
            logger.error(f"[RelationshipEngine] LLM reasoning failed for {fact_a.fact_id} vs {fact_b.fact_id}: {e}")
            return FactRelationship(
                fact_a_id=fact_a.fact_id,
                fact_b_id=fact_b.fact_id,
                relationship=RelationshipType.UNRELATED,
                confidence=0.5,
                explanation=f"Classification failed due to error: {e}",
                detected_by="error_fallback"
            )

    def _check_fast_path(self, fact_a: ExtractedFact, fact_b: ExtractedFact) -> Optional[FactRelationship]:
        """Programmatic fast-path for exact matching metrics to conserve tokens."""
        # Check if both have identical numeric values and identical non-null periods
        if (
            fact_a.numeric_value is not None 
            and fact_b.numeric_value is not None
            and abs(fact_a.numeric_value - fact_b.numeric_value) < 1e-4
            and fact_a.period 
            and fact_b.period 
            and fact_a.period.strip().lower() == fact_b.period.strip().lower()
        ):
            # Check unit compatibility
            u_a = (fact_a.unit or "").strip().lower()
            u_b = (fact_b.unit or "").strip().lower()
            if u_a == u_b or not u_a or not u_b:
                # Check predicate overlap across snake_case words
                words_a = set(fact_a.predicate.lower().replace('_', ' ').split())
                words_b = set(fact_b.predicate.lower().replace('_', ' ').split())
                overlap = words_a & words_b
                # Require at least one meaningful keyword overlap
                if overlap:
                    return FactRelationship(
                        fact_a_id=fact_a.fact_id,
                        fact_b_id=fact_b.fact_id,
                        relationship=RelationshipType.CORROBORATES,
                        confidence=0.98,
                        explanation=(
                            f"Exact programmatic corroboration: Both sources confirm {fact_a.subject} "
                            f"{fact_a.predicate} = {fact_a.object_value} for {fact_a.period}."
                        ),
                        detected_by="rule_heuristic"
                    )
        return None

    def batch_classify(
        self, 
        candidate_pairs: List[Tuple[ExtractedFact, ExtractedFact, float]], 
        doc_names: Optional[Dict[str, str]] = None
    ) -> List[FactRelationship]:
        """Classify a list of candidate pairs and return all substantive relationships (excluding unrelated)."""
        doc_names = doc_names or {}
        relationships: List[FactRelationship] = []

        for f1, f2, score in candidate_pairs:
            doc_a_name = doc_names.get(f1.document_id, "Document A")
            doc_b_name = doc_names.get(f2.document_id, "Document B")

            rel = self.classify_pair(f1, f2, doc_a_name=doc_a_name, doc_b_name=doc_b_name)
            relationships.append(rel)

        return relationships
