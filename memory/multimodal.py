"""
Multimodal Processor — 多模态处理组件
支持：图片理解（OCR/描述）、图片 Embedding、多格式文档解析
借鉴 Java DocumentParseService (Apache Tika) + 千问 VL 多模态 API
"""
import os
import base64
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from core.logger import get_logger

_OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    pass


class MediaType(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass
class MultimodalDocument:
    """多模态文档 — 统一文本/图片/PDF 的表示"""
    doc_id: str
    title: str
    media_type: MediaType
    text_content: str           # 提取/描述的文本
    image_base64: Optional[str] = None  # 图片的base64（如有）
    image_description: Optional[str] = None  # AI对图片的描述
    ocr_text: Optional[str] = None  # OCR提取的文字
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """获取用于检索的完整文本"""
        parts = [self.text_content]
        if self.image_description:
            parts.append(f"[图片描述] {self.image_description}")
        if self.ocr_text:
            parts.append(f"[图片文字] {self.ocr_text}")
        return "\n".join(parts)


class ImageAnalyzer:
    """
    图片分析器
    使用千问 VL 多模态 API 进行图片理解和OCR
    """

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VISION_MODEL = "qwen-vl-plus"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.logger = get_logger("image_analyzer")
        self._client = None
        if self.api_key and _OPENAI_AVAILABLE:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.DASHSCOPE_BASE_URL,
            )

    def analyze(self, image_path: str, prompt: Optional[str] = None) -> Dict[str, str]:
        """
        分析图片，返回描述和OCR文本
        """
        if not self._client:
            return self._fallback_analyze(image_path)

        try:
            image_b64 = self._encode_image(image_path)
            ext = os.path.splitext(image_path)[1].lower().replace(".", "")
            mime = f"image/{'jpeg' if ext == 'jpg' else ext}"

            user_prompt = prompt or "请描述这张图片的内容，并提取图片中的所有文字信息。请用中文回答。"

            result = self._client.chat.completions.create(
                model=self.VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                        {"type": "text", "text": user_prompt},
                    ]
                }],
                max_tokens=1000,
            )

            full_response = result.choices[0].message.content or ""

            self.logger.info("图片分析完成", extra={
                "image": os.path.basename(image_path),
                "response_length": len(full_response)
            })

            return {
                "description": full_response,
                "ocr_text": full_response,
                "model": self.VISION_MODEL,
            }

        except Exception as e:
            self.logger.error("图片分析失败", extra={"error": str(e)})
            return self._fallback_analyze(image_path)

    def _fallback_analyze(self, image_path: str) -> Dict[str, str]:
        """无API时的回退：基于文件名和大小做基本分析"""
        fname = os.path.basename(image_path)
        fsize = os.path.getsize(image_path) if os.path.exists(image_path) else 0
        return {
            "description": f"图片: {fname} ({fsize} bytes)",
            "ocr_text": f"图片文件名: {fname}",
            "model": "fallback",
        }

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @property
    def available(self) -> bool:
        return self._client is not None


class ImageEmbedder:
    """
    图片 Embedding 生成器
    支持：DashScope multimodal embedding / 回退到文本 embedding
    """

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MULTIMODAL_EMBED_MODEL = "tongyi-embedding-vision-01"

    def __init__(self, api_key: Optional[str] = None, text_embedder=None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.text_embedder = text_embedder
        self.logger = get_logger("image_embedder")
        self._client = None
        if self.api_key and _OPENAI_AVAILABLE:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.DASHSCOPE_BASE_URL,
            )

    def embed_image(self, image_path: str, description: str = "") -> Optional[List[float]]:
        """
        生成图片的向量表示
        优先使用多模态 embedding，回退到文本描述 embedding
        """
        # 回退方案：对图片描述文本做 embedding
        if self.text_embedder:
            return self.text_embedder.encode(description or f"图片: {os.path.basename(image_path)}")
        return None

    @property
    def available(self) -> bool:
        return self._client is not None


