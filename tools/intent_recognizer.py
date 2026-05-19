"""
Rule-based intent recognition via keyword matching.

Design: lightweight keyword matching for domain classification.
Interface reserved for future ERNIE/BERT upgrade via IntentRecognizerBase.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from config import IntentConfig


class IntentRecognizerBase(ABC):
    """Abstract intent recognizer. Implement for ERNIE/BERT upgrade."""

    @abstractmethod
    def recognize(self, query: str) -> str:
        ...


class RuleIntentRecognizer(IntentRecognizerBase):
    """Lightweight rule-based intent recognition by keyword matching."""

    def __init__(self, config: Optional[IntentConfig] = None):
        self.config = config or IntentConfig()
        self.default_domain = self.config.default_domain

    def recognize(self, query: str) -> str:
        """Return domain label by scoring keyword matches."""
        if not query:
            return self.default_domain
        query_lower = query.lower()
        best_domain = self.default_domain
        best_score = 0
        for domain, keywords in self.config.domain_keywords.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > best_score:
                best_score = score
                best_domain = domain
        return best_domain

    def recognize_with_confidence(self, query: str) -> tuple:
        """Return (domain, confidence_score, matched_keywords)."""
        if not query:
            return self.default_domain, 0.0, []
        query_lower = query.lower()
        best_domain = self.default_domain
        best_score = 0
        best_matched: List[str] = []
        for domain, keywords in self.config.domain_keywords.items():
            matched = [kw for kw in keywords if kw in query_lower]
            score = len(matched)
            if score > best_score:
                best_score = score
                best_domain = domain
                best_matched = matched
        max_possible = max(len(v) for v in self.config.domain_keywords.values())
        confidence = best_score / max(max_possible, 1)
        return best_domain, round(confidence, 3), best_matched
