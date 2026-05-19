"""
Embedding Provider — 文本向量化组件
支持多种后端：千问 DashScope API（默认）、sentence-transformers、确定性哈希
"""
import os
import hashlib
import re
import math
from typing import List, Optional

_DASHSCOPE_AVAILABLE = False
try:
    from openai import OpenAI
    _DASHSCOPE_AVAILABLE = True
except ImportError:
    pass

_HAS_SENTENCE_TRANSFORMERS = False
try:
    from sentence_transformers import SentenceTransformer
    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    pass


class DeterministicEmbedding:
    """
    确定性文本向量化（零依赖，回退方案）
    基于字符n-gram哈希 + TF-IDF加权，生成稳定的向量
    """

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = []
        chinese_chars = re.findall(r'[一-鿿]', text)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i + 1])
        words = re.findall(r'[a-z0-9]+', text)
        tokens.extend(words)
        clean = re.sub(r'\s+', '', text)
        for i in range(0, len(clean) - 2, 2):
            tokens.append(clean[i:i + 3])
        return tokens

    def encode(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        tf: dict = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        vec = [0.0] * self.dim
        for token, freq in tf.items():
            h = hashlib.md5(token.encode()).digest()
            for i in range(0, len(h) - 1, 2):
                idx = (h[i] * 256 + h[i + 1]) % self.dim
                vec[idx] += freq * (1.0 / math.sqrt(len(tokens)))
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.encode(t) for t in texts]


class DashScopeEmbedding:
    """
    千问 DashScope Embedding API
    借鉴 Java LlmProviderRegistry 中 DashScope 配置：
    - 模型: text-embedding-v3
    - 维度: 1024
    - 批量大小: 最大10条（API限制）
    - 通过 OpenAI 兼容接口调用
    """

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "text-embedding-v3"
    DEFAULT_DIM = 1024
    MAX_BATCH_SIZE = 10

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL
        self.dim = self.DEFAULT_DIM

        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 未设置")

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.DASHSCOPE_BASE_URL,
        )

    def encode(self, text: str) -> List[float]:
        result = self._client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.DEFAULT_DIM,
        )
        return result.data[0].embedding

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        all_embeddings = []
        # DashScope 批量限制，分批调用
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i:i + self.MAX_BATCH_SIZE]
            result = self._client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.DEFAULT_DIM,
            )
            all_embeddings.extend([d.embedding for d in result.data])
        return all_embeddings


class EmbeddingProvider:
    """
    统一Embedding入口
    优先级：千问 DashScope API > sentence-transformers > 确定性哈希
    """

    def __init__(self, model_name: Optional[str] = None, dim: int = 1024,
                 api_key: Optional[str] = None):
        self.dim = dim
        self._model = None
        self._backend = "deterministic"

        # 尝试千问 DashScope API
        effective_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        # 回退：从 .env 文件读取
        if not effective_key:
            _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(_env_path):
                with open(_env_path, "r", encoding="utf-8") as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line.startswith("DASHSCOPE_API_KEY="):
                            effective_key = _line.split("=", 1)[1].strip()
                            break
        if effective_key and _DASHSCOPE_AVAILABLE:
            try:
                self._model = DashScopeEmbedding(api_key=effective_key)
                self.dim = self._model.dim
                self._backend = "dashscope"
            except Exception:
                pass

        # 尝试 sentence-transformers
        if self._model is None and _HAS_SENTENCE_TRANSFORMERS and model_name:
            try:
                self._model = SentenceTransformer(model_name)
                self.dim = self._model.get_sentence_embedding_dimension()
                self._backend = "sentence-transformers"
            except Exception:
                self._model = None

        # 回退到确定性哈希
        if self._model is None:
            self._deterministic = DeterministicEmbedding(dim=dim)

    def encode(self, text: str) -> List[float]:
        if self._model is not None:
            return self._model.encode(text)
        return self._deterministic.encode(text)

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        if self._model is not None:
            return self._model.encode_batch(texts)
        return self._deterministic.encode_batch(texts)

    @property
    def backend(self) -> str:
        return self._backend
