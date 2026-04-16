# OrderGuardian-AI

基于多智能体协作（Multi-Agent）+ 深度检索（DeepSearch）的**双层订单异常治理系统**。

## 项目定位
- 前置：订单脏单拦截、规则校验
- 后置：差错池智能诊断（掉单、状态不一致、金额不匹配）
- 全程只读、不执行资金操作、可审计、可解释

## 技术亮点（面试向）
- 自研 MCP（Multi-Agent Cooperation Protocol）多智能体协作层
- 三级记忆体系：短期窗口 / 中期任务状态 / 长期案例向量库
- DeepSearch 深度检索：RAG 召回 + 多轮精读 + 交叉验证
- 配置驱动架构，参考 DeerFlow 2.0 设计思想
- 专家 SubAgent 并行调度：数据核对 / 深度检索 / 财务影响 / 风险评估
- 反思机制（Reflection）减少幻觉，提升决策可靠性

## 架构分层
1. Config 配置层
2. Domain 领域模型
3. Tool 原子工具
4. Skill 业务技能
5. Memory 记忆体系
6. MCP 智能体协作
7. Agent 专家团队
8. Flow 业务流程
9. VectorStore 向量存储
10. Runtime 运行时与多轮对话

1. Schema          统一结构规范
2. Model           LLM 模型调用（强模型/轻量模型）
3. Plan Agent      意图理解 + rewriting + 全局分析 + 步骤规划
4. Coordinator     任务调度、决策、汇总、流程编排
5. MCP             控制平面：权限、ACL、Prompt、上下文切片、Memory 访问策略
6. Memory          数据平面：缓存、会话记忆、步骤状态、持久化
7. Tools / Skill   原子能力 & 业务能力
8. Workers         轻量专家 Agent
9. Monitor         监控、超时、熔断、日志

## 开发状态
🔥 正在迭代建设中…