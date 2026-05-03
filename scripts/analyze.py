#!/usr/bin/env python3
"""
龙头战法量化分析 — 主入口

用法:
    python3 analyze.py 002xxx                    # 分析单只股票
    python3 analyze.py 002xxx --verbose          # 详细输出
    python3 analyze.py 002xxx --json             # JSON 输出
"""

import sys
import json
import argparse
import time
from datetime import datetime

from eastmoney_api import (
    get_limit_up_list,
    get_industry_components,
    get_stock_kline,
    get_stock_quote,
    get_all_active_sector_5min,
    get_market_index_kline,
    infer_consecutive_boards,
)
from drive_analysis import calc_drive_score
from anti_drop import calc_anti_drop_score
from leadership import calc_leading_score
from absorption import calc_absorption_score


def analyze_stock(code: str, verbose: bool = False) -> dict:
    """对单只股票执行四维分析。"""

    print(f"🔍 正在分析 {code}...", file=sys.stderr)

    # ── 数据采集 ──
    print("  📡 获取涨停榜...", file=sys.stderr)
    limit_up_list = get_limit_up_list()

    print("  📊 获取个股K线...", file=sys.stderr)
    stock_kline = get_stock_kline(code, days=20)

    print("  📈 获取大盘指数K线...", file=sys.stderr)
    market_kline = get_market_index_kline("1.000001", days=20)

    print("  🏷️  获取实时行情...", file=sys.stderr)
    quote = get_stock_quote(code)

    # 找到该股近 3 个涨停日，并推算连板数 + 补日期
    stock_limit_ups = [lu for lu in limit_up_list if lu["code"] == code]
    # 用最新 K 线日期填充涨停日期
    latest_date = stock_kline[-1]["date"] if stock_kline else ""
    for lu in stock_limit_ups:
        lu["consecutive"] = infer_consecutive_boards(code, stock_kline)
        if not lu.get("date"):
            lu["date"] = latest_date
    stock_limit_ups.sort(key=lambda x: x.get("consecutive", 1), reverse=True)
    recent_limit_ups = stock_limit_ups[:3]

    if not recent_limit_ups:
        print(f"  ⚠️  {code} 近期无涨停记录，带动性/承接性分析受限", file=sys.stderr)

    # 行业信息：优先从涨停榜获取，其次从实时行情
    industry_name = recent_limit_ups[0]["industry_name"] if recent_limit_ups else ""
    industry_code = recent_limit_ups[0]["industry_code"] if recent_limit_ups else ""

    if not industry_name:
        # 尝试从实时行情推断（可能为空）
        industry_name = "未知"

    # ── 维度一：带动性 ──
    print("  🐉 分析带动性...", file=sys.stderr)
    drive_result = {"score": 30, "breakdown": {"error": "无涨停日数据"}}
    co_limitup_map = {}

    if recent_limit_ups and industry_code:
        # 获取行业成分股
        industry_components = get_industry_components(industry_code if industry_code else industry_name)

        # 构建 co_limitup_map：同行业其他涨停股
        for ld in recent_limit_ups:
            co_list = [
                lu for lu in limit_up_list
                if lu.get("industry_name") == industry_name
                and lu["code"] != code
            ]
            co_limitup_map[ld.get("date", "")] = co_list

        drive_result = calc_drive_score(
            code, recent_limit_ups, co_limitup_map, industry_components
        )
    else:
        industry_components = []

    # ── 维度二：抗跌性 ──
    print("  🛡️  分析抗跌性...", file=sys.stderr)
    anti_drop_result = calc_anti_drop_score(stock_kline, market_kline)

    # ── 维度三：领涨性 ──
    print("  📊 分析领涨性...", file=sys.stderr)
    if not industry_components and industry_code:
        industry_components = get_industry_components(industry_code)
    limit_dates = [ld.get("date", "") for ld in recent_limit_ups]
    leading_result = calc_leading_score(stock_kline, industry_components, limit_dates)

    # ── 维度四：资金承接性（轻量模式：只加载目标板块）──
    print("  💰 分析资金承接性...", file=sys.stderr)
    absorption_result = {"score": 50, "breakdown": {"note": "无行业数据"}}
    if industry_code:
        try:
            from eastmoney_api import get_sector_5min_kline
            target_sector = get_sector_5min_kline(industry_code)
            if target_sector and len(target_sector) >= 40:
                # 只传目标板块（轻量模式），多板块对比需 --deep 模式
                absorption_result = calc_absorption_score(
                    industry_code, {industry_code: target_sector}
                )
        except Exception as e:
            absorption_result = {"score": 50, "breakdown": {"error": str(e)}}

    # ── 综合评分 ──
    composite = (
        drive_result["score"] * 0.35
        + anti_drop_result["score"] * 0.15
        + leading_result["score"] * 0.25
        + absorption_result["score"] * 0.25
    )

    # 评级
    if composite >= 85:
        rating = "🐉 真龙"
    elif composite >= 70:
        rating = "⭐ 强票"
    elif composite >= 50:
        rating = "📊 中规中矩"
    else:
        rating = "🐔 杂毛"

    return {
        "code": code,
        "name": quote.get("name", ""),
        "price": quote.get("price", 0),
        "pct": quote.get("pct", 0),
        "industry": industry_name,
        "industry_code": industry_code,
        "composite_score": round(composite, 1),
        "rating": rating,
        "drive": drive_result,
        "anti_drop": anti_drop_result,
        "leading": leading_result,
        "absorption": absorption_result,
    }


