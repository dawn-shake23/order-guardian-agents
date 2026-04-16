from typing import Optional
from models.struct_memory import SessionMemory

class MySQLMemoryRepo:
    def save_session(self, session: SessionMemory) -> None:
        # 持久化到 MySQL
        pass

    def load_session(self, session_id: str) -> Optional[SessionMemory]:
        return None