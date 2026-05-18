"""
Session Context Manager — 多轮对话上下文管理
借鉴 Java RagChatSessionEntity + RagChatMessageEntity 的持久化设计
"""
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from core.logger import get_logger


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ChatMessage:
    """对话消息 — 借鉴 Java RagChatMessageEntity"""
    role: MessageRole
    content: str
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }

    def to_api_format(self) -> Dict[str, str]:
        """转为 LLM API 格式"""
        return {"role": self.role.value, "content": self.content}


@dataclass
class SessionContext:
    """
    会话上下文 — 借鉴 Java RagChatSessionEntity
    包含完整的多轮对话历史
    """
    session_id: str
    order_id: str = ""
    title: str = ""
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "active"  # active / completed / timeout
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def total_tokens(self) -> int:
        return sum(m.token_count for m in self.messages)

    def add_user_message(self, content: str) -> ChatMessage:
        msg = ChatMessage(role=MessageRole.USER, content=content,
                          token_count=self._estimate_tokens(content))
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg

    def add_assistant_message(self, content: str, metadata: Optional[Dict] = None) -> ChatMessage:
        msg = ChatMessage(role=MessageRole.ASSISTANT, content=content,
                          token_count=self._estimate_tokens(content),
                          metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg

    def get_history(self, max_messages: int = 10) -> List[Dict[str, str]]:
        """获取最近 N 条消息，用于 LLM 上下文注入"""
        recent = self.messages[-max_messages:]
        return [m.to_api_format() for m in recent]

    def get_history_for_rewrite(self, max_chars: int = 200) -> List[Dict[str, str]]:
        """获取用于查询改写的历史（截断过长的回复）"""
        result = []
        total = 0
        for msg in reversed(self.messages[-6:]):
            content = msg.content
            if len(content) > max_chars:
                content = content[:max_chars] + "..."
            result.append({"role": msg.role.value, "content": content})
            total += len(content)
            if total > max_chars * 3:
                break
        result.reverse()
        return result

    def trim(self, max_messages: int = 20, max_tokens: int = 8000):
        """裁剪历史消息，防止 token 溢出"""
        while len(self.messages) > max_messages or self.total_tokens > max_tokens:
            if len(self.messages) <= 2:
                break
            removed = self.messages.pop(0)
            self.logger.debug("裁剪历史消息", extra={
                "message_id": removed.message_id,
                "remaining": len(self.messages)
            })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "order_id": self.order_id,
            "title": self.title,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "messages": [m.to_dict() for m in self.messages],
            "status": self.status,
            "metadata": self.metadata,
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        import re
        chinese = len(re.findall(r'[一-鿿]', text))
        english = len(re.findall(r'[a-zA-Z0-9]+', text))
        return chinese + int(english * 1.3)


class SessionManager:
    """
    会话管理器
    借鉴 Java RagChatSessionService 的会话生命周期管理
    """

    def __init__(self, memory_hub=None, max_sessions: int = 100,
                 session_ttl_seconds: int = 3600):
        self.memory_hub = memory_hub
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl_seconds
        self._sessions: Dict[str, SessionContext] = {}
        self.logger = get_logger("session_manager")

    def create_session(self, order_id: str = "", title: str = "") -> SessionContext:
        """创建新会话"""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session = SessionContext(
            session_id=session_id,
            order_id=order_id,
            title=title or f"诊断_{order_id}"
        )
        self._sessions[session_id] = session
        self._evict_if_needed()
        self.logger.info("会话创建", extra={"session_id": session_id, "order_id": order_id})
        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """获取会话"""
        session = self._sessions.get(session_id)
        if session:
            if time.time() - session.updated_at > self.session_ttl:
                self.logger.info("会话已过期", extra={"session_id": session_id})
                self._sessions.pop(session_id, None)
                return None
        return session

    def add_message(self, session_id: str, role: MessageRole, content: str,
                    metadata: Optional[Dict] = None) -> Optional[ChatMessage]:
        """添加消息到会话"""
        session = self.get_session(session_id)
        if not session:
            return None

        if role == MessageRole.USER:
            msg = session.add_user_message(content)
        else:
            msg = session.add_assistant_message(content, metadata)

        session.trim()  # 自动裁剪过长的历史

        # 持久化到 memory_hub
        if self.memory_hub:
            self.memory_hub.struct_redis.set(
                f"session:{session_id}:history",
                session.to_dict(),
                expire=self.session_ttl
            )

        return msg

    def get_history(self, session_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
        """获取会话历史"""
        session = self.get_session(session_id)
        if not session:
            return []
        return session.get_history(max_messages)

    def complete_session(self, session_id: str):
        """标记会话完成"""
        session = self._sessions.get(session_id)
        if session:
            session.status = "completed"
            session.updated_at = time.time()

    def delete_session(self, session_id: str):
        """删除会话"""
        self._sessions.pop(session_id, None)
        if self.memory_hub:
            self.memory_hub.struct_redis.delete(f"session:{session_id}:history")

    def _evict_if_needed(self):
        """超过最大会话数时淘汰最旧的"""
        if len(self._sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].updated_at
            )
            for session_id, _ in sorted_sessions[:len(self._sessions) - self.max_sessions]:
                self._sessions.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.status == "active")
