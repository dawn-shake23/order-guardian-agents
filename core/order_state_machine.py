from enum import Enum, auto
from typing import Dict, Any, Optional

class OrderState(Enum):
    """订单状态枚举"""
    CREATED = auto()        # 订单已创建
    PENDING_PAYMENT = auto() # 待支付
    PAID = auto()           # 已支付
    PROCESSING = auto()     # 处理中
    SHIPPED = auto()        # 已发货
    DELIVERED = auto()      # 已送达
    COMPLETED = auto()      # 已完成
    CANCELLED = auto()      # 已取消
    REFUNDED = auto()       # 已退款

class OrderEvent(Enum):
    """订单事件枚举"""
    PAY = auto()            # 支付
    PROCESS = auto()        # 开始处理
    SHIP = auto()           # 发货
    DELIVER = auto()        # 送达
    COMPLETE = auto()       # 完成
    CANCEL = auto()         # 取消
    REFUND = auto()         # 退款

class OrderStateMachine:
    """订单状态机"""
    def __init__(self):
        # 状态转移表
        self.transitions = {
            OrderState.CREATED: {
                OrderEvent.PAY: OrderState.PENDING_PAYMENT,
                OrderEvent.CANCEL: OrderState.CANCELLED
            },
            OrderState.PENDING_PAYMENT: {
                OrderEvent.PAY: OrderState.PAID,
                OrderEvent.CANCEL: OrderState.CANCELLED
            },
            OrderState.PAID: {
                OrderEvent.PROCESS: OrderState.PROCESSING,
                OrderEvent.CANCEL: OrderState.CANCELLED,
                OrderEvent.REFUND: OrderState.REFUNDED
            },
            OrderState.PROCESSING: {
                OrderEvent.SHIP: OrderState.SHIPPED,
                OrderEvent.CANCEL: OrderState.CANCELLED
            },
            OrderState.SHIPPED: {
                OrderEvent.DELIVER: OrderState.DELIVERED,
                OrderEvent.CANCEL: OrderState.CANCELLED
            },
            OrderState.DELIVERED: {
                OrderEvent.COMPLETE: OrderState.COMPLETED,
                OrderEvent.REFUND: OrderState.REFUNDED
            },
            OrderState.COMPLETED: {
                OrderEvent.REFUND: OrderState.REFUNDED
            }
        }
    
    def can_transition(self, current_state: OrderState, event: OrderEvent) -> bool:
        """
        检查是否可以从当前状态转换到下一状态
        """
        return current_state in self.transitions and event in self.transitions[current_state]
    
    def transition(self, current_state: OrderState, event: OrderEvent) -> Optional[OrderState]:
        """
        执行状态转换
        """
        if self.can_transition(current_state, event):
            return self.transitions[current_state][event]
        return None
    
    def get_available_events(self, current_state: OrderState) -> list:
        """
        获取当前状态下可用的事件
        """
        if current_state in self.transitions:
            return list(self.transitions[current_state].keys())
        return []
    
    def validate_order_state(self, order_data: Dict[str, Any]) -> bool:
        """
        验证订单状态是否有效
        """
        # 实际项目中应该实现更复杂的状态验证逻辑
        return True