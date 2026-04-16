from pydantic import BaseModel, Field
from typing import List, Optional

class VectorDocument(BaseModel):
    doc_id: str
    title: str
    content: str
    biz_domain: str = Field(description="order/payment/risk/reconciliation")
    sensitive_level: str = Field(default="internal", description="public/internal/confidential")
    embedding: List[float]
    source: str = Field(default="business_manual")