import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent
KB_PATH = BASE / "products.json"
DEFAULT_CSV = BASE / "demo_products.csv"
OUT_DIR = BASE / "output"


def load_kb():
    with open(KB_PATH, encoding="utf-8") as f:
        return json.load(f)


def near_expiry_threshold(days):
    """临期界定阈值：保质期越短，提前提醒的天数越少（参照行业通用标准）。"""
    if days > 365:
        return 45
    if days >= 180:
        return 20
    if days >= 90:
        return 15
    if days >= 30:
        return 10
    if days >= 16:
        return 5
    if days >= 7:
        return 2
    return 1


def classify(shelf_life_days, produce_date, current_date):
    expire_date = produce_date + timedelta(days=shelf_life_days)
    remaining = (expire_date - current_date).days
    threshold = near_expiry_threshold(shelf_life_days)

    if remaining < 0:
        level, action = "过期", "立即下架，登记报损台账，禁止销售"
    elif remaining <= threshold:
        level, action = "临期", "移至临期专区，打折促销，优先陈列售卖"
    else:
        level, action = "正常", "正常销售"

    return {
        "expire_date": expire_date.isoformat(),
        "remaining_days": remaining,
        "threshold_days": threshold,
        "level": level,
        "action": action,
    }


def parse_date(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def run_batch(csv_path, current_date, kb):
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            category = r["类别"].strip()
            name = r["商品名称"].strip()
            produce = parse_date(r["生产日期"])
            sl_raw = r.get("保质期天数", "").strip()
            sl = int(sl_raw) if sl_raw else kb[category]["default_shelf_life_days"]

            result = classify(sl, produce, current_date)
            result.update(
                {
                    "name": name,
                    "category": category,
                    "produce_date": produce.isoformat(),
                    "shelf_life_days": sl,
                    "quantity": r.get("数量", "").strip(),
                    "storage_required": kb[category]["storage"],
                    "storage_actual": r.get("实际贮存条件", "").strip(),
                }
            )
            rows.append(result)
    return rows


def render_markdown(rows, current_date):
    counts = Counter(r["level"] for r in rows)
    lines = [
        f"# 门店食品安全巡检清单（{current_date.isoformat()}）",
        "",
        f"- 总商品数：{len(rows)} 件",
        f"- 过期：{counts.get('过期', 0)} 件（需立即下架报损）",
        f"- 临期：{counts.get('临期', 0)} 件（需打折促销）",
        f"- 正常：{counts.get('正常', 0)} 件",
        "",
        "| 等级 | 商品 | 类别 | 生产日期 | 到期日 | 剩余天数 | 数量 | 要求贮存 | 实际贮存 | 处理建议 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    order = {"过期": 0, "临期": 1, "正常": 2}
    for r in sorted(rows, key=lambda x: (order[x["level"]], x["remaining_days"])):
        lines.append(
            "| {level} | {name} | {category} | {produce_date} | {expire_date} | "
            "{remaining_days} | {quantity} | {storage_required} | {storage_actual} | {action} |".format(**r)
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="门店临期 / 食品安全自查助手")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="商品清单 CSV 路径")
    parser.add_argument("--date", default=date.today().isoformat(), help="巡检日期 YYYY-MM-DD，默认今天")
    args = parser.parse_args()

    current_date = parse_date(args.date)
    kb = load_kb()
    rows = run_batch(Path(args.csv), current_date, kb)

    markdown = render_markdown(rows, current_date)
    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"巡检清单_{current_date.isoformat()}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"\n[已生成] {out_path}")


if __name__ == "__main__":
    main()
