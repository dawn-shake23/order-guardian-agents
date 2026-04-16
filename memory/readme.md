Memory/
├── __init__.py
├── core/                  # 内存核心
│   ├── session_memory.py    # 会话级记忆（全局）
│   ├── step_memory.py       # 步骤级临时记忆
│   ├── context_memory.py    # 上下文切片存储
│   └── global_state.py      # 任务全局状态
├── cache/                 # 缓存层
├── storage/               # 持久化（可选）
└── base_memory.py         # 统一记忆接口