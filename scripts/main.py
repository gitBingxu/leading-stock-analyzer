#!/usr/bin/env python3
"""
龙头战法批量筛选 — 主流程

工作流：
  1. 拉取当日涨停榜，过滤出主板 + 非ST
  2. 按连板数排序，取前 15
  3. 逐个跑四维分析
  4. 按加权综合分排序，取前 5
  5. 输出报告（含每只票的四维选择理由）

用法:
  python3 main.py                # 终端输出报告
  python3 main.py --json         # JSON 输出（供定时任务/飞书使用）
  python3 main.py --top 10       # 自定义 Top N
"""

import sys
import json
import argparse
import time
from collections import Counter

from eastmoney_api import (
    get_limit_up_list,
    get_stock_kline,
    get_industry_components,
    infer_consecutive_boards,
    get_market_index_kline,
    get_stock_quote,
    get_sector_5min_kline,
)
from drive_analysis import calc_drive_score
from anti_drop import calc_anti_drop_score
from leadership import calc_leading_score
from absorption import calc_absorption_score


# ─── Step 1: 获取并过滤涨停榜 ─────────────────────────

def fetch_and_filter():
    """拉取涨停榜，过滤：主板 + 非ST。返回 (filtered_list, all_limit_up_list)。"""
    lu = get_limit_up_list()
    filtered = []
    for s in lu:
        code = s["code"]
        name = s["name"]

        # 主板：非 30/68 开头（排除创业板、科创板）
        if code.startswith(("30", "68")):
            continue

        # 非 ST
        if "ST" in name.upper():
            continue

        filtered.append(s)

    print(f"📡 涨停榜: {len(lu)} 只 → 主板非ST: {len(filtered)} 只", file=sys.stderr)
    return filtered, lu


# ─── Step 2: 推算连板、过滤 >2 板、排序 ──────────────────

def rank_by_consecutive(stocks: list[dict]) -> list[dict]:
    """推算连板数，剔除超过 2 板的（不好介入），按连板降序排列。
    同时缓存 K 线数据供后续分析复用。"""
    for s in stocks:
        try:
            kl = get_stock_kline(s["code"], 20)
            s["_cached_kline"] = kl
            s["est_cons"] = infer_consecutive_boards(s["code"], kl) if kl else 1
        except Exception:
            s["_cached_kline"] = []
            s["est_cons"] = 1

    # 剔除连板 > 2
    before = len(stocks)
    stocks = [s for s in stocks if s["est_cons"] <= 2]
    print(f"  剔除 >2 连板: {before} → {len(stocks)} 只", file=sys.stderr)

    stocks.sort(key=lambda x: (x["est_cons"], x.get("pct", 0)), reverse=True)
    return stocks


# ─── Step 3 & 4: 批量四维分析 ───────────────────────────

def batch_analyze(candidates: list[dict], market_kline: list[dict],
                  all_lu: list[dict]) -> list[dict]:
    """对候选股逐个做四维分析，返回结果列表。"""
    # 预加载板块5分钟K线（从涨停榜中收集活跃板块，用于资金承接性跨板块对比）
    sector_klines = {}
    target_codes = {s.get("industry_code", "") for s in candidates if s.get("industry_code")}
    # 从涨停榜中额外补充 8 个最活跃板块
    ind_count = {}
    for lu in all_lu:
        ic = lu.get("industry_code", "")
        if ic and ic not in target_codes:
            ind_count[ic] = ind_count.get(ic, 0) + 1
    extra_codes = sorted(ind_count, key=ind_count.get, reverse=True)[:8]
    all_sector_codes = list(target_codes) + extra_codes
    for sc in all_sector_codes[:15]:
        try:
            kl = get_sector_5min_kline(sc)
            if kl and len(kl) >= 40:
                sector_klines[sc] = kl
            time.sleep(0.1)
        except Exception:
            continue

    results = []
    total = len(candidates)

    for i, stock in enumerate(candidates):
        code = stock["code"]
        name = stock["name"]
        cons = stock.get("est_cons", 1)
        ind_name = stock.get("industry_name", "")

        print(f"  [{i+1}/{total}] {code} {name} ({ind_name}) {cons}连板...",
              file=sys.stderr)

        try:
            result = _analyze_single(stock, market_kline, all_lu, sector_klines)
            results.append(result)
        except Exception as e:
            print(f"    ⚠️ 分析失败: {e}", file=sys.stderr)
            results.append({
                "code": code, "name": name,
                "industry": ind_name, "est_cons": cons,
                "pct": stock.get("pct", 0),
                "composite_score": 0,
                "rating": "❌ 分析失败",
                "drive": {"score": 30},
                "anti_drop": {"score": 50},
                "leading": {"score": 50},
                "absorption": {"score": 50},
                "reasons": [("❌ 错误", str(e))],
            })

        time.sleep(0.2)  # 温柔限速

    # 按综合得分降序
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results


