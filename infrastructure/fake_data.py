import time
import random
from typing import Dict, Any, Optional, List
from infrastructure.mock_infra import MockDB, MockRedis, MockRAG


FAKE_ORDERS = {
    "ORD00001": {
        "order_id": "ORD00001", "user_id": "U100001", "amount": 299.00,
        "channel": "alipay", "status": "pending_payment", "create_time": "2026-04-19 10:00:00",
        "currency": "CNY", "merchant_id": "M2001", "product_desc": "会员订阅"
    },
    "ORD00002": {
        "order_id": "ORD00002", "user_id": "U100002", "amount": 1580.00,
        "channel": "wechat", "status": "paid", "create_time": "2026-04-19 09:30:00",
        "currency": "CNY", "merchant_id": "M2002", "product_desc": "企业套餐"
    },
    "ORD00003": {
        "order_id": "ORD00003", "user_id": "U100003", "amount": 0.01,
        "channel": "unionpay", "status": "timeout", "create_time": "2026-04-19 08:00:00",
        "currency": "CNY", "merchant_id": "M2001", "product_desc": "测试订单"
    },
}

FAKE_PAYMENTS = {
    "PAY00001": {
        "payment_id": "PAY00001", "order_id": "ORD00001", "amount": 299.00,
        "channel": "alipay", "status": "timeout", "error_code": "E2001",
        "msg": "支付超时，回调未到达", "pay_time": "2026-04-19 10:01:00",
        "callback_time": None
    },
    "PAY00002": {
        "payment_id": "PAY00002", "order_id": "ORD00002", "amount": 1580.00,
        "channel": "wechat", "status": "success", "error_code": None,
        "msg": "支付成功", "pay_time": "2026-04-19 09:31:00",
        "callback_time": "2026-04-19 09:31:05"
    },
    "PAY00003": {
        "payment_id": "PAY00003", "order_id": "ORD00003", "amount": 0.01,
        "channel": "unionpay", "status": "failed", "error_code": "E2002",
        "msg": "余额不足", "pay_time": "2026-04-19 08:01:00",
        "callback_time": "2026-04-19 08:01:02"
    },
    "PAY00004": {
        "payment_id": "PAY00004", "order_id": "ORD00001", "amount": 299.00,
        "channel": "alipay", "status": "reversed", "error_code": "E2004",
        "msg": "支付已退回", "pay_time": "2026-04-19 10:05:00",
        "callback_time": "2026-04-19 10:05:03"
    },
}

FAKE_RISKS = {
    "RISK_ORD00001": {
        "order_id": "ORD00001", "risk_level": "medium", "rule_id": "R001",
        "reason": "同一用户短时间多次支付", "score": 65, "hit_rules": ["R001", "R003"]
    },
    "RISK_ORD00002": {
        "order_id": "ORD00002", "risk_level": "low", "rule_id": None,
        "reason": "正常交易", "score": 15, "hit_rules": []
    },
    "RISK_ORD00003": {
        "order_id": "ORD00003", "risk_level": "high", "rule_id": "R005",
        "reason": "黑名单用户", "score": 95, "hit_rules": ["R005", "R007"]
    },
}

FAKE_RECONCILIATIONS = {
    "RECON_ORD00001": {
        "order_id": "ORD00001", "order_amount": 299.00, "payment_amount": 299.00,
        "diff_amount": 0.00, "diff_type": "none", "status": "mismatch_status",
        "order_status": "pending_payment", "payment_status": "timeout"
    },
    "RECON_ORD00002": {
        "order_id": "ORD00002", "order_amount": 1580.00, "payment_amount": 1580.00,
        "diff_amount": 0.00, "diff_type": "none", "status": "match",
        "order_status": "paid", "payment_status": "success"
    },
    "RECON_ORD00003": {
        "order_id": "ORD00003", "order_amount": 0.01, "payment_amount": 0.01,
        "diff_amount": 0.00, "diff_type": "none", "status": "match",
        "order_status": "timeout", "payment_status": "failed"
    },
}

