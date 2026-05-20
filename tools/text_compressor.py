"""
Text compression and content summarization for long documents, batch logs, and verbose rules.

Strategies:
  - Extractive: key sentence selection by TF-IDF scoring
  - Hierarchical: recursive summarization for very long texts
  - Metadata-preserving: retain error codes, amounts, dates during compression
"""
import re
import math
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

from core.logger import get_logger


class TextCompressor:
    """
    Compress long documents into concise summaries.
    Preserves structured data (error codes, amounts, dates) while removing redundancy.
    """

    def __init__(self, max_output_tokens: int = 500, min_sentence_length: int = 10):
        self.max_tokens = max_output_tokens
        self.min_sentence_len = min_sentence_length
        self.logger = get_logger("text_compressor")

    def compress(self, text: str, preserve_patterns: Optional[List[str]] = None) -> str:
        """Main entry: compress text while preserving critical patterns."""
        if self._estimate_tokens(text) <= self.max_tokens:
            return text
        sentences = self._split_sentences(text)
        if len(sentences) <= 3:
            return text
        preserve_patterns = preserve_patterns or [
            r'E\d{4}', r'\d+\.\d{2}', r'ORD\d{5,}', r'PAY\d{5,}',
            r'\d{4}-\d{2}-\d{2}', r'R\d{3}', r'TXN\d+',
        ]
        preserved_spans = self._extract_preserved(text, preserve_patterns)
        scored = self._score_sentences(sentences)
        scored.sort(key=lambda x: x[1], reverse=True)

        selected = []
        used_tokens = 0
        budget = self.max_tokens - 50

        for sent, score in scored:
            tokens = self._estimate_tokens(sent)
            if used_tokens + tokens > budget:
                break
            selected.append((sent, score))
            used_tokens += tokens

        selected.sort(key=lambda x: sentences.index(x[0]))
        result = "。".join(s[0] for s in selected) + "。"

        for span in preserved_spans:
            if span not in result:
                result += f"\n[preserved] {span}"

        self.logger.info("compression_done", extra={
            "original_tokens": self._estimate_tokens(text),
            "compressed_tokens": self._estimate_tokens(result),
            "ratio": round(len(result) / max(len(text), 1), 2),
        })
        return result

    def summarize_batch(self, documents: List[str], max_per_doc: int = 200) -> str:
        """Summarize a batch of documents into a single coherent summary."""
        summaries = []
        for doc in documents:
            compressed = self.compress(doc)
            if len(compressed) > max_per_doc:
                compressed = compressed[:max_per_doc] + "..."
            summaries.append(compressed)
        combined = "\n\n---\n\n".join(summaries)
        if self._estimate_tokens(combined) > self.max_tokens:
            combined = self.compress(combined)
        return combined

    def extract_key_info(self, text: str) -> Dict[str, Any]:
        """Extract structured key information from text."""
        info: Dict[str, Any] = {}
        error_codes = re.findall(r'E\d{4}', text)
        if error_codes:
            info["error_codes"] = list(set(error_codes))
        order_ids = re.findall(r'ORD\d{5,}', text)
        if order_ids:
            info["order_ids"] = list(set(order_ids))
        amounts = re.findall(r'(\d+\.\d{2})', text)
        if amounts:
            info["amounts"] = amounts[:5]
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', text)
        if dates:
            info["dates"] = dates[:5]
        rule_ids = re.findall(r'R\d{3}', text)
        if rule_ids:
            info["rule_ids"] = list(set(rule_ids))
        return info

    def _split_sentences(self, text: str) -> List[str]:
        raw = re.split(r'(?<=[。。！!？?\.;；\n])(?=[^\s])', text)
        return [s.strip() for s in raw if len(s.strip()) >= self.min_sentence_len]

    def _score_sentences(self, sentences: List[str]) -> List[Tuple[str, float]]:
        all_text = " ".join(sentences)
        words = re.findall(r'[\w一-鿿]+', all_text.lower())
        word_freq = Counter(words)
        max_freq = max(word_freq.values()) if word_freq else 1
        scored = []
        for sent in sentences:
            sent_words = re.findall(r'[\w一-鿿]+', sent.lower())
            if not sent_words:
                scored.append((sent, 0.0))
                continue
            tfidf_sum = sum(word_freq.get(w, 0) / max_freq for w in sent_words)
            has_error = 1.5 if re.search(r'E\d{4}', sent) else 1.0
            has_amount = 1.3 if re.search(r'\d+\.\d{2}', sent) else 1.0
            has_action = 1.2 if re.search(r'(处理|方案|步骤|建议|规则)', sent) else 1.0
            position_bonus = 1.1 if sentences.index(sent) < len(sentences) * 0.3 else 1.0
            score = tfidf_sum * has_error * has_amount * has_action * position_bonus
            scored.append((sent, round(score, 4)))
        return scored

    def _extract_preserved(self, text: str, patterns: List[str]) -> List[str]:
        spans = []
        for pat in patterns:
            spans.extend(re.findall(pat, text))
        return list(set(spans))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        chinese = len(re.findall(r'[一-鿿]', text))
        english = len(re.findall(r'[a-zA-Z0-9]+', text))
        return chinese + int(english * 1.3)


class LogCompressor:
    """Compress verbose batch logs into structured summaries."""

    def compress_logs(self, log_lines: List[str], max_lines: int = 20) -> str:
        if len(log_lines) <= max_lines:
            return "\n".join(log_lines)
        head = log_lines[:5]
        tail = log_lines[-5:]
        error_lines = [l for l in log_lines if "ERROR" in l or "FAIL" in l or "error" in l.lower()]
        summary = f"[{len(log_lines)} lines total, {len(error_lines)} errors]"
        return "\n".join(head + [f"... ({len(log_lines) - 10} lines omitted) ...", summary] + tail)
