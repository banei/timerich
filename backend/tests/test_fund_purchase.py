from app.services.fund_purchase import parse_em_purchase_row


def test_paused_subscription():
    info = parse_em_purchase_row("161130", "易方达纳指", "暂停申购", 10.0)
    assert info.status == "paused"
    assert info.daily_limit == 0.0


def test_limited_10_yuan():
    info = parse_em_purchase_row("270042", "广发纳指", "限大额", 10.0)
    assert info.status == "limited"
    assert info.daily_limit == 10.0


def test_open_unlimited():
    info = parse_em_purchase_row("118002", "标普", "开放申购", 1e11)
    assert info.status == "active"
    assert info.daily_limit is None


def test_limited_100_when_paused_status_but_cap():
    info = parse_em_purchase_row("018043", "天弘", "暂停申购", 100.0)
    assert info.status == "paused"
    assert info.daily_limit == 0.0