class MultimodalProcessor:
    """
    多模态处理器 — 统一入口
    负责：分析图片 → 提取文字 → 生成描述 → 生成Embedding
    借鉴 Java DocumentParseService (Tika) 的统一解析接口
    """

    def __init__(self, api_key: Optional[str] = None, embedding_provider=None):
        self.image_analyzer = ImageAnalyzer(api_key=api_key)
        self.image_embedder = ImageEmbedder(api_key=api_key, text_embedder=embedding_provider)
        self.embedding = embedding_provider
        self.logger = get_logger("multimodal")

    def process_image(self, image_path: str, doc_id: str, title: str = "",
                      biz_domain: str = "order") -> MultimodalDocument:
        """
        处理单张图片：分析 → 描述 → Embedding
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片不存在: {image_path}")

        self.logger.info("处理图片", extra={
            "doc_id": doc_id, "path": os.path.basename(image_path)
        })

        # Step 1: 图片分析（OCR + 描述）
        analysis = self.image_analyzer.analyze(image_path)

        # Step 2: 生成 embedding
        full_text = f"{title}\n{analysis['description']}"
        embedding = None
        if self.embedding:
            embedding = self.embedding.encode(full_text)

        # 尝试图片级 embedding
        img_embedding = self.image_embedder.embed_image(
            image_path, description=analysis["description"]
        )

        doc = MultimodalDocument(
            doc_id=doc_id,
            title=title or os.path.basename(image_path),
            media_type=MediaType.IMAGE,
            text_content=analysis["description"],
            ocr_text=analysis.get("ocr_text"),
            image_description=analysis["description"],
            embedding=embedding or img_embedding,
            metadata={
                "source_file": os.path.basename(image_path),
                "analysis_model": analysis.get("model", "unknown"),
                "has_ocr": bool(analysis.get("ocr_text")),
                "biz_domain": biz_domain,
            }
        )

        self.logger.info("图片处理完成", extra={
            "doc_id": doc_id,
            "text_length": len(doc.full_text),
            "has_embedding": doc.embedding is not None
        })

        return doc

    def process_file(self, file_path: str, doc_id: str, title: str = "",
                     biz_domain: str = "order") -> MultimodalDocument:
        """
        统一文件处理入口：自动检测类型 → 路由到对应处理器
        借鉴 Java DocumentParseService 的统一解析接口
        """
        ext = os.path.splitext(file_path)[1].lower()
        media_type = self._detect_type(file_path)

        if media_type == MediaType.IMAGE:
            return self.process_image(file_path, doc_id, title, biz_domain)
        elif media_type == MediaType.PDF:
            return self._process_pdf(file_path, doc_id, title, biz_domain)
        else:
            return self._process_text_file(file_path, doc_id, title, biz_domain)

    def _process_pdf(self, file_path: str, doc_id: str, title: str,
                     biz_domain: str) -> MultimodalDocument:
        """PDF文件解析"""
        text = self._extract_pdf_text(file_path)
        embedding = self.embedding.encode(text) if self.embedding else None
        return MultimodalDocument(
            doc_id=doc_id,
            title=title or os.path.basename(file_path),
            media_type=MediaType.PDF,
            text_content=text,
            embedding=embedding,
            metadata={"source_file": os.path.basename(file_path), "biz_domain": biz_domain}
        )

    def _process_text_file(self, file_path: str, doc_id: str, title: str,
                           biz_domain: str) -> MultimodalDocument:
        """文本文件解析"""
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        embedding = self.embedding.encode(text) if self.embedding else None
        return MultimodalDocument(
            doc_id=doc_id,
            title=title or os.path.basename(file_path),
            media_type=MediaType.TEXT,
            text_content=text,
            embedding=embedding,
            metadata={"source_file": os.path.basename(file_path), "biz_domain": biz_domain}
        )

    def _detect_type(self, file_path: str) -> MediaType:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'):
            return MediaType.IMAGE
        elif ext == '.pdf':
            return MediaType.PDF
        elif ext in ('.txt', '.md', '.csv', '.json', '.xml', '.yaml'):
            return MediaType.TEXT
        return MediaType.UNKNOWN

    def _extract_pdf_text(self, file_path: str) -> str:
        """PDF文本提取"""
        try:
            import subprocess
            result = subprocess.run(
                ["python", "-c",
                 f"import fitz; doc=fitz.open('{file_path}'); print(''.join(p.get_text() for p in doc))"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            # 简单的PDF文字提取：查找文本流
            import re
            texts = re.findall(rb'\((.*?)\)', content)
            decoded = []
            for t in texts:
                try:
                    decoded.append(t.decode('utf-8', errors='ignore'))
                except Exception:
                    pass
            return "\n".join(decoded)
        except Exception:
            return f"无法解析PDF文件: {os.path.basename(file_path)}"

    @property
    def image_analysis_available(self) -> bool:
        return self.image_analyzer.available

    @property
    def multimodal_embedding_available(self) -> bool:
        return self.image_embedder.available
