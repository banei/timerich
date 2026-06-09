from app.services.bucket_config import parse_bucket_config, validate_bucket_targets


def test_parse_custom_names():
    raw = {
        "buckets": [
            {"code": "growth", "name": "纳指", "target_pct": 0.35, "color": "#3ABFF8"},
            {"code": "dividend", "name": "红利", "target_pct": 0.40, "color": "#F87272"},
            {"code": "gold", "name": "黄金", "target_pct": 0.0, "color": "#FBBD23"},
            {"code": "bond_long", "name": "长债", "target_pct": 0.175, "color": "#B083F0"},
            {"code": "bond_short", "name": "短债", "target_pct": 0.075, "color": "#67E8F9"},
        ]
    }
    buckets = parse_bucket_config(raw)
    assert buckets[0].name == "纳指"
    assert validate_bucket_targets(buckets)