def _analyze_single(stock: dict, market_kline: list[dict],
                    all_lu: list[dict], sector_klines: dict[str, list[dict]]) -> dict:
    """对单只股票执行完整四维分析。"""
    code = stock["code"]
    name = stock["name"]
    ind_name = stock.get("industry_name", "")
    ind_code = stock.get("industry_code", "")

    stock_kline = stock.get("_cached_kline", [])
    if not stock_kline:
        try:
            stock_kline = get_stock_kline(code, 20)
        except Exception:
            stock_kline = []

    try:
        quote = get_stock_quote(code)
    except Exception:
        quote = {"price": 0, "pct": 0}

    latest_date = stock_kline[-1]["date"] if (stock_kline and len(stock_kline) > 0) else ""
    stock["date"] = stock.get("date") or latest_date
    stock["consecutive"] = stock.get("est_cons", 1)
    recent_lu = [stock]

    # ── 带动性 ──
    industry_components = []
    co_limitup_map = {}
    drive_result = {"score": 30, "breakdown": {"error": "无行业数据"}}

    if ind_code:
        try:
            industry_components = get_industry_components(ind_code)
        except Exception:
            industry_components = []

        try:
            co_list = [
                lu for lu in all_lu
                if lu.get("industry_name") == ind_name
                and lu["code"] != code
            ]
            co_limitup_map[stock.get("date", "")] = co_list
            drive_result = calc_drive_score(code, recent_lu, co_limitup_map, industry_components)
        except Exception as e:
            drive_result = {"score": 30, "breakdown": {"error": str(e)}}

    # ── 抗跌性 ──
    try:
        anti_drop_result = calc_anti_drop_score(stock_kline, market_kline)
    except Exception as e:
        anti_drop_result = {"score": 50, "breakdown": {"error": str(e)}}

    # ── 领涨性 ──
    if not industry_components and ind_code:
        try:
            industry_components = get_industry_components(ind_code)
        except Exception:
            industry_components = []
    
    limit_dates = [stock.get("date", "")]
    try:
        leading_result = calc_leading_score(stock_kline, industry_components, limit_dates)
    except Exception as e:
        leading_result = {"score": 50, "breakdown": {"error": str(e)}}

    # ── 资金承接性 ──
    absorption_result = {"score": 50, "breakdown": {"note": "无板块数据"}}
    if ind_code and ind_code in sector_klines:
        try:
            # 跨板块对比：目标板块 + 其他活跃板块
            absorption_result = calc_absorption_score(ind_code, sector_klines)
        except Exception as e:
            absorption_result = {"score": 50, "breakdown": {"error": str(e)}}

    # ── 综合 ──
    drive_score = drive_result.get("score", 30)
    anti_score = anti_drop_result.get("score", 50)
    leading_score = leading_result.get("score", 50)
    absorption_score = absorption_result.get("score", 50)
    
    composite = (
        drive_score * 0.35
        + anti_score * 0.15
        + leading_score * 0.25
        + absorption_score * 0.25
    )

    if composite >= 85:
        rating = "🐉 真龙"
    elif composite >= 70:
        rating = "⭐ 强票"
    elif composite >= 50:
        rating = "📊 中规中矩"
    else:
        rating = "🐔 杂毛"

    reasons = _build_reasons(
        drive_result, anti_drop_result, leading_result, absorption_result
    )

    return {
        "code": code,
        "name": name,
        "industry": ind_name,
        "est_cons": stock.get("est_cons", 1),
        "pct": stock.get("pct", 0),
        "price": quote.get("price", 0),
        "composite_score": round(composite, 1),
        "rating": rating,
        "drive": drive_result,
        "anti_drop": anti_drop_result,
        "leading": leading_result,
        "absorption": absorption_result,
        "reasons": reasons,
    }


# ─── 理由生成 ──────────────────────────────────────────

