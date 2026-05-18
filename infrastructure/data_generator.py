"""
批量数据生成器 — 生成1000条测试数据
800条业务数据（订单/支付/风控/对账）+ 200条知识库文档
"""
import random
import json
import os
import time
from typing import Dict, Any, List

random.seed(42)

# ============================================================
# 配置
# ============================================================

ORDER_COUNT = 250
PAYMENT_COUNT = 250
RISK_COUNT = 150
RECON_COUNT = 150
KB_COUNT = 200

CHANNELS = ["alipay", "wechat", "unionpay", "bank_transfer", "jd_pay", "meituan_pay"]
STATUSES = ["pending_payment", "paid", "timeout", "cancelled", "refunded", "partial_refund"]
PAY_STATUSES = ["success", "timeout", "failed", "reversed", "pending", "processing"]
RISK_LEVELS = ["low", "medium", "high", "critical"]
DIFF_TYPES = ["none", "amount_diff", "status_diff", "missing", "duplicate"]
MERCHANTS = ["M2001", "M2002", "M2003", "M2004", "M2005"]

ERROR_CODES = {
    "order": ["E1001", "E1002", "E1003", "E1004", "E1005", "E1006", "E1007", "E1008", "E1009", "E1010"],
    "payment": ["E2001", "E2002", "E2003", "E2004", "E2005", "E2006", "E2007", "E2008", "E2009", "E2010",
                "E2011", "E2012", "E2013", "E2014", "E2015"],
    "risk": ["E3001", "E3002", "E3003", "E3004", "E3005", "E3006", "E3007", "E3008", "E3009", "E3010"],
}

RISK_RULES = [
    "R001:高频交易", "R002:异地登录", "R003:设备变更", "R004:金额异常",
    "R005:黑名单用户", "R006:IP异常", "R007:关联账户风险", "R008:退款频繁",
    "R009:凌晨交易", "R010:大额交易", "R011:新设备", "R012:代理IP",
]


def generate_orders(n: int) -> List[Dict]:
    orders = {}
    for i in range(1, n + 1):
        order_id = f"ORD{i:05d}"
        status = random.choices(
            STATUSES, weights=[25, 35, 15, 10, 10, 5], k=1
        )[0]
        amount = round(random.uniform(0.01, 9999.99), 2)
        orders[order_id] = {
            "order_id": order_id,
            "user_id": f"U{random.randint(100000, 999999)}",
            "amount": amount,
            "channel": random.choice(CHANNELS),
            "status": status,
            "create_time": f"2026-{random.randint(1,5):02d}-{random.randint(1,28):02d} {random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}",
            "currency": random.choice(["CNY", "USD", "EUR", "HKD"]),
            "merchant_id": random.choice(MERCHANTS),
            "product_desc": random.choice([
                "会员订阅", "企业套餐", "测试商品", "电子产品", "服装鞋帽",
                "食品饮料", "家居用品", "图书音像", "美妆护肤", "运动户外"
            ]),
        }
    return orders


def generate_payments(n: int, order_ids: List[str]) -> List[Dict]:
    payments = {}
    for i in range(1, n + 1):
        payment_id = f"PAY{i:05d}"
        order_id = order_ids[(i - 1) % len(order_ids)]
        status = random.choices(
            PAY_STATUSES, weights=[40, 15, 15, 10, 10, 10], k=1
        )[0]
        error_code = None
        if status in ("timeout", "failed", "reversed"):
            error_code = random.choice(ERROR_CODES["payment"])

        pay_time = f"2026-{random.randint(1,5):02d}-{random.randint(1,28):02d} {random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
        callback_time = None
        if status in ("success", "reversed"):
            h, m, s = int(pay_time[11:13]), int(pay_time[14:16]), int(pay_time[17:19])
            s += random.randint(1, 30)
            callback_time = f"{pay_time[:17]}{s:02d}"

        payments[payment_id] = {
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": round(random.uniform(0.01, 9999.99), 2),
            "channel": random.choice(CHANNELS),
            "status": status,
            "error_code": error_code,
            "msg": _error_msg(error_code) if error_code else ("支付成功" if status == "success" else "处理中"),
            "pay_time": pay_time,
            "callback_time": callback_time,
            "transaction_id": f"TXN{random.randint(100000000, 999999999)}",
        }
    return payments


