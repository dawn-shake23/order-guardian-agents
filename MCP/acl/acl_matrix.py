AGENT_ACL = {
    "order": {"tools": ["order_query"], "fields": ["order_id", "amount", "status"]},
    "payment": {"tools": ["payment_query"], "fields": ["channel", "pay_status"]},
    "risk": {"tools": ["risk_rule_check"], "fields": ["risk_score", "blacklist"]},
    "operation": {"tools": [], "fields": ["handle_suggestion"]},
    "reconciliation": {"tools": ["reconcile"], "fields": ["account_diff"]}
}