def print_report(result: dict, verbose: bool = False):
    """格式化输出分析报告。"""
    print()
    print("=" * 60)
    print(f"  🐉 龙头战法量化分析 — {result['name']}({result['code']})")
    print("=" * 60)
    print(f"  现价: {result['price']:.2f}  |  涨跌: {result['pct']:+.2f}%")
    print(f"  行业: {result['industry']}")
    print()

    # 综合评分
    score = result["composite_score"]
    bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
    print(f"  📊 综合评分: {score:.1f} / 100  {bar}")
    print(f"  🏅 评级:     {result['rating']}")
    print()
    print("  " + "-" * 56)

    # 各维度明细
    dims = [
        ("带动性",    result["drive"],      0.35),
        ("抗跌性",    result["anti_drop"],   0.15),
        ("领涨性",    result["leading"],     0.25),
        ("资金承接",  result["absorption"],  0.25),
    ]
    for name, dim, w in dims:
        s = dim["score"]
        bar = "▓" * int(s / 5) + "░" * (20 - int(s / 5))
        print(f"  {name:　<6s}  {s:5.1f} ×{w:.2f}  {bar}")

    print()

    # ── 四维选择理由 ──
    print("  📋 四维选择理由:")
    reasons = _build_reasons(result)
    for label, text in reasons:
        print(f"     {label}: {text}")

    print()
    if verbose:
        print("=" * 60)
        print("  详细分析")
        print("=" * 60)

        # 带动性详情
        d = result["drive"]
        print(f"\n── 带动性 (score={d['score']}) ──")
        if "best_day" in d and d["best_day"]:
            bd = d["best_day"]
            print(f"  最佳日: {bd.get('date','')}  封板时间: {bd.get('board_time','一键')}")
            bk = bd.get("breakdown", {})
            print(f"    板块共鸣度: {bk.get('voice_score','')}")
            print(f"    板块跟风力: {bk.get('follow_score','')}")
            print(f"    封板决策力: {bk.get('board_leadership_score','')}")
        elif "error" in d.get("breakdown", {}):
            print(f"  ⚠️ {d['breakdown']['error']}")

        # 抗跌性详情
        ad = result["anti_drop"]
        print(f"\n── 抗跌性 (score={ad['score']}) ──")
        if ad.get("drop_days_count", 0) > 0:
            print(f"  跳水日数: {ad['drop_days_count']}")
            for date, bd in ad.get("breakdown", {}).items():
                print(f"    {date}: 相对回撤={bd.get('rel_score')} 承接={bd.get('support_score')} 反弹={bd.get('rebound_score')} → {bd.get('total')}")
        else:
            print(f"  ℹ️ {ad.get('details', '无跳水日')}")

        # 领涨性详情
        ld = result["leading"]
        print(f"\n── 领涨性 (score={ld['score']}) ──")
        bk = ld.get("breakdown", {})
        print(f"  分位排名: {bk.get('avg_pct_rank',0):.1%}（0%最优/100%最差)")
        print(f"  行业中位数涨幅: {bk.get('industry_median_pct', 0):+.2f}%")
        print(f"  偏离度加分: {bk.get('deviation_bonus', 0)}")

        # 资金承接性详情
        ab = result["absorption"]
        print(f"\n── 资金承接性 (score={ab['score']}) ──")
        if ab.get("event_count", 0) > 0:
            print(f"  虹吸事件数: {ab['event_count']}")
            be = ab.get("best_event")
            if be:
                print(f"  最佳事件: {be['dropping_count']}个板块逃逸 "
                      f"(均跌{be['dropping_avg']:.2f}%) → "
                      f"目标拉升{be['target_rise']:.2f}%")
                print(f"  回撤: {be['retrace_pct']*100:.1f}%  |  方向一致性: {be['up_bars']}/6阳")
        else:
            print(f"  ℹ️ {ab.get('breakdown',{}).get('note','无事件')}")
        print()


