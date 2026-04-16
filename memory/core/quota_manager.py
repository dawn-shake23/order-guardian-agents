from models.sandbox_memory import AgentSandboxMemory

class SandboxQuota:
    # 单沙盒字段数配额校验
    @staticmethod
    def check_quota(sandbox: AgentSandboxMemory) -> bool:
        return len(sandbox.private_data)<= sandbox.quota_limit

    # 内存占用预警
    @staticmethod
    def check_memory_usage(data_size: int, max_size: int = 1024*1024) -> bool:
<= max_size