def _build_reasons(drive, anti_drop, leading, absorption) -> list[tuple[str, str]]:
    reasons = []

    # 带动性
    try:
        ds = drive.get("score", 0)
        best = drive.get("best_day", {}) or {}
        bk = best.get("breakdown", {}) or {}
        voice = bk.get("voice_score", 0)
        follow = bk.get("follow_score", 0)
        board = bk.get("board_leadership_score", 0)
        
        if ds >= 85:
            reasons.append(("🐉 带动性",
                f"板块共鸣{voice:.0f}/跟风{follow:.0f}/决策力{board:.0f}，板块共振强劲"))
        elif ds >= 70:
            reasons.append(("🐉 带动性",
                f"板块共鸣{voice:.0f}/跟风{follow:.0f}/决策力{board:.0f}，有带动效应"))
        elif ds >= 50:
            reasons.append(("🐉 带动性", f"板块效应偏弱"))
        else:
            reasons.append(("🐉 带动性", f"数据不足"))
    except Exception:
        reasons.append(("🐉 带动性", "分析异常"))

    # 抗跌性
    try:
        ads = anti_drop.get("score", 0)
        dc = anti_drop.get("drop_days_count", 0)
        if ads >= 70:
            reasons.append(("🛡️ 抗跌性", f"近{dc}次跳水表现坚挺"))
        elif ads >= 40:
            reasons.append(("🛡️ 抗跌性", f"近{dc}次跳水抗跌一般"))
        elif dc > 0:
            reasons.append(("🛡️ 抗跌性", f"近{dc}次跳水偏弱，警惕系统性风险"))
        else:
            reasons.append(("🛡️ 抗跌性", "近期无跳水日，待验证"))
    except Exception:
        reasons.append(("🛡️ 抗跌性", "分析异常"))

    # 领涨性
    try:
        lds = leading.get("score", 0)
        lbk = leading.get("breakdown", {}) or {}
        rank = lbk.get("avg_pct_rank", 0.5)
        median = lbk.get("industry_median_pct", 0)
        if lds >= 70:
            reasons.append(("📊 领涨性",
                f"行业排名前{rank*100:.0f}%，跑赢中位数{median:+.1f}%"))
        elif lds >= 50:
            reasons.append(("📊 领涨性",
                f"行业排名约{rank*100:.0f}%分位，与中位数{median:+.1f}%持平"))
        else:
            reasons.append(("📊 领涨性", "行业排名靠后"))
    except Exception:
        reasons.append(("📊 领涨性", "分析异常"))

    # 资金承接
    try:
        abs_ = absorption.get("score", 0)
        evt = absorption.get("event_count", 0)
        if abs_ >= 70:
            reasons.append(("💰 资金承接", f"发现{evt}次跨板块虹吸事件"))
        elif abs_ >= 50:
            reasons.append(("💰 资金承接", "暂无显著跨板块虹吸信号"))
        else:
            reasons.append(("💰 资金承接", "资金承接信号弱"))
    except Exception:
        reasons.append(("💰 资金承接", "分析异常"))

    return reasons


# ─── 输出 ──────────────────────────────────────────────

def print_results(results: list[dict]):
    """终端格式化输出 Top N。"""
    print()
    print("=" * 70)
    print("  🐉 龙头战法批量筛选 — 最新交易日")
    print("=" * 70)
    print()

    for rank, r in enumerate(results, 1):
        medal = ["🥇", "🥈", "🥉", "4", "5"][rank - 1] if rank <= 5 else str(rank)
        cons = r.get("est_cons", 1)
        pct = r.get("pct", 0)
        print(f"  {medal}  {r['name']}({r['code']})  {r['industry']}  "
              f"{cons}连板 {pct:+.1f}%")
        print(f"     综合: {r['composite_score']:.1f}  {r['rating']}")
        print(f"     带动性 {r['drive']['score']:.0f}  "
              f"抗跌性 {r['anti_drop']['score']:.0f}  "
              f"领涨性 {r['leading']['score']:.0f}  "
              f"承接 {r['absorption']['score']:.0f}")
        print(f"     📋 ", end="")
        for label, text in r.get("reasons", []):
            print(f"{label}: {text}", end="  ")
        print()
        print()


# ─── 主流程 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="龙头战法批量筛选")
    parser.add_argument("--top", type=int, default=5, help="输出前 N 名（默认5）")
    parser.add_argument("--candidates", type=int, default=15,
                        help="分析候选数（默认15）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    t_start = time.time()

    # Step 1: 拉涨停榜 + 过滤
    print("🔍 拉取涨停榜...", file=sys.stderr)
    stocks, all_lu = fetch_and_filter()

    if not stocks:
        print("⚠️ 无符合条件的涨停股", file=sys.stderr)
        sys.exit(1)

    # Step 2: 推算连板 + 排序
    print("📊 推算连板数...", file=sys.stderr)
    stocks = rank_by_consecutive(stocks)

    # Step 3: 取前 N 候选
    candidates = stocks[:args.candidates]
    print(f"🎯 候选池: {len(candidates)} 只 (连板 {candidates[0].get('est_cons',1)}→{candidates[-1].get('est_cons',1)})",
          file=sys.stderr)

    # 预加载大盘K线（复用）
    print("📈 加载大盘数据...", file=sys.stderr)
    market_kline = get_market_index_kline("1.000001", 20)

    # Step 4: 批量四维分析
    print(f"🐉 四维分析 ({len(candidates)} 只)...", file=sys.stderr)
    analyzed = batch_analyze(candidates, market_kline, all_lu)

    # Step 5: 取前 N
    top_n = analyzed[:args.top]
    elapsed = time.time() - t_start
    print(f"\n✅ 完成 ({elapsed:.0f}s)", file=sys.stderr)

    # Step 6: 输出
    if args.json:
        print(json.dumps(top_n, ensure_ascii=False, indent=2, default=str))
    else:
        print_results(top_n)


if __name__ == "__main__":
    main()