def _build_reasons(result: dict) -> list[tuple[str, str]]:
    """根据四维得分生成选择理由。"""
    reasons = []

    # 带动性
    d = result.get("drive", {})
    ds = d.get("score", 0)
    best = d.get("best_day", {}) or {}
    bk = best.get("breakdown", {}) or {}
    voice = bk.get("voice_score", 0)
    follow = bk.get("follow_score", 0)
    board = bk.get("board_leadership_score", 0)

    if ds >= 85:
        reasons.append(("🐉 带动性",
            f"板块共鸣{voice:.0f}/跟风{follow:.0f}/决策力{board:.0f}，"
            f"同板块小弟跟风紧密，实打实的带头大哥"))
    elif ds >= 70:
        reasons.append(("🐉 带动性",
            f"板块共鸣{voice:.0f}/跟风{follow:.0f}/决策力{board:.0f}，"
            f"有带动效应但板块共振还不够强"))
    elif ds >= 50:
        reasons.append(("🐉 带动性",
            f"板块共鸣{voice:.0f}/跟风{follow:.0f}/决策力{board:.0f}，"
            f"带动性一般，板块效应不明显"))
    else:
        reasons.append(("🐉 带动性", f"数据不足，无法评估带动效应"))

    # 抗跌性
    ad = result.get("anti_drop", {})
    ads = ad.get("score", 0)
    drop_count = ad.get("drop_days_count", 0)
    if ads >= 70:
        reasons.append(("🛡️ 抗跌性",
            f"近{drop_count}次大盘跳水中表现坚挺，资金承接力强"))
    elif ads >= 40:
        reasons.append(("🛡️ 抗跌性",
            f"近{drop_count}次大盘跳水中抗跌一般，有跟跌倾向"))
    elif drop_count > 0:
        reasons.append(("🛡️ 抗跌性",
            f"近{drop_count}次大盘跳水中表现偏弱，需警惕系统性风险"))
    else:
        reasons.append(("🛡️ 抗跌性", "近期无跳水日，抗跌性待验证"))

    # 领涨性
    ld = result.get("leading", {})
    lds = ld.get("score", 0)
    lbk = ld.get("breakdown", {}) or {}
    rank = lbk.get("avg_pct_rank", 0.5)
    median = lbk.get("industry_median_pct", 0)
    if lds >= 70:
        reasons.append(("📊 领涨性",
            f"行业排名前{rank*100:.0f}%，持续跑赢板块中位数{median:+.1f}%"))
    elif lds >= 50:
        reasons.append(("📊 领涨性",
            f"行业排名约{rank*100:.0f}%分位，与板块中位数{median:+.1f}%持平"))
    else:
        reasons.append(("📊 领涨性", f"行业排名靠后，非板块领涨品种"))

    # 资金承接性
    ab = result.get("absorption", {})
    abs_ = ab.get("score", 0)
    evt = ab.get("event_count", 0)
    if abs_ >= 70:
        reasons.append(("💰 资金承接",
            f"发现{evt}次跨板块虹吸事件，资金主动涌入且持续到收盘"))
    elif abs_ >= 50:
        reasons.append(("💰 资金承接",
            f"暂未发现显著的跨板块资金虹吸信号" if evt == 0 else
            f"发现{evt}次虹吸事件但强度偏弱"))
    else:
        reasons.append(("💰 资金承接", "资金承接信号弱，板块间无资金集中迹象"))

    return reasons


def main():
    parser = argparse.ArgumentParser(description="龙头战法量化分析")
    parser.add_argument("code", help="股票代码，如 002xxx 或 600519")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--json", "-j", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    result = analyze_stock(args.code, verbose=args.verbose or args.json)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_report(result, verbose=args.verbose)


if __name__ == "__main__":
    main()
