from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid

class RelationshipType(str, Enum):
    CORROBORATES = "corroborates"
    CONTRADICTS = "contradicts"
    RECONCILES = "reconciles"
    UNRELATED = "unrelated"

class RawRelationshipResponse(BaseModel):
    relationship: RelationshipType = Field(..., description="Relationship classification between Fact A and Fact B: corroborates, contradicts, reconciles, or unrelated")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    explanation: str = Field(..., description="Detailed human-readable explanation of why these facts corroborate, contradict, or reconcile")
    reconciliation_context: Optional[str] = Field(None, description="Specific context for reconciliation: e.g. temporal divergence, segment vs consolidated, unit conversion/rounding")

class FactRelationship(BaseModel):
    relationship_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    fact_a_id: str
    fact_b_id: str
    relationship: RelationshipType
    confidence: float
    explanation: str
    reconciliation_context: Optional[str] = None
    detected_by: str = "llm_reasoning"
