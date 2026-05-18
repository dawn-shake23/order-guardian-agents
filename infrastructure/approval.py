import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class ApprovalRequest(BaseModel):
    request_id: str
    order_id: str
    agent_type: str
    action: str
    reason: str
    risk_level: str = "low"
    required_role: str = "operator"
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None


class ApprovalEngine:
    RISK_APPROVAL_MAP = {
        "low": {"auto_approve": True, "required_role": "operator"},
        "medium": {"auto_approve": False, "required_role": "senior_operator"},
        "high": {"auto_approve": False, "required_role": "manager"},
    }

    AUTO_APPROVE_ACTIONS = {"query", "read", "notify"}

    def __init__(self):
        self._pending: Dict[str, ApprovalRequest] = {}
        self._resolved: List[ApprovalRequest] = []

    def submit(self, order_id: str, agent_type: str, action: str,
               reason: str, risk_level: str = "low") -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=f"APR_{int(time.time()*1000)}",
            order_id=order_id,
            agent_type=agent_type,
            action=action,
            reason=reason,
            risk_level=risk_level,
            required_role=self.RISK_APPROVAL_MAP.get(risk_level, {}).get("required_role", "operator")
        )

        if action in self.AUTO_APPROVE_ACTIONS:
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolved_by = "auto"
            self._resolved.append(req)
        elif self.RISK_APPROVAL_MAP.get(risk_level, {}).get("auto_approve", False):
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolved_by = "auto_risk_low"
            self._resolved.append(req)
        else:
            req.status = ApprovalStatus.PENDING
            self._pending[req.request_id] = req

        return req

    def approve(self, request_id: str, approver: str) -> Optional[ApprovalRequest]:
        req = self._pending.pop(request_id, None)
        if req:
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolved_by = approver
            self._resolved.append(req)
        return req

    def reject(self, request_id: str, approver: str) -> Optional[ApprovalRequest]:
        req = self._pending.pop(request_id, None)
        if req:
            req.status = ApprovalStatus.REJECTED
            req.resolved_at = time.time()
            req.resolved_by = approver
            self._resolved.append(req)
        return req

    def escalate(self, request_id: str) -> Optional[ApprovalRequest]:
        req = self._pending.get(request_id)
        if req:
            req.status = ApprovalStatus.ESCALATED
            req.required_role = "manager"
        return req

    def get_pending(self) -> List[ApprovalRequest]:
        return list(self._pending.values())

    def auto_resolve_pending(self):
        for req_id in list(self._pending.keys()):
            req = self._pending.pop(req_id)
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolved_by = "mock_auto"
            self._resolved.append(req)
