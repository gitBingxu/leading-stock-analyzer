#!/usr/bin/env python3
"""
领涨性分析模块 (Leadership Analysis)

平时（非涨停日）这只票在同行业里排第几？
"""


def calc_leading_score(
    stock_kline: list[dict],
    industry_components: list[dict],
    limit_up_dates: list[str],
) -> dict:
    """
    计算领涨性综合得分。

    参数:
        stock_kline: 个股近 15 个交易日日K线
        industry_components: 某日行业成分股行情（取最近一个交易日）
        limit_up_dates: 涨停日期列表

    返回:
        {"score": 72, "breakdown": {"avg_pct_rank": 0.28, "deviation_bonus": 5}}
    """
    if not industry_components:
        return {"score": 50, "breakdown": {"error": "无行业数据"}}

    # Step 1: 单日排名
    sorted_comp = sorted(industry_components, key=lambda x: x.get("pct", 0), reverse=True)
    total = len(sorted_comp)
    stock_code = stock_kline[-1].get("code", "") if stock_kline else ""

    rank = None
    for i, s in enumerate(sorted_comp):
        if s["code"] == stock_code or not stock_code:
            rank = i + 1
            break
    if rank is None:
        rank = total // 2  # 中位数兜底

    pct_rank = rank / total

    # Step 2: 近 5 个非涨停日排名均值（简化：用日K涨跌幅模拟）
    non_limit_dates = []
    for k in stock_kline:
        if k["date"] not in limit_up_dates:
            non_limit_dates.append(k)

    recent = non_limit_dates[-5:] if len(non_limit_dates) >= 5 else non_limit_dates

    # 用行业涨幅中位数做近似排名
    median_pct = _median([s.get("pct", 0) for s in industry_components])

    pct_ranks = []
    for k in recent:
        # 该股日涨幅 vs 行业中位数，估算其分位
        deviation = k["pct"] - median_pct
        # 偏离越大，排名越靠前（简化估计）
        est_rank = max(0.01, 0.5 - deviation * 0.1)
        est_rank = max(0.01, min(1.0, est_rank))
        pct_ranks.append(est_rank)

    avg_rank = sum(pct_ranks) / len(pct_ranks) if pct_ranks else pct_rank
    leading = (1 - avg_rank) * 100

    # Step 3: 偏离度加分
    last_k = stock_kline[-1] if stock_kline else {"pct": 0}
    deviation = last_k["pct"] - median_pct
    deviation_bonus = max(0, min(deviation * 50, 20))

    return {
        "score": round(min(leading + deviation_bonus, 100), 1),
        "breakdown": {
            "avg_pct_rank": round(avg_rank, 3),
            "base_score": round(leading, 1),
            "deviation_bonus": round(deviation_bonus, 1),
            "industry_size": total,
            "industry_median_pct": round(median_pct, 2),
        },
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