KNOWLEDGE_BASE = [
    {"doc_id": "KB001", "title": "E2001支付超时处理规则", "content": "当支付超时(E2001)时：1.查询渠道确认支付状态；2.若渠道已扣款，手动补单；3.若未扣款，关闭订单并通知用户；4.超时阈值：支付宝30分钟，微信15分钟", "biz_domain": "payment", "doc_type": "rule"},
    {"doc_id": "KB002", "title": "E2002余额不足处理流程", "content": "当余额不足(E2002)时：1.标记支付失败；2.通知用户更换支付方式；3.保留订单24小时等待重新支付；4.超时自动关闭", "biz_domain": "payment", "doc_type": "process"},
    {"doc_id": "KB003", "title": "E2003渠道异常应急SOP", "content": "当渠道异常(E2003)时：1.立即切换备用渠道；2.记录异常日志并上报；3.触发渠道健康检查；4.连续3次异常触发熔断", "biz_domain": "payment", "doc_type": "process"},
    {"doc_id": "KB004", "title": "E3001风控拦截处理规范", "content": "当风控拦截(E3001)时：1.冻结订单；2.人工审核；3.审核通过后放行；4.审核拒绝则退款；5.高风险订单需主管审批", "biz_domain": "risk", "doc_type": "rule"},
    {"doc_id": "KB005", "title": "对账不一致处理流程", "content": "当对账不一致(E3004/E3005)时：1.标记差异记录；2.自动重试对账3次；3.仍不一致则人工介入；4.金额差异>1元需财务确认", "biz_domain": "reconciliation", "doc_type": "process"},
    {"doc_id": "KB006", "title": "运营SOP-订单异常处理", "content": "运营处理订单异常标准流程：1.确认异常类型；2.查询关联数据；3.按错误码匹配处理规则；4.执行处理方案；5.记录处理结果；6.必要时升级审批", "biz_domain": "operation", "doc_type": "sop"},
    {"doc_id": "KB007", "title": "E2005支付回调丢失处理", "content": "当支付回调丢失(E2005)时：1.主动查询渠道支付结果；2.若渠道已成功，补发回调更新状态；3.若渠道未成功，标记支付失败；4.设置回调超时监控", "biz_domain": "payment", "doc_type": "rule"},
    {"doc_id": "KB008", "title": "风控策略-黑名单规则", "content": "黑名单规则(E3002)：1.用户黑名单-直接拒绝；2.设备黑名单-标记可疑；3.IP黑名单-限流+验证；4.黑名单每24小时更新一次", "biz_domain": "risk", "doc_type": "policy"},
    {"doc_id": "KB009", "title": "订单超时自动关闭规则", "content": "订单超时(E1004)处理：1.普通订单30分钟未支付自动关闭；2.大额订单(>5000元)60分钟；3.预售订单支持延长至24小时；4.关闭后释放库存", "biz_domain": "order", "doc_type": "rule"},
    {"doc_id": "KB010", "title": "支付退回处理流程", "content": "支付退回(E2004)处理：1.确认退回原因；2.更新订单状态为待支付；3.通知用户重新支付；4.记录退回日志；5.若用户30分钟内未重新支付，关闭订单", "biz_domain": "payment", "doc_type": "process"},
]

EXPERT_CASES = [
    {"case_id": "CASE001", "title": "支付宝掉单-回调延迟", "problem": "用户已付款但订单状态仍为待支付", "root_cause": "支付宝回调延迟，系统未收到支付成功通知", "solution": "1.主动查询支付宝交易状态；2.确认已扣款后手动补单；3.增加回调超时补偿机制", "biz_domain": "payment", "similarity": 0.92},
    {"case_id": "CASE002", "title": "微信支付余额不足", "problem": "用户微信余额不足导致支付失败", "root_cause": "用户微信零钱和绑卡余额均不足", "solution": "1.提示用户更换支付方式；2.保留订单24小时；3.推送充值提醒", "biz_domain": "payment", "similarity": 0.75},
    {"case_id": "CASE003", "title": "风控拦截-高频交易", "problem": "正常用户被风控系统拦截", "root_cause": "用户短时间发起多次支付触发频率规则", "solution": "1.人工审核确认是否本人操作；2.通过后放行并加入白名单；3.调整频率规则阈值", "biz_domain": "risk", "similarity": 0.68},
    {"case_id": "CASE004", "title": "对账差异-金额不一致", "problem": "订单金额与实际支付金额不一致", "root_cause": "优惠券抵扣未同步到支付系统", "solution": "1.核实优惠券使用记录；2.修正金额差异；3.增加优惠券同步校验", "biz_domain": "reconciliation", "similarity": 0.55},
]


def init_mock_data(db: MockDB, rag: MockRAG):
    for pk, order in FAKE_ORDERS.items():
        db.insert("orders", pk, order)
    for pk, payment in FAKE_PAYMENTS.items():
        db.insert("payments", pk, payment)
    for pk, risk in FAKE_RISKS.items():
        db.insert("risks", pk, risk)
    for pk, recon in FAKE_RECONCILIATIONS.items():
        db.insert("reconciliations", pk, recon)
    for doc in KNOWLEDGE_BASE:
        rag.add_document(doc["doc_id"], doc["title"], doc["content"], doc["biz_domain"], doc["doc_type"])
    for case in EXPERT_CASES:
        rag.add_document(case["case_id"], case["title"], json.dumps(case, ensure_ascii=False), case["biz_domain"], "case")


import json
