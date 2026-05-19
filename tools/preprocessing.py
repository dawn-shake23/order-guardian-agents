"""
Query preprocessing with jieba segmentation.
Chinese tokenization, keyword extraction, stopword filtering.
"""
from typing import List, Optional

import jieba

from config import PreprocessConfig


class QueryPreprocessor:
    """Chinese query preprocessing pipeline."""

    def __init__(self, config: Optional[PreprocessConfig] = None):
        self.config = config or PreprocessConfig()
        self._stopwords: set = self._load_stopwords()

    def _load_stopwords(self) -> set:
        base = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "or", "but", "not", "no", "this", "that", "it", "its",
        }
        if self.config.stopwords_file:
            try:
                with open(self.config.stopwords_file, "r", encoding="utf-8") as f:
                    for line in f:
                        w = line.strip()
                        if w:
                            base.add(w)
            except FileNotFoundError:
                pass
        return base

    def segment(self, text: str) -> List[str]:
        """Tokenize Chinese text into words."""
        if not text:
            return []
        return [w.strip() for w in jieba.cut(text) if w.strip()]

    def extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords, filtering stopwords and short tokens."""
        tokens = self.segment(text)
        keywords: List[str] = []
        for t in tokens:
            t_lower = t.lower()
            if t_lower in self._stopwords:
                continue
            if len(t) < self.config.min_keyword_len:
                continue
            keywords.append(t)
        return keywords[:self.config.max_keywords]

    def clean(self, text: str) -> str:
        """Clean query: segment and rejoin keywords."""
        keywords = self.extract_keywords(text)
        return " ".join(keywords) if keywords else text