def generate_risks(n: int, order_ids: List[str]) -> List[Dict]:
    risks = {}
    for i in range(1, n + 1):
        order_id = order_ids[(i - 1) % len(order_ids)]
        level = random.choices(RISK_LEVELS, weights=[45, 25, 20, 10], k=1)[0]
        score = {"low": random.randint(0, 30), "medium": random.randint(31, 69),
                 "high": random.randint(70, 89), "critical": random.randint(90, 100)}[level]
        hit_rules = random.sample(RISK_RULES, random.randint(0, min(4, score // 20)))
        risks[f"RISK_{order_id}"] = {
            "order_id": order_id,
            "risk_level": level,
            "rule_id": hit_rules[0].split(":")[0] if hit_rules else None,
            "reason": random.choice([
                "正常交易", "同一用户短时间多次支付", "金额超阈值",
                "黑名单用户", "新设备首次交易", "异地登录后交易",
                "凌晨高风险时段", "关联账户异常", "IP地址异常",
                "退款率过高", "代理IP检测", "设备指纹异常"
            ]),
            "score": score,
            "hit_rules": [r.split(":")[0] for r in hit_rules],
        }
    return risks


def generate_reconciliations(n: int, order_ids: List[str]) -> List[Dict]:
    recons = {}
    for i in range(1, n + 1):
        order_id = order_ids[(i - 1) % len(order_ids)]
        diff_type = random.choices(DIFF_TYPES, weights=[60, 15, 15, 5, 5], k=1)[0]
        order_amount = round(random.uniform(0.01, 9999.99), 2)
        if diff_type == "amount_diff":
            payment_amount = round(order_amount + random.uniform(-10, 10), 2)
        else:
            payment_amount = order_amount

        status = "match" if diff_type == "none" else f"mismatch_{diff_type}"
        recons[f"RECON_{order_id}"] = {
            "order_id": order_id,
            "order_amount": order_amount,
            "payment_amount": payment_amount,
            "diff_amount": round(abs(order_amount - payment_amount), 2),
            "diff_type": diff_type,
            "status": status,
            "order_status": random.choice(STATUSES),
            "payment_status": random.choice(PAY_STATUSES),
            "reconcile_batch": f"BATCH{random.randint(1,30):03d}",
        }
    return recons


def generate_knowledge_base(n: int) -> List[Dict]:
    templates = [
        # 订单域规则
        ("E1001:订单不存在处理规则", "order", "rule",
         "当订单不存在(E1001)时：1.核实order_id是否正确；2.检查是否跨系统查询；3.确认订单是否被归档删除"),
        ("E1002:订单状态异常处理", "order", "rule",
         "当订单状态异常(E1002)时：1.回溯状态变更日志；2.检查状态机流转是否合规；3.必要时人工修正状态"),
        ("E1003:订单金额不一致处理", "order", "rule",
         "当订单金额不一致(E1003)时：1.核对优惠券/折扣计算；2.检查运费/税费；3.比对支付金额，差异>1元需人工确认"),
        ("E1004:订单超时自动关闭规则", "order", "rule",
         "订单超时(E1004)：普通订单30分钟未支付自动关闭；大额订单(>5000元)60分钟；预售订单支持延长至24小时"),
        ("E1005:重复订单检测规则", "order", "rule",
         "当疑似重复订单(E1005)时：1.比对用户+金额+时间窗口(5分钟)；2.若完全匹配则标记为重复；3.通知用户确认"),
        ("E1006:订单渠道异常", "order", "rule",
         "当渠道异常(E1006)时：1.检查渠道可用性；2.切换备用渠道；3.记录异常日志并通知运维"),
        ("E1007:库存不足处理", "order", "rule",
         "库存不足(E1007)时：1.通知用户；2.自动退单；3.记录缺货商品；4.触发补货提醒"),
        ("E1008:用户信息校验失败", "order", "rule",
         "用户信息校验失败(E1008)时：1.核实收货地址完整性；2.检查手机号格式；3.要求用户补充信息"),

        # 支付域规则
        ("E2001:支付超时处理规则", "payment", "rule",
         "支付超时(E2001)时：1.查询渠道确认支付状态；2.若已扣款则手动补单；3.若未扣款则关闭订单并通知用户；4.支付宝超时30分钟，微信超时15分钟"),
        ("E2002:余额不足处理流程", "payment", "process",
         "余额不足(E2002)时：1.标记支付失败；2.通知用户更换支付方式；3.保留订单24小时等待重新支付；4.超时自动关闭"),
        ("E2003:渠道异常应急SOP", "payment", "process",
         "渠道异常(E2003)时：1.立即切换备用渠道；2.记录异常日志并上报；3.触发渠道健康检查；4.连续3次异常触发熔断"),
        ("E2004:支付已退回处理", "payment", "rule",
         "支付退回(E2004)时：1.确认退回原因；2.更新订单状态为待支付；3.通知用户重新支付；4.30分钟内未支付则关闭订单"),
        ("E2005:支付回调丢失处理", "payment", "rule",
         "回调丢失(E2005)时：1.主动查询渠道支付结果；2.若已成功则补发回调更新状态；3.若未成功则标记支付失败；4.设置回调超时监控"),
        ("E2006:支付金额不匹配", "payment", "rule",
         "支付金额不匹配(E2006)时：1.核对订单金额与实际扣款金额；2.差异<0.01元忽略；3.差异>0.01元触发退款或补款流程"),
        ("E2007:重复支付检测", "payment", "rule",
         "重复支付(E2007)时：1.核实是否为同一笔订单多次扣款；2.确认后自动退款多余部分；3.记录重复支付日志"),
        ("E2008:支付渠道限流", "payment", "rule",
         "渠道限流(E2008)时：1.自动切换备用渠道；2.排队等待重试；3.最多重试3次；4.通知用户支付延迟"),
        ("E2009:银行卡信息校验失败", "payment", "rule",
         "银行卡校验失败(E2009)时：1.提示用户核实卡号；2.检查卡类型是否支持；3.建议更换银行卡"),
        ("E2010:跨境支付汇率异常", "payment", "rule",
         "汇率异常(E2010)时：1.查询实时汇率；2.若偏差>5%则暂停交易；3.通知用户汇率波动；4.人工审核后放行"),
        ("E2011:分期付款异常", "payment", "process",
         "分期异常(E2011)时：1.检查分期期数是否合法；2.核实每期金额；3.检查手续费计算；4.异常则取消分期改用全额支付"),
        ("E2012:企业支付审批超时", "payment", "process",
         "企业审批超时(E2012)时：1.自动提醒审批人；2.超过48小时自动驳回；3.通知用户重新发起支付"),
        ("E2013:代付订单异常", "payment", "rule",
         "代付异常(E2013)时：1.核实代付人身份；2.检查代付限额；3.超过限额需分笔支付"),
        ("E2014:支付风控拦截", "payment", "rule",
         "支付风控拦截(E2014)时：1.暂停支付流程；2.触发风控审核；3.审核通过后放行；4.拒绝则通知用户"),
        ("E2015:支付证书过期", "payment", "rule",
         "证书过期(E2015)时：1.暂停所有支付；2.紧急更新证书；3.通知运维处理；4.切换备用证书"),

        # 风控域规则
        ("E3001:风控拦截-高风险处理规范", "risk", "rule",
         "高风险拦截(E3001)时：1.冻结订单；2.人工审核；3.审核通过后放行；4.审核拒绝则退款；5.高额订单需主管审批"),
        ("E3002:风控策略-黑名单规则", "risk", "policy",
         "黑名单规则(E3002)：1.用户黑名单-直接拒绝；2.设备黑名单-标记可疑；3.IP黑名单-限流+验证；4.黑名单每24小时更新"),
        ("E3003:风控评分异常处理", "risk", "rule",
         "评分异常(E3003)时：1.检查评分模型是否更新；2.核实特征数据源；3.若模型异常则回退到规则模式"),
        ("E3004:高频交易风控", "risk", "rule",
         "高频交易(E3004)：同一用户1分钟内>3笔交易触发风控；5分钟内>10笔直接冻结；需人工审核解冻"),
        ("E3005:关联账户风险", "risk", "policy",
         "关联账户风险(E3005)：1.检测同设备多账号；2.检测同IP多账号；3.检测资金归集行为；4.关联度>80%则冻结所有关联账户"),
        ("E3006:设备指纹异常", "risk", "rule",
         "设备指纹异常(E3006)时：1.检测模拟器/越狱/Root；2.检测设备信息篡改；3.标记可疑设备；4.可疑设备交易需二次验证"),
        ("E3007:地理位置异常", "risk", "rule",
         "位置异常(E3007)时：1.比对常用登录地；2.短时间内跨省/跨国交易触发预警；3.需要短信验证码确认"),
        ("E3008:交易时间异常", "risk", "policy",
         "时间异常(E3008)：凌晨2:00-5:00的大额交易(>1000元)自动标记可疑；需人工审核后放行"),
        ("E3009:退款欺诈检测", "risk", "rule",
         "退款欺诈(E3009)时：1.检测退款频率(>5次/天)；2.检测退款金额模式；3.检测物流异常；4.命中2项则冻结退款"),
        ("E3010:账户接管检测", "risk", "policy",
         "账户接管(E3010)：1.检测密码修改后立即大额交易；2.检测新设备+异地登录+交易；3.命中则冻结并要求人脸验证"),

        # 对账域规则
        ("E4001:对账差异-金额不一致处理", "reconciliation", "rule",
         "金额差异(E4001)时：1.比对订单金额与支付金额；2.检查优惠券/折扣/税费；3.差异>1元需财务确认；4.<1元自动调账"),
        ("E4002:对账差异-状态不一致", "reconciliation", "process",
         "状态不一致(E4002)时：1.对比订单状态与支付状态；2.以支付渠道状态为准；3.手动修正订单状态；4.记录修正日志"),
        ("E4003:对账差异-缺失记录", "reconciliation", "rule",
         "缺失记录(E4003)：支付渠道有记录但订单系统无对应订单时：1.查询全库确认；2.检查数据同步延迟；3.补建订单记录"),
        ("E4004:对账批次异常", "reconciliation", "process",
         "批次异常(E4004)时：1.暂停当前批次对账；2.回滚已处理记录；3.修复数据源后重新对账"),
        ("E4005:对账数据源超时", "reconciliation", "rule",
         "数据源超时(E4005)时：1.切换备用数据源；2.延长超时时间；3.分批拉取数据；4.超过3次超时告警"),
        ("E4006:重复对账记录", "reconciliation", "rule",
         "重复记录(E4006)时：1.按transaction_id去重；2.保留最新记录；3.标记重复记录为无效"),
        ("E4007:跨日对账处理", "reconciliation", "process",
         "跨日对账(E4007)：涉及23:50-00:10的交易需跨日对账；延迟交易的结算时间以渠道为准"),

        # 运营SOP
        ("运营SOP-订单异常处理标准流程", "operation", "sop",
         "运营处理订单异常标准流程：1.确认异常类型与错误码；2.查询关联订单/支付/风控数据；3.按错误码匹配处理规则；4.执行处理方案；5.记录处理结果；6.必要时升级审批"),
        ("运营SOP-批量退款处理", "operation", "sop",
         "批量退款处理流程：1.确认退款原因(系统故障/商品问题/用户投诉)；2.导出退款清单；3.逐笔审核退款金额；4.财务确认后批量执行；5.短信通知用户"),
        ("运营SOP-投诉处理手册", "operation", "sop",
         "用户投诉处理手册：1.分类(支付/商品/物流/服务)；2.2小时内首次响应；3.24小时内给出处理方案；4.72小时内闭环；5.满意度回访"),
        ("运营SOP-系统故障应急预案", "operation", "sop",
         "系统故障应急：1.确认影响范围与时长；2.通知技术值班；3.15分钟内启动应急预案；4.通过公告/短信通知用户；5.故障恢复后补偿方案"),
        ("运营SOP-大促期间保障方案", "operation", "sop",
         "大促保障：1.提前扩容(3倍日常)；2.关闭非核心服务；3.实时监控QPS/RT/错误率；4.降级开关预备；5.每小时同步战报"),

        # 案例分析
        ("CASE:支付宝掉单-回调延迟典型案例", "payment", "case",
         "支付宝掉单案例：用户支付成功但订单状态未更新。根因：支付宝回调延迟3分钟，期间用户刷新页面触发重复支付检查。方案：增加回调等待窗口至5分钟，主动查询补偿"),
        ("CASE:微信支付-余额不足重试风暴", "payment", "case",
         "余额不足重试风暴案例：用户连续点击支付按钮15次，产生15笔支付请求。根因：前端未做防重复点击。方案：增加支付按钮冷却时间3秒，后端幂等校验"),
        ("CASE:风控拦截-大促误杀批量订单", "risk", "case",
         "大促误杀案例：双11期间风控规则过于严格，误拦截200+正常订单。根因：大促期间用户行为模式变化，规则未动态调整。方案：大促期间启用宽松模式，事后人工复核"),
        ("CASE:对账差异-汇率波动导致金额不一致", "reconciliation", "case",
         "汇率差异案例：跨境订单以美元结算，对账时因汇率波动导致人民币金额不一致。根因：使用了不同时间点的汇率。方案：统一使用交易日汇率，差异在0.5%以内自动调账"),
        ("CASE:订单超时-短信通知延迟致用户投诉", "order", "case",
         "短信延迟案例：订单支付超时短信延迟30分钟发出，用户已重新下单并支付成功，收到关闭通知后投诉。根因：短信通道排队积压。方案：切换短信通道，增加时效性监控"),
        ("CASE:退款欺诈-团伙作案检测", "risk", "case",
         "退款欺诈案例：10个账号使用相同设备指纹发起批量退款。根因：设备指纹检测未覆盖退款场景。方案：退款环节增加设备指纹校验，相同设备24小时内退款>3次触发风控"),
        ("CASE:渠道故障-银联宕机紧急切换", "payment", "case",
         "银联宕机案例：银联渠道突发故障30分钟，期间所有交易失败。根因：单渠道依赖+无自动切换。方案：实现多渠道自动降级切换，故障5秒内切换备用渠道"),
        ("CASE:数据库死锁-对账任务阻塞", "reconciliation", "case",
         "对账死锁案例：对账任务与订单更新事务发生死锁，导致对账中断2小时。根因：大事务未拆分+锁顺序不一致。方案：拆分对账事务为小批次，统一加锁顺序"),
    ]

    # 从模板生成大量变体
    docs = []
    for i, (title, domain, dtype, content) in enumerate(templates):
        docs.append({
            "doc_id": f"KB{i+1:03d}",
            "title": title,
            "content": content,
            "biz_domain": domain,
            "doc_type": dtype,
        })

    # 如果模板不足n，随机复制变体
    while len(docs) < n:
        base = random.choice(templates)
        variant_title = f"{base[0]} (变体{len(docs)})"
        variant_content = f"{base[3]} [补充说明{random.randint(1,100)}]：请结合实际业务场景参考执行"
        docs.append({
            "doc_id": f"KB{len(docs)+1:03d}",
            "title": variant_title,
            "content": variant_content,
            "biz_domain": base[1],
            "doc_type": base[2],
        })

    return docs[:n]


def _error_msg(code: str) -> str:
    msgs = {
        "E2001": "支付超时，回调未到达",
        "E2002": "余额不足",
        "E2003": "渠道异常",
        "E2004": "支付已退回",
        "E2005": "回调丢失",
        "E2006": "金额不匹配",
        "E2007": "重复支付",
        "E2008": "渠道限流",
        "E2009": "银行卡信息校验失败",
        "E2010": "跨境支付汇率异常",
        "E2011": "分期付款异常",
        "E2012": "企业支付审批超时",
        "E2013": "代付订单异常",
        "E2014": "支付风控拦截",
        "E2015": "支付证书过期",
    }
    return msgs.get(code, f"支付异常{code}")


def generate_all(output_dir: str = "./data") -> Dict[str, Any]:
    """生成全部数据并保存"""
    os.makedirs(output_dir, exist_ok=True)
    start = time.time()

    print(f"生成订单 {ORDER_COUNT}条...")
    orders = generate_orders(ORDER_COUNT)
    order_ids = list(orders.keys())

    print(f"生成支付 {PAYMENT_COUNT}条...")
    payments = generate_payments(PAYMENT_COUNT, order_ids)

    print(f"生成风控 {RISK_COUNT}条...")
    risks = generate_risks(RISK_COUNT, order_ids)

    print(f"生成对账 {RECON_COUNT}条...")
    recons = generate_reconciliations(RECON_COUNT, order_ids)

    print(f"生成知识库 {KB_COUNT}条...")
    kb_docs = generate_knowledge_base(KB_COUNT)

    # 保存
    datasets = {
        "orders": orders,
        "payments": payments,
        "risks": risks,
        "reconciliations": recons,
        "knowledge_base": kb_docs,
    }

    for name, data in datasets.items():
        path = os.path.join(output_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    elapsed = (time.time() - start) * 1000

    summary = {
        "orders": len(orders),
        "payments": len(payments),
        "risks": len(risks),
        "reconciliations": len(recons),
        "knowledge_base": len(kb_docs),
        "total": len(orders) + len(payments) + len(risks) + len(recons) + len(kb_docs),
        "duration_ms": round(elapsed, 2),
    }

    print(f"\n数据生成完成:")
    print(f"  订单: {summary['orders']}条")
    print(f"  支付: {summary['payments']}条")
    print(f"  风控: {summary['risks']}条")
    print(f"  对账: {summary['reconciliations']}条")
    print(f"  知识库: {summary['knowledge_base']}条")
    print(f"  合计: {summary['total']}条")
    print(f"  耗时: {summary['duration_ms']:.1f}ms")
    print(f"  输出: {output_dir}/")

    return summary


if __name__ == "__main__":
    generate_all()
