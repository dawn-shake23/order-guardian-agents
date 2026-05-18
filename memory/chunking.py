"""
Text Chunking / Splitter — 文本分块器
借鉴 Java TokenTextSplitter 设计，支持：
- 基于语义边界切分（段落、句子）
- Token 数量控制
- Chunk 重叠窗口
- 元数据继承
"""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from core.logger import get_logger


@dataclass
class ChunkConfig:
    """分块配置 — 借鉴 KnowledgeBaseQueryProperties"""
    max_chunk_tokens: int = 800        # 每块最大 token 数
    chunk_overlap_tokens: int = 50     # 块间重叠 token 数
    split_by_paragraph: bool = True    # 优先按段落切分
    split_by_sentence: bool = True     # 段落内按句子切分
    min_chunk_tokens: int = 50         # 最小块 token 数，低于此值的碎片合并到前一块


@dataclass
class TextChunk:
    """文本块"""
    chunk_id: str
    text: str
    token_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_index: int = 0
    total_chunks: int = 0


class TextSplitter:
    """
    文本分块器
    策略：段落切分 → 句子切分 → Token 限制 → 重叠窗口
    """

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()
        self.logger = get_logger("text_splitter")

    def split(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[TextChunk]:
        """
        将文本切分为多个 chunk
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        clean_text = self._clean_text(text)

        # Step 1: 按段落切分
        paragraphs = self._split_paragraphs(clean_text)

        # Step 2: 段落内按句子切分（如果段落过大）
        segments = []
        for para in paragraphs:
            if self._estimate_tokens(para) > self.config.max_chunk_tokens:
                segments.extend(self._split_sentences(para))
            else:
                segments.append(para)

        # Step 3: 按 token 限制合并/拆分
        chunks = self._assemble_chunks(segments, metadata)

        # Step 4: 生成 chunk_id 和索引
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        self.logger.info("文本分块完成", extra={
            "total_chunks": len(chunks),
            "total_tokens": sum(c.token_count for c in chunks),
            "avg_tokens": sum(c.token_count for c in chunks) / max(len(chunks), 1)
        })

        return chunks

    def _clean_text(self, text: str) -> str:
        """文本清洗 — 借鉴 TextCleaningService"""
        # 移除控制字符（保留换行）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        # 规范化换行
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 压缩连续空行（最大2个连续换行）
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 移除行内多余空白
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def _split_paragraphs(self, text: str) -> List[str]:
        """按段落切分"""
        if not self.config.split_by_paragraph:
            return [text]
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_sentences(self, text: str) -> List[str]:
        """按句子切分（中英文兼容）"""
        if not self.config.split_by_sentence:
            # 如果段落仍超大，强制按长度切分
            return self._force_split(text, self.config.max_chunk_tokens)

        # 中英文句子边界
        sentences = re.split(r'(?<=[。！？\.!?\n])(?=[^\s])', text)
        result = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            # 如果单句仍超大，强制切分
            if self._estimate_tokens(sent) > self.config.max_chunk_tokens:
                result.extend(self._force_split(sent, self.config.max_chunk_tokens))
            else:
                result.append(sent)
        return result

    def _force_split(self, text: str, max_tokens: int) -> List[str]:
        """强制按长度切分（兜底方案）"""
        parts = []
        words = text
        chunk_size = max_tokens * 2  # 粗略按字符数估算（中文1字≈1token，英文1词≈1.3token）
        for i in range(0, len(words), chunk_size - self.config.chunk_overlap_tokens * 2):
            part = words[i:i + chunk_size].strip()
            if part:
                parts.append(part)
        return parts

    def _assemble_chunks(self, segments: List[str], base_metadata: Dict[str, Any]) -> List[TextChunk]:
        """将 segments 组装为符合 token 限制的 chunk"""
        chunks = []
        current_segments = []
        current_tokens = 0
        chunk_counter = 0

        for seg in segments:
            seg_tokens = self._estimate_tokens(seg)

            # 如果加入当前 segment 会超出限制，先保存当前 chunk
            if current_tokens + seg_tokens > self.config.max_chunk_tokens and current_segments:
                chunk_text = self._join_with_overlap(chunks, current_segments)
                chunk_counter += 1
                chunks.append(TextChunk(
                    chunk_id=f"chunk_{chunk_counter}",
                    text=chunk_text,
                    token_count=current_tokens,
                    metadata={**base_metadata}
                ))
                current_segments = []
                current_tokens = 0

            current_segments.append(seg)
            current_tokens += seg_tokens

        # 处理最后剩余 segments
        if current_segments:
            if current_tokens < self.config.min_chunk_tokens and chunks:
                # 合并到前一个 chunk
                chunks[-1].text += "\n" + "\n".join(current_segments)
                chunks[-1].token_count += current_tokens
            else:
                chunk_text = self._join_with_overlap(chunks, current_segments)
                chunk_counter += 1
                chunks.append(TextChunk(
                    chunk_id=f"chunk_{chunk_counter}",
                    text=chunk_text,
                    token_count=current_tokens,
                    metadata={**base_metadata}
                ))

        return chunks

    def _join_with_overlap(self, existing_chunks: List[TextChunk], new_segments: List[str]) -> str:
        """拼接时加入与前一块的重叠"""
        new_text = "\n".join(new_segments)
        if not existing_chunks:
            return new_text

        # 从前一个chunk末尾取重叠文本
        prev_text = existing_chunks[-1].text
        overlap_chars = min(self.config.chunk_overlap_tokens * 2, len(prev_text) // 3)
        if overlap_chars > 0:
            overlap_text = prev_text[-overlap_chars:]
            # 在重叠边界处截断（找第一个句子边界）
            boundary = max(
                overlap_text.rfind('。'), overlap_text.rfind('！'),
                overlap_text.rfind('？'), overlap_text.rfind('.'),
                overlap_text.rfind('\n')
            )
            if boundary > 0:
                overlap_text = overlap_text[boundary + 1:]
                if overlap_text.strip():
                    new_text = overlap_text + "\n" + new_text

        return new_text

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Token 数估算（中文≈字符数，英文≈词数*1.3）"""
        chinese_chars = len(re.findall(r'[一-鿿]', text))
        english_words = len(re.findall(r'[a-zA-Z0-9]+', text))
        others = len(text) - chinese_chars - len(re.findall(r'[a-zA-Z0-9\s]', text))
        return chinese_chars + int(english_words * 1.3) + others


class DocumentChunker:
    """
    文档分块器 — 对知识库文档执行分块并生成嵌入
    借鉴 KnowledgeBaseVectorService.vectorizeAndStore()
    """

    def __init__(self, splitter: Optional[TextSplitter] = None, embedding_provider=None):
        self.splitter = splitter or TextSplitter()
        self.embedding = embedding_provider
        self.logger = get_logger("document_chunker")

    def chunk_and_embed(self, doc_id: str, title: str, content: str,
                        biz_domain: str, doc_type: str = "rule",
                        extra_meta: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        对文档进行分块并逐块生成 embedding
        返回: [{embedding, metadata, chunk_text}, ...]
        """
        base_meta = {
            "doc_id": doc_id,
            "title": title,
            "biz_domain": biz_domain,
            "doc_type": doc_type,
            **(extra_meta or {})
        }

        full_text = f"{title}\n{content}"
        chunks = self.splitter.split(full_text, base_meta)

        results = []
        for chunk in chunks:
            chunk_meta = {
                **base_meta,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "content": chunk.text,
            }

            embedding = None
            if self.embedding:
                embedding = self.embedding.encode(chunk.text)

            results.append({
                "embedding": embedding,
                "metadata": chunk_meta,
                "chunk_text": chunk.text,
            })

        self.logger.info("文档分块+嵌入完成", extra={
            "doc_id": doc_id,
            "chunks": len(results),
            "avg_chunk_tokens": sum(c["metadata"].get("chunk_index", 0) for c in results) / max(len(results), 1)
        })

        return results
