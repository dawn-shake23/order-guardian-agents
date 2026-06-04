"""
Mock 订单数据模型 & 全场景测试数据集

订单类型覆盖：
- normal:         正常订单
- dropped:        掉单（支付发起但未完成）
- lost:           丢单（订单存在但无支付记录）
- reconciliation: 渠道对账不符
- risk_suspicious: 财务风险可疑订单
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import random


# ============================================================
# 枚举定义
# ============================================================

class OrderState(str, Enum):
    CREATED = "created"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REFUNDED = "refunded"


class ChannelType(str, Enum):
    ALIPAY = "alipay"
    WECHAT = "wechat"
    UNIONPAY = "unionpay"
    BANK_TRANSFER = "bank_transfer"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    NORMAL = "normal"                          # 正常
    DROPPED_ORDER = "dropped_order"            # 掉单
    LOST_ORDER = "lost_order"                  # 丢单
    RECONCILIATION_MISMATCH = "recon_mismatch"  # 对账不符
    RISK_SUSPICIOUS = "risk_suspicious"         # 风控可疑


# ============================================================
# 订单数据模型 (Pydantic 强校验)
# ============================================================

class PaymentRecord(BaseModel):
    payment_id: str
    channel: ChannelType
    amount: float
    state: PaymentState
    channel_order_no: Optional[str] = None
    paid_at: Optional[str] = None
    callback_received: bool = False
    callback_at: Optional[str] = None
    raw_channel_response: Dict[str, Any] = Field(default_factory=dict)


class OrderInfo(BaseModel):
    order_id: str
    merchant_id: str
    user_id: str
    product_name: str
    order_amount: float
    currency: str = "CNY"
    state: OrderState
    created_at: str
    updated_at: Optional[str] = None
    ip_address: Optional[str] = None
    device_fingerprint: Optional[str] = None


class MockOrder(BaseModel):
    """完整的 Mock 订单模型，涵盖所有校验所需字段"""
    anomaly_type: AnomalyType
    description: str
    order: OrderInfo
    payments: List[PaymentRecord] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def total_paid(self) -> float:
        return sum(
            p.amount for p in self.payments
            if p.state == PaymentState.SUCCESS
        )

    @property
    def has_payment_record(self) -> bool:
        return len(self.payments) > 0

    @property
    def payment_channels(self) -> list:
        return [p.channel.value for p in self.payments]


# ============================================================
# Mock 数据集生成
# ============================================================

def _now() -> str:
    return datetime.now().isoformat()


def _ago(minutes: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------
# 1. 正常订单 (10 条)
# ---------------------------------------------------------------------------

NORMAL_ORDERS: List[MockOrder] = [
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="支付宝全额支付成功，已完成",
        order=OrderInfo(
            order_id="ORD-NORMAL-001", merchant_id="M1001", user_id="U20001",
            product_name="iPhone 15 Pro Max 256GB", order_amount=8999.00,
            currency="CNY", state=OrderState.COMPLETED,
            created_at=_ago(120), updated_at=_ago(30),
            ip_address="58.33.12.100", device_fingerprint="fp_a1b2c3d4",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N001", channel=ChannelType.ALIPAY, amount=8999.00,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101001",
                paid_at=_ago(118), callback_received=True, callback_at=_ago(118),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="微信全额支付成功，处理中",
        order=OrderInfo(
            order_id="ORD-NORMAL-002", merchant_id="M1001", user_id="U20002",
            product_name="MacBook Pro 14 M4", order_amount=14999.00,
            currency="CNY", state=OrderState.PROCESSING,
            created_at=_ago(60), updated_at=_ago(55),
            ip_address="114.88.45.12", device_fingerprint="fp_x9y8z7w6",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N002", channel=ChannelType.WECHAT, amount=14999.00,
                state=PaymentState.SUCCESS, channel_order_no="WX20260101001",
                paid_at=_ago(58), callback_received=True, callback_at=_ago(58),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="银行卡转账全额支付，已发货",
        order=OrderInfo(
            order_id="ORD-NORMAL-003", merchant_id="M1002", user_id="U20003",
            product_name="AirPods Pro 2", order_amount=1899.00,
            currency="CNY", state=OrderState.SHIPPED,
            created_at=_ago(180), updated_at=_ago(90),
            ip_address="220.181.38.251", device_fingerprint="fp_1q2w3e4r",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N003", channel=ChannelType.BANK_TRANSFER, amount=1899.00,
                state=PaymentState.SUCCESS, channel_order_no="BANK20260101001",
                paid_at=_ago(178), callback_received=True, callback_at=_ago(178),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="银联在线支付成功，已完成",
        order=OrderInfo(
            order_id="ORD-NORMAL-004", merchant_id="M1003", user_id="U20004",
            product_name="Sony WH-1000XM5", order_amount=2499.00,
            currency="CNY", state=OrderState.COMPLETED,
            created_at=_ago(300), updated_at=_ago(30),
            ip_address="101.226.168.228", device_fingerprint="fp_z9x8c7v6",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N004", channel=ChannelType.UNIONPAY, amount=2499.00,
                state=PaymentState.SUCCESS, channel_order_no="UP20260101001",
                paid_at=_ago(298), callback_received=True, callback_at=_ago(298),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="小额订单支付宝秒付，已完成",
        order=OrderInfo(
            order_id="ORD-NORMAL-005", merchant_id="M1001", user_id="U20005",
            product_name="USB-C 充电线 1m", order_amount=59.00,
            currency="CNY", state=OrderState.COMPLETED,
            created_at=_ago(45), updated_at=_ago(40),
            ip_address="58.33.12.100", device_fingerprint="fp_a1b2c3d4",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N005", channel=ChannelType.ALIPAY, amount=59.00,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101002",
                paid_at=_ago(44), callback_received=True, callback_at=_ago(44),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="微信支付，已发货，等待确认收货",
        order=OrderInfo(
            order_id="ORD-NORMAL-006", merchant_id="M1002", user_id="U20006",
            product_name="iPad Air M2 11寸", order_amount=4799.00,
            currency="CNY", state=OrderState.SHIPPED,
            created_at=_ago(200), updated_at=_ago(72),
            ip_address="117.136.12.89", device_fingerprint="fp_h5g4f3d2",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N006", channel=ChannelType.WECHAT, amount=4799.00,
                state=PaymentState.SUCCESS, channel_order_no="WX20260101002",
                paid_at=_ago(198), callback_received=True, callback_at=_ago(198),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="支付宝大额支付，已完成（企业采购）",
        order=OrderInfo(
            order_id="ORD-NORMAL-007", merchant_id="M1003", user_id="U20007",
            product_name="服务器机柜 42U", order_amount=45000.00,
            currency="CNY", state=OrderState.COMPLETED,
            created_at=_ago(480), updated_at=_ago(120),
            ip_address="202.96.209.133", device_fingerprint="fp_corp_xyz01",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N007", channel=ChannelType.BANK_TRANSFER, amount=45000.00,
                state=PaymentState.SUCCESS, channel_order_no="BANK20260101002",
                paid_at=_ago(478), callback_received=True, callback_at=_ago(478),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="银联支付，已创建待发货",
        order=OrderInfo(
            order_id="ORD-NORMAL-008", merchant_id="M1001", user_id="U20008",
            product_name="华为手表 GT5", order_amount=1588.00,
            currency="CNY", state=OrderState.PAID,
            created_at=_ago(35), updated_at=_ago(33),
            ip_address="123.139.56.100", device_fingerprint="fp_m8n7b6v5",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N008", channel=ChannelType.UNIONPAY, amount=1588.00,
                state=PaymentState.SUCCESS, channel_order_no="UP20260101002",
                paid_at=_ago(34), callback_received=True, callback_at=_ago(34),
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="支付宝花呗分期支付，已完成",
        order=OrderInfo(
            order_id="ORD-NORMAL-009", merchant_id="M1002", user_id="U20009",
            product_name="大疆无人机 Mini 4 Pro", order_amount=4788.00,
            currency="CNY", state=OrderState.COMPLETED,
            created_at=_ago(400), updated_at=_ago(200),
            ip_address="106.38.112.77", device_fingerprint="fp_dji_2026",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N009", channel=ChannelType.ALIPAY, amount=4788.00,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101003",
                paid_at=_ago(398), callback_received=True, callback_at=_ago(398),
                raw_channel_response={"installment": "12", "fee": "0"},
            )
        ],
    ),
    MockOrder(
        anomaly_type=AnomalyType.NORMAL,
        description="微信小程序支付，秒付秒回调",
        order=OrderInfo(
            order_id="ORD-NORMAL-010", merchant_id="M1003", user_id="U20010",
            product_name="美团外卖订单 #89757", order_amount=45.50,
            currency="CNY", state=OrderState.COMPLETED,
            created_at=_ago(15), updated_at=_ago(14),
            ip_address="223.104.3.228", device_fingerprint="fp_miniapp_01",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-N010", channel=ChannelType.WECHAT, amount=45.50,
                state=PaymentState.SUCCESS, channel_order_no="WX20260101003",
                paid_at=_ago(14), callback_received=True, callback_at=_ago(14),
            )
        ],
    ),
]


# ---------------------------------------------------------------------------
# 2. 掉单：支付发起但未完成 (5 条)
# ---------------------------------------------------------------------------

DROPPED_ORDERS: List[MockOrder] = [
    MockOrder(
        anomaly_type=AnomalyType.DROPPED_ORDER,
        description="支付宝支付超时，用户已扣款但未收到回调",
        order=OrderInfo(
            order_id="ORD-DROP-001", merchant_id="M1001", user_id="U30001",
            product_name="Sony PS5 Pro", order_amount=4999.00,
            state=OrderState.CREATED,
            created_at=_ago(90), updated_at=_ago(90),
            ip_address="58.33.12.100", device_fingerprint="fp_ps5pro001",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-D001", channel=ChannelType.ALIPAY, amount=4999.00,
                state=PaymentState.TIMEOUT, channel_order_no="ALI20260101004",
                paid_at=_ago(88), callback_received=False,
                raw_channel_response={"error": "timeout", "duration_ms": 30000},
            )
        ],
        metadata={"gap_minutes": 88, "expected_callback": True},
    ),
    MockOrder(
        anomaly_type=AnomalyType.DROPPED_ORDER,
        description="微信支付处理中超过30分钟，疑似掉单",
        order=OrderInfo(
            order_id="ORD-DROP-002", merchant_id="M1001", user_id="U30002",
            product_name="Nintendo Switch OLED", order_amount=2199.00,
            state=OrderState.CREATED,
            created_at=_ago(60), updated_at=_ago(60),
            ip_address="114.88.45.12", device_fingerprint="fp_ns_oled",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-D002", channel=ChannelType.WECHAT, amount=2199.00,
                state=PaymentState.PROCESSING, channel_order_no="WX20260101004",
                paid_at=None, callback_received=False,
            )
        ],
        metadata={"gap_minutes": 60, "expected_callback": False},
    ),
    MockOrder(
        anomaly_type=AnomalyType.DROPPED_ORDER,
        description="银联支付回调丢失，用户银行已扣款",
        order=OrderInfo(
            order_id="ORD-DROP-003", merchant_id="M1002", user_id="U30003",
            product_name="小米扫地机器人", order_amount=1299.00,
            state=OrderState.CREATED,
            created_at=_ago(120), updated_at=_ago(45),
            ip_address="123.139.56.100", device_fingerprint="fp_xiaomi_s",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-D003", channel=ChannelType.UNIONPAY, amount=1299.00,
                state=PaymentState.SUCCESS, channel_order_no="UP20260101003",
                paid_at=_ago(115), callback_received=False,
                raw_channel_response={"bank_msg": "交易成功"},
            )
        ],
        metadata={"gap_minutes": 115, "callback_missing": True, "bank_confirmed": True},
    ),
    MockOrder(
        anomaly_type=AnomalyType.DROPPED_ORDER,
        description="银行卡转账成功但异步通知未到达",
        order=OrderInfo(
            order_id="ORD-DROP-004", merchant_id="M1003", user_id="U30004",
            product_name="DELL 显示器 27寸 4K", order_amount=3299.00,
            state=OrderState.CREATED,
            created_at=_ago(240), updated_at=_ago(240),
            ip_address="202.96.209.133", device_fingerprint="fp_dell_4k",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-D004", channel=ChannelType.BANK_TRANSFER, amount=3299.00,
                state=PaymentState.SUCCESS, channel_order_no="BANK20260101003",
                paid_at=_ago(235), callback_received=False,
            )
        ],
        metadata={"gap_minutes": 235, "async_notify_failed": True},
    ),
    MockOrder(
        anomaly_type=AnomalyType.DROPPED_ORDER,
        description="支付宝支付失败但渠道未返回明确错误码",
        order=OrderInfo(
            order_id="ORD-DROP-005", merchant_id="M1001", user_id="U30005",
            product_name="Switch 游戏卡带", order_amount=299.00,
            state=OrderState.CREATED,
            created_at=_ago(25), updated_at=_ago(25),
            ip_address="58.33.12.100", device_fingerprint="fp_game001",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-D005", channel=ChannelType.ALIPAY, amount=299.00,
                state=PaymentState.FAILED, channel_order_no="ALI20260101005",
                paid_at=None, callback_received=False,
                raw_channel_response={"code": "UNKNOWN", "msg": "系统繁忙，请稍后重试"},
            )
        ],
        metadata={"gap_minutes": 25, "retry_suggested": True},
    ),
]


# ---------------------------------------------------------------------------
# 3. 丢单：订单存在但无任何支付记录 (5 条)
# ---------------------------------------------------------------------------

LOST_ORDERS: List[MockOrder] = [
    MockOrder(
        anomaly_type=AnomalyType.LOST_ORDER,
        description="用户已下单30分钟，无任何支付发起记录",
        order=OrderInfo(
            order_id="ORD-LOST-001", merchant_id="M1001", user_id="U40001",
            product_name="机械键盘 Cherry MX", order_amount=899.00,
            state=OrderState.CREATED,
            created_at=_ago(30), updated_at=_ago(30),
            ip_address="114.88.45.12", device_fingerprint="fp_kb_cherry",
        ),
        payments=[],
        metadata={"no_action_minutes": 30},
    ),
    MockOrder(
        anomaly_type=AnomalyType.LOST_ORDER,
        description="高价值订单无支付动作超过2小时",
        order=OrderInfo(
            order_id="ORD-LOST-002", merchant_id="M1002", user_id="U40002",
            product_name="RTX 5090 显卡", order_amount=12999.00,
            state=OrderState.CREATED,
            created_at=_ago(150), updated_at=_ago(150),
            ip_address="101.226.168.228", device_fingerprint="fp_rtx5090",
        ),
        payments=[],
        metadata={"no_action_minutes": 150, "high_value": True},
    ),
    MockOrder(
        anomaly_type=AnomalyType.LOST_ORDER,
        description="订单已取消但无任何操作记录",
        order=OrderInfo(
            order_id="ORD-LOST-003", merchant_id="M1003", user_id="U40003",
            product_name="Bose 降噪耳机 QC45", order_amount=2299.00,
            state=OrderState.CANCELLED,
            created_at=_ago(500), updated_at=_ago(490),
            ip_address="220.181.38.251", device_fingerprint="fp_bose_qc45",
        ),
        payments=[],
        metadata={"no_action_minutes": 500, "state": "cancelled"},
    ),
    MockOrder(
        anomaly_type=AnomalyType.LOST_ORDER,
        description="订单创建后用户跳失，购物车转订单但未进入支付页",
        order=OrderInfo(
            order_id="ORD-LOST-004", merchant_id="M1001", user_id="U40004",
            product_name="罗技鼠标 MX Master 3S", order_amount=699.00,
            state=OrderState.CREATED,
            created_at=_ago(45), updated_at=_ago(45),
            ip_address="117.136.12.89", device_fingerprint="fp_logi_mx3s",
        ),
        payments=[],
        metadata={"no_action_minutes": 45, "bounce_reason": "payment_page_exit"},
    ),
    MockOrder(
        anomaly_type=AnomalyType.LOST_ORDER,
        description="凌晨下单无支付（疑似测试/欺诈探测）",
        order=OrderInfo(
            order_id="ORD-LOST-005", merchant_id="M1002", user_id="U40005",
            product_name="iPhone 16 Pro Max 1TB", order_amount=13999.00,
            state=OrderState.CREATED,
            created_at=_ago(480), updated_at=_ago(480),
            ip_address="45.33.32.156", device_fingerprint="fp_suspect_vpn",
        ),
        payments=[],
        metadata={"no_action_minutes": 480, "suspicious_ip": True, "created_hour": "03:15"},
    ),
]


# ---------------------------------------------------------------------------
# 4. 渠道对账不符 (5 条)
# ---------------------------------------------------------------------------

RECONCILIATION_ORDERS: List[MockOrder] = [
    MockOrder(
        anomaly_type=AnomalyType.RECONCILIATION_MISMATCH,
        description="支付宝渠道金额比订单金额多0.01元",
        order=OrderInfo(
            order_id="ORD-RECON-001", merchant_id="M1001", user_id="U50001",
            product_name="Type-C Hub 转换器", order_amount=199.00,
            state=OrderState.PAID,
            created_at=_ago(80), updated_at=_ago(78),
            ip_address="58.33.12.100", device_fingerprint="fp_hub001",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-R001", channel=ChannelType.ALIPAY, amount=199.01,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101R01",
                paid_at=_ago(78), callback_received=True, callback_at=_ago(78),
            )
        ],
        metadata={"diff_amount": 0.01, "diff_pct": 0.005},
    ),
    MockOrder(
        anomaly_type=AnomalyType.RECONCILIATION_MISMATCH,
        description="微信渠道金额比订单金额少50元",
        order=OrderInfo(
            order_id="ORD-RECON-002", merchant_id="M1001", user_id="U50002",
            product_name="Apple Watch Ultra 2", order_amount=6499.00,
            state=OrderState.PAID,
            created_at=_ago(100), updated_at=_ago(97),
            ip_address="114.88.45.12", device_fingerprint="fp_watch_u2",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-R002", channel=ChannelType.WECHAT, amount=6449.00,
                state=PaymentState.SUCCESS, channel_order_no="WX20260101R02",
                paid_at=_ago(97), callback_received=True, callback_at=_ago(97),
            )
        ],
        metadata={"diff_amount": -50.00, "diff_pct": -0.0077, "possible_coupon": True},
    ),
    MockOrder(
        anomaly_type=AnomalyType.RECONCILIATION_MISMATCH,
        description="多渠道重复支付：支付宝+微信都成功扣款",
        order=OrderInfo(
            order_id="ORD-RECON-003", merchant_id="M1002", user_id="U50003",
            product_name="iPad Pro M4 12.9寸", order_amount=9299.00,
            state=OrderState.PAID,
            created_at=_ago(150), updated_at=_ago(145),
            ip_address="101.226.168.228", device_fingerprint="fp_ipad_pro",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-R003A", channel=ChannelType.ALIPAY, amount=9299.00,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101R03",
                paid_at=_ago(148), callback_received=True, callback_at=_ago(148),
            ),
            PaymentRecord(
                payment_id="PAY-R003B", channel=ChannelType.WECHAT, amount=9299.00,
                state=PaymentState.SUCCESS, channel_order_no="WX20260101R03",
                paid_at=_ago(146), callback_received=True, callback_at=_ago(146),
            ),
        ],
        metadata={"duplicate_payment": True, "overpaid_amount": 9299.00},
    ),
    MockOrder(
        anomaly_type=AnomalyType.RECONCILIATION_MISMATCH,
        description="银联回调成功但渠道金额为0（异常）",
        order=OrderInfo(
            order_id="ORD-RECON-004", merchant_id="M1003", user_id="U50004",
            product_name="三星 SSD 2TB", order_amount=899.00,
            state=OrderState.PAID,
            created_at=_ago(50), updated_at=_ago(48),
            ip_address="123.139.56.100", device_fingerprint="fp_ssd_2tb",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-R004", channel=ChannelType.UNIONPAY, amount=0.00,
                state=PaymentState.SUCCESS, channel_order_no="UP20260101R04",
                paid_at=_ago(48), callback_received=True, callback_at=_ago(48),
                raw_channel_response={"amount": "0", "msg": "交易成功"},
            )
        ],
        metadata={"zero_amount_anomaly": True},
    ),
    MockOrder(
        anomaly_type=AnomalyType.RECONCILIATION_MISMATCH,
        description="银行转账金额不符，渠道显示未足额到账",
        order=OrderInfo(
            order_id="ORD-RECON-005", merchant_id="M1002", user_id="U50005",
            product_name="企业级打印机", order_amount=8500.00,
            state=OrderState.PAID,
            created_at=_ago(200), updated_at=_ago(195),
            ip_address="202.96.209.133", device_fingerprint="fp_printer_ent",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-R005", channel=ChannelType.BANK_TRANSFER, amount=8000.00,
                state=PaymentState.SUCCESS, channel_order_no="BANK20260101R05",
                paid_at=_ago(195), callback_received=True, callback_at=_ago(195),
                raw_channel_response={"amount": "8000", "fee_deducted": "500"},
            )
        ],
        metadata={"diff_amount": -500.00, "diff_pct": -0.0588, "bank_fee_possible": True},
    ),
]


# ---------------------------------------------------------------------------
# 5. 财务风险可疑订单 (5 条)
# ---------------------------------------------------------------------------

RISK_ORDERS: List[MockOrder] = [
    MockOrder(
        anomaly_type=AnomalyType.RISK_SUSPICIOUS,
        description="同一IP 30分钟内创建5个大额订单",
        order=OrderInfo(
            order_id="ORD-RISK-001", merchant_id="M1001", user_id="U60001",
            product_name="MacBook Pro 16 M4 Max + AppleCare", order_amount=32999.00,
            state=OrderState.PAID,
            created_at=_ago(10), updated_at=_ago(8),
            ip_address="45.33.32.156", device_fingerprint="fp_bulk_risk_01",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-RISK001", channel=ChannelType.ALIPAY, amount=32999.00,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101F01",
                paid_at=_ago(8), callback_received=True, callback_at=_ago(8),
            )
        ],
        metadata={
            "bulk_order_count_30min": 5, "total_amount_30min": 165000.00,
            "same_ip": True, "new_account_days": 1,
        },
    ),
    MockOrder(
        anomaly_type=AnomalyType.RISK_SUSPICIOUS,
        description="设备和用户不匹配，疑似盗刷",
        order=OrderInfo(
            order_id="ORD-RISK-002", merchant_id="M1002", user_id="U60002",
            product_name="金条 100g", order_amount=58000.00,
            state=OrderState.PAID,
            created_at=_ago(15), updated_at=_ago(13),
            ip_address="98.158.101.23", device_fingerprint="fp_device_new_unknown",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-RISK002", channel=ChannelType.BANK_TRANSFER, amount=58000.00,
                state=PaymentState.SUCCESS, channel_order_no="BANK20260101F02",
                paid_at=_ago(13), callback_received=True, callback_at=_ago(13),
            )
        ],
        metadata={
            "device_change_count_7d": 3, "ip_geo_mismatch": True,
            "first_large_order": True, "user_usual_amount": 200.00,
        },
    ),
    MockOrder(
        anomaly_type=AnomalyType.RISK_SUSPICIOUS,
        description="凌晨大额支付 + 海外IP + 新设备",
        order=OrderInfo(
            order_id="ORD-RISK-003", merchant_id="M1003", user_id="U60003",
            product_name="劳力士潜航者 126610LN", order_amount=86000.00,
            state=OrderState.PAID,
            created_at=_ago(240), updated_at=_ago(238),
            ip_address="103.235.46.92",
            device_fingerprint="fp_new_unknown_os",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-RISK003", channel=ChannelType.ALIPAY, amount=86000.00,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101F03",
                paid_at=_ago(238), callback_received=True, callback_at=_ago(238),
            )
        ],
        metadata={
            "created_hour": "02:30", "overseas_ip": True,
            "amount_anomaly_score": 0.95, "new_device": True,
        },
    ),
    MockOrder(
        anomaly_type=AnomalyType.RISK_SUSPICIOUS,
        description="短时高频退款记录关联新订单",
        order=OrderInfo(
            order_id="ORD-RISK-004", merchant_id="M1001", user_id="U60004",
            product_name="华为 MateBook X Pro", order_amount=11999.00,
            state=OrderState.PAID,
            created_at=_ago(20), updated_at=_ago(18),
            ip_address="58.33.12.100", device_fingerprint="fp_refund_abuser",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-RISK004", channel=ChannelType.WECHAT, amount=11999.00,
                state=PaymentState.SUCCESS, channel_order_no="WX20260101F04",
                paid_at=_ago(18), callback_received=True, callback_at=_ago(18),
            )
        ],
        metadata={
            "refund_count_30d": 12, "refund_amount_30d": 85000.00,
            "refund_rate": 0.75, "abnormal_pattern": True,
        },
    ),
    MockOrder(
        anomaly_type=AnomalyType.RISK_SUSPICIOUS,
        description="支付金额和商品价格严重不匹配（0.01元测试）",
        order=OrderInfo(
            order_id="ORD-RISK-005", merchant_id="M1002", user_id="U60005",
            product_name="外星人游戏本 m18", order_amount=29999.00,
            state=OrderState.PAID,
            created_at=_ago(5), updated_at=_ago(4),
            ip_address="103.235.46.92", device_fingerprint="fp_tester_001",
        ),
        payments=[
            PaymentRecord(
                payment_id="PAY-RISK005", channel=ChannelType.ALIPAY, amount=0.01,
                state=PaymentState.SUCCESS, channel_order_no="ALI20260101F05",
                paid_at=_ago(4), callback_received=True, callback_at=_ago(4),
            )
        ],
        metadata={
            "price_amount_ratio": 0.0000003, "test_amount_suspicious": True,
        },
    ),
]


# ============================================================
# 聚合数据集
# ============================================================

ALL_MOCK_ORDERS: List[MockOrder] = (
    NORMAL_ORDERS
    + DROPPED_ORDERS
    + LOST_ORDERS
    + RECONCILIATION_ORDERS
    + RISK_ORDERS
)

DATASET_BY_TYPE: Dict[str, List[MockOrder]] = {
    "normal": NORMAL_ORDERS,
    "dropped": DROPPED_ORDERS,
    "lost": LOST_ORDERS,
    "reconciliation": RECONCILIATION_ORDERS,
    "risk_suspicious": RISK_ORDERS,
}


def get_dataset_summary() -> Dict[str, int]:
    """获取数据集概览"""
    return {k: len(v) for k, v in DATASET_BY_TYPE.items()}


def get_orders_by_type(anomaly_type: AnomalyType) -> List[MockOrder]:
    """按异常类型获取订单列表"""
    return [o for o in ALL_MOCK_ORDERS if o.anomaly_type == anomaly_type]


def sample_order(anomaly_type: Optional[AnomalyType] = None) -> MockOrder:
    """随机采样一个订单"""
    if anomaly_type:
        pool = get_orders_by_type(anomaly_type)
    else:
        pool = ALL_MOCK_ORDERS
    return random.choice(pool)
