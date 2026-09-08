import sqlite3
import numpy as np
from typing import List, Tuple, Optional
from app.database import get_connection
from app.models.schemas import ParsedDocument
from app.models.fact import ExtractedFact
from app.models.relationship import FactRelationship, RelationshipType
from app.services.embedder import Embedder

class FactStore:
    """Unified repository for persisting documents, chunks, facts, and running semantic vector search."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.embedder = Embedder()

    def save_document(self, doc: ParsedDocument):
        conn = get_connection(self.db_path)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents (document_id, filename, filepath, total_pages, status) VALUES (?, ?, ?, ?, ?)",
                (doc.document_id, doc.filename, doc.filepath, doc.total_pages, "indexed")
            )
            for chunk in doc.chunks:
                conn.execute(
                    """INSERT OR REPLACE INTO document_chunks 
                       (chunk_id, document_id, page_number, chunk_index, text, section_header, is_table, char_start, char_end)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (chunk.chunk_id, doc.document_id, chunk.page_number, chunk.chunk_index, chunk.text, 
                     chunk.section_header, 1 if chunk.is_table else 0, chunk.char_start, chunk.char_end)
                )
        conn.close()

    def save_facts(self, facts: List[ExtractedFact]):
        if not facts:
            return

        # 1. Batch compute embeddings
        texts_to_embed = [self.embedder.format_fact_for_embedding(f) for f in facts]
        embeddings = self.embedder.embed_batch(texts_to_embed)

        conn = get_connection(self.db_path)
        with conn:
            for fact, emb in zip(facts, embeddings):
                # Ensure foreign key parents exist
                conn.execute(
                    "INSERT OR IGNORE INTO documents (document_id, filename, filepath, total_pages) VALUES (?, ?, ?, ?)",
                    (fact.document_id, "auto_generated", "", fact.page_number)
                )
                conn.execute(
                    """INSERT OR IGNORE INTO document_chunks 
                       (chunk_id, document_id, page_number, chunk_index, text, char_start, char_end)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (fact.chunk_id, fact.document_id, fact.page_number, 0, fact.verbatim_quote, 0, len(fact.verbatim_quote))
                )
                blob = self.embedder.serialize_vector(emb)
                conn.execute(
                    """INSERT OR REPLACE INTO facts 
                       (fact_id, document_id, chunk_id, page_number, section_header, fact_type, subject, predicate, 
                        object_value, numeric_value, unit, period, scope, verbatim_quote, confidence, qualifiers, 
                        grounding_verified, char_offset_in_chunk, embedding_blob)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fact.fact_id, fact.document_id, fact.chunk_id, fact.page_number, fact.section_header,
                     fact.fact_type, fact.subject, fact.predicate, fact.object_value, fact.numeric_value,
                     fact.unit, fact.period, fact.scope, fact.verbatim_quote, fact.confidence, fact.qualifiers,
                     1 if fact.grounding_verified else 0, fact.char_offset_in_chunk, blob)
                )
        conn.close()

    def get_facts_by_document(self, document_id: str) -> List[ExtractedFact]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM facts WHERE document_id = ?", (document_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_fact(r) for r in rows]

    def get_all_facts(self) -> List[ExtractedFact]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM facts")
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_fact(r) for r in rows]

    def search_similar_facts(self, query: str, top_k: int = 10, exclude_doc_id: Optional[str] = None) -> List[Tuple[ExtractedFact, float]]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        if exclude_doc_id:
            cursor.execute("SELECT fact_id, embedding_blob FROM facts WHERE document_id != ? AND embedding_blob IS NOT NULL", (exclude_doc_id,))
        else:
            cursor.execute("SELECT fact_id, embedding_blob FROM facts WHERE embedding_blob IS NOT NULL")
        rows = cursor.fetchall()

        if not rows:
            conn.close()
            return []

        query_vec = self.embedder.embed_text(query)
        scored_ids = []

        for r in rows:
            blob = r["embedding_blob"]
            fact_vec = self.embedder.deserialize_vector(blob)
            sim = float(np.dot(query_vec, fact_vec))
            scored_ids.append((r["fact_id"], sim))

        scored_ids.sort(key=lambda x: x[1], reverse=True)
        top_matches = scored_ids[:top_k]

        # Hydrate only the top_k winning records
        id_to_score = {fid: sim for fid, sim in top_matches}
        placeholders = ",".join("?" * len(id_to_score))
        cursor.execute(f"SELECT * FROM facts WHERE fact_id IN ({placeholders})", list(id_to_score.keys()))
        full_rows = cursor.fetchall()
        conn.close()

        hydrated_facts = {r["fact_id"]: self._row_to_fact(r) for r in full_rows}
        return [(hydrated_facts[fid], sim) for fid, sim in top_matches if fid in hydrated_facts]

    def find_candidate_pairs(self, target_doc_id: str, top_k_per_fact: int = 5, threshold: float = 0.65) -> List[Tuple[ExtractedFact, ExtractedFact, float]]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # Retrieve target filename to enforce physical file-level separation
        cursor.execute("SELECT filename FROM documents WHERE document_id = ?", (target_doc_id,))
        doc_row = cursor.fetchone()
        target_filename = doc_row["filename"] if doc_row else None

        # Strictly quarantine ungrounded facts: only compare verified facts
        cursor.execute("SELECT * FROM facts WHERE document_id = ? AND grounding_verified = 1", (target_doc_id,))
        target_rows = cursor.fetchall()

        if target_filename and target_filename != "auto_generated":
            # Exclude facts from any document entry sharing the same underlying file, and require grounding_verified = 1
            cursor.execute("""
                SELECT f.* FROM facts f
                JOIN documents d ON f.document_id = d.document_id
                WHERE d.filename != ? AND f.grounding_verified = 1
            """, (target_filename,))
        else:
            cursor.execute("SELECT * FROM facts WHERE document_id != ? AND grounding_verified = 1", (target_doc_id,))
        other_rows = cursor.fetchall()
        conn.close()

        if not target_rows or not other_rows:
            return []

        target_facts = [self._row_to_fact(r) for r in target_rows]
        other_facts = [self._row_to_fact(r) for r in other_rows]

        target_matrix = np.array([self.embedder.deserialize_vector(r["embedding_blob"]) for r in target_rows])
        other_matrix = np.array([self.embedder.deserialize_vector(r["embedding_blob"]) for r in other_rows])

        # Matrix multiply: [N, 384] x [384, M] -> [N, M] cosine similarities
        similarity_matrix = np.dot(target_matrix, other_matrix.T)

        candidate_pairs = []
        for i, t_fact in enumerate(target_facts):
            sims = similarity_matrix[i]
            # Top-K indices above threshold
            top_indices = np.argsort(sims)[::-1][:top_k_per_fact]
            for j in top_indices:
                score = float(sims[j])
                if score >= threshold:
                    candidate_pairs.append((t_fact, other_facts[j], score))

        return candidate_pairs

    @staticmethod
    def _row_to_fact(r: sqlite3.Row) -> ExtractedFact:
        return ExtractedFact(
            fact_id=r["fact_id"],
            document_id=r["document_id"],
            chunk_id=r["chunk_id"],
            page_number=r["page_number"],
            section_header=r["section_header"],
            fact_type=r["fact_type"],
            subject=r["subject"],
            predicate=r["predicate"],
            object_value=r["object_value"],
            numeric_value=r["numeric_value"],
            unit=r["unit"],
            period=r["period"],
            scope=r["scope"],
            verbatim_quote=r["verbatim_quote"],
            confidence=r["confidence"],
            qualifiers=r["qualifiers"],
            grounding_verified=bool(r["grounding_verified"]),
            char_offset_in_chunk=r["char_offset_in_chunk"]
        )

    def save_relationship(self, rel: FactRelationship):
        conn = get_connection(self.db_path)
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO relationships 
                   (relationship_id, fact_a_id, fact_b_id, relationship, confidence, explanation, reconciliation_context, detected_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rel.relationship_id, rel.fact_a_id, rel.fact_b_id, 
                 rel.relationship.value if hasattr(rel.relationship, 'value') else rel.relationship,
                 rel.confidence, rel.explanation, rel.reconciliation_context, rel.detected_by)
            )
        conn.close()

    def save_relationships(self, rels: List[FactRelationship]):
        if not rels:
            return
        conn = get_connection(self.db_path)
        with conn:
            for rel in rels:
                conn.execute(
                    """INSERT OR REPLACE INTO relationships 
                       (relationship_id, fact_a_id, fact_b_id, relationship, confidence, explanation, reconciliation_context, detected_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rel.relationship_id, rel.fact_a_id, rel.fact_b_id, 
                     rel.relationship.value if hasattr(rel.relationship, 'value') else rel.relationship,
                     rel.confidence, rel.explanation, rel.reconciliation_context, rel.detected_by)
                )
        conn.close()

    def get_relationships(self, rel_type: Optional[str] = None) -> List[FactRelationship]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        if rel_type:
            cursor.execute("SELECT * FROM relationships WHERE relationship = ?", (rel_type,))
        else:
            cursor.execute("SELECT * FROM relationships")
        rows = cursor.fetchall()
        conn.close()
        return [
            FactRelationship(
                relationship_id=r["relationship_id"],
                fact_a_id=r["fact_a_id"],
                fact_b_id=r["fact_b_id"],
                relationship=RelationshipType(r["relationship"]),
                confidence=r["confidence"],
                explanation=r["explanation"],
                reconciliation_context=r["reconciliation_context"],
                detected_by=r["detected_by"]
            )
            for r in rows
        ]

    def get_fact_by_id(self, fact_id: str) -> Optional[ExtractedFact]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_fact(row) if row else None
