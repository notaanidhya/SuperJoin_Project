from pydantic import BaseModel, Field
from typing import Optional, List
import uuid

class RawExtractedFact(BaseModel):
    source_chunk_index: int = Field(0, description="0-indexed index of the chunk in the batch that contains this fact")
    fact_type: str = Field(..., description="Category: e.g. financial_metric, operational_metric, macroeconomic_indicator, corporate_governance")
    subject: str = Field(..., description="The entity the claim is about (e.g. Delhivery, India, Reserve Bank of India)")
    predicate: str = Field(..., description="Specific metric or property in snake_case (e.g. revenue_from_operations, real_gdp_growth, active_customers)")
    object_value: str = Field(..., description="The value as stated in text (e.g. ₹8,109 Cr, 6.5%, Sahil Barua)")
    numeric_value: Optional[float] = Field(None, description="Parsed numeric value if applicable, else null")
    unit: Optional[str] = Field(None, description="Unit of measurement (e.g. INR Crore, %, million), else null")
    period: Optional[str] = Field(None, description="Time frame (e.g. FY24, Q4 FY24, 2024-25), else null")
    scope: Optional[str] = Field(None, description="Scope (e.g. consolidated, standalone, national), else null")
    verbatim_quote: str = Field(..., description="Exact snippet directly from the source text confirming this fact")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    qualifiers: Optional[str] = Field(None, description="Additional context or notes, e.g. 'basis: IFRS'")

class FactExtractionResponse(BaseModel):
    facts: List[RawExtractedFact] = Field(default_factory=list)

class ExtractedFact(RawExtractedFact):
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    chunk_id: str
    page_number: int
    section_header: Optional[str] = None
    grounding_verified: bool = False
    char_offset_in_chunk: Optional[int] = None
