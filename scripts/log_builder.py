#!/usr/bin/env python3
"""
四维日志构建模块

所有函数均为纯数据→文本转换，不做 API 调用。
"""

from typing import Optional


# ─── 带动性日志 ──────────────────────────────────────────

def build_drive_logs(code: str, name: str, drive_result: dict,
                     stock_5min: list[dict],
                     companions: list[dict],
                     sector_5min: list[dict]) -> list[str]:
    """生成带动性详细日志。"""
    logs = []
    best = drive_result.get("best_day", {}) or {}
    bk = best.get("breakdown", {}) or {}
    score = drive_result.get("score", 0)
    board_time = best.get("board_time", "")
    date = best.get("date", "")

    if not best:
        logs.append("带动性: 无涨停日数据")
        return logs

    # 板块与股票行为描述
    has_5min = False
    if stock_5min:
        pre = _describe_pre_board(stock_5min, board_time)
        if pre:
            logs.extend(pre)
            has_5min = True
        vol = _describe_volume_spike(stock_5min, board_time, code, name)
        if vol:
            logs.extend(vol)
            has_5min = True

    # 封板时间
    if board_time and board_time not in ("", "-", "9999"):
        logs.append(f"{board_time[:2]}:{board_time[2:4]} {name} 封板")
    elif has_5min:
        logs.append(f"{name} 封板")

    # 小弟跟风
    if companions:
        for cp in companions:
            cp_name = cp.get("name", cp.get("code", ""))
            cp_kline = cp.get("kline", [])
            cp_log = _describe_companion(cp_kline, cp_name, board_time)
            if cp_log:
                logs.append(cp_log)

    # 板块指数
    if sector_5min:
        sec_log = _describe_sector_reaction(sector_5min, board_time)
        if sec_log:
            logs.append(sec_log)

    if not logs:
        logs.append(f"带动性: {score:.0f}分")

    return logs


def _describe_pre_board(kline: list[dict], board_time: str) -> list[str]:
    """描述封板前横盘行为。"""
    tb = _time_to_index(board_time)
    if tb is None or tb < 2:
        return []
    pre_bars = kline[max(0, tb - 4):tb]
    if len(pre_bars) < 2:
        return []
    highs = [b["high"] for b in pre_bars]
    lows = [b["low"] for b in pre_bars]
    if not lows or lows[0] == 0:
        return []
    range_pct = (max(highs) / min(lows) - 1) * 100
    if range_pct < 0.5:
        start_t = pre_bars[0]["time"]
        end_t = pre_bars[-1]["time"]
        return [f"{_fmt_time(start_t)}-{_fmt_time(end_t)} 持续横盘，振幅仅{range_pct:.1f}%"]
    return []


def _describe_volume_spike(kline: list[dict], board_time: str,
                           code: str, name: str) -> list[str]:
    """描述封板时放量行为。"""
    tb = _time_to_index(board_time)
    if tb is None:
        return []
    if tb >= len(kline):
        tb = len(kline) - 1
    spike_bar = kline[tb]
    prev_bars = kline[max(0, tb - 5):tb]
    if not prev_bars:
        return []
    avg_vol = sum(b.get("volume", 0) for b in prev_bars) / len(prev_bars)
    spike_vol = spike_bar.get("volume", 0)
    if avg_vol > 0 and spike_vol > avg_vol * 1.5:
        ratio = spike_vol / avg_vol
        t = _fmt_time(spike_bar["time"])
        return [f"{t} {name} 放量拉升(量比约{ratio:.0f}x) → 封板"]
    elif spike_vol > 0:
        t = _fmt_time(spike_bar["time"])
        return [f"{t} {name} 拉升封板"]
    return []


def _describe_companion(kline: list[dict], name: str, leader_board_time: str) -> str:
    """描述小弟跟随行为。"""
    if not kline or len(kline) < 2:
        return ""
    # 找封板后 30 分钟内的最高涨幅
    tb = _time_to_index(leader_board_time)
    if tb is None or tb >= len(kline):
        return ""
    start = kline[max(0, tb - 1)]
    end_idx = min(len(kline) - 1, tb + 6)
    best_pct = 0
    best_time = ""
    for i in range(tb + 1, end_idx + 1):
        b = kline[i]
        chg = (b["close"] / start["close"] - 1) * 100
        if chg > best_pct:
            best_pct = chg
            best_time = _fmt_time(b["time"])
    if best_pct >= 1.0:
        return f"{best_time} {name} 跟随拉升+{best_pct:.1f}%"
    elif best_pct > 0:
        return f"{best_time} {name} 小幅跟随+{best_pct:.1f}%"
    return ""


def _describe_sector_reaction(kline: list[dict], board_time: str) -> str:
    """描述板块指数对封板的反应。"""
    if not kline or len(kline) < 2:
        return ""
    tb = _time_to_index(board_time)
    if tb is None:
        return ""
    # 封板前一根 vs 封板后最高点
    pre_idx = max(0, tb - 1)
    pre_close = kline[pre_idx]["close"]
    post_end = min(len(kline) - 1, tb + 6)
    post_high = max(b["close"] for b in kline[tb:post_end + 1])
    chg = (post_high / pre_close - 1) * 100
    if chg > 0.5:
        return f"板块指数同步拉升+{chg:.1f}%"
    elif chg > 0:
        return f"板块指数微幅上扬+{chg:.1f}%"
    return ""


# ─── 抗跌性日志 ──────────────────────────────────────────

def build_anti_drop_logs(anti_drop_result: dict) -> list[str]:
    """生成抗跌性详细日志。"""
    logs = []
    daily = anti_drop_result.get("daily_scores", [])
    if not daily:
        data = anti_drop_result.get("details", "")
        if data:
            logs.append(f"抗跌性: {data}")
        else:
            logs.append("抗跌性: 无跳水日数据")
        return logs

    for d in daily:
        date = d.get("date", "")[-5:]  # MM-DD
        mpct = d.get("market_pct", 0)
        rel = d.get("rel_score", 0)
        sup = d.get("support_score", 0)
        reb = d.get("rebound_score", 0)
        parts = [f"{date} 大盘{mpct:+.1f}%"]

        if rel >= 80:
            parts.append("逆势抗跌")
        elif rel >= 50:
            parts.append("小幅跟跌")
        else:
            parts.append("跟跌明显")

        if sup >= 70:
            parts.append("承接强")
        elif sup >= 40:
            parts.append("承接一般")

        if reb >= 70:
            parts.append("次日反弹强劲")
        elif reb >= 50:
            parts.append("次日小幅反弹")

        logs.append(" → ".join(parts))

    return logs


# ─── 领涨性日志 ──────────────────────────────────────────

def build_leadership_logs(leading_result: dict) -> list[str]:
    """生成领涨性详细日志。"""
    logs = []
    bk = leading_result.get("breakdown", {}) or {}
    size = bk.get("industry_size", 0)
    rank_pct = bk.get("avg_pct_rank", 0.5)
    median = bk.get("industry_median_pct", 0)
    dev = bk.get("deviation_bonus", 0)

    rank_pos = int(rank_pct * size) if size > 0 else 0
    if size > 0:
        logs.append(f"行业排名前{rank_pct*100:.0f}% ({rank_pos}/{size})")
    else:
        logs.append(f"行业排名前{rank_pct*100:.0f}%")

    logs.append(f"跑赢中位数{median:+.1f}%")
    if dev > 5:
        logs.append(f"偏离度加分+{dev:.0f}")

    return logs


# ─── 资金承接性日志 ────────────────────────────────────────

def build_absorption_logs(absorption_result: dict,
                          code_to_name: dict[str, str]) -> list[str]:
    """生成资金承接性详细日志。"""
    logs = []
    events = absorption_result.get("events") or []
    best = absorption_result.get("best_event")

    if not events:
        note = (absorption_result.get("breakdown", {}) or {}).get("note", "无事件")
        logs.append(f"资金承接: {note}")
        return logs

    # 最佳事件
    if best:
        logs.append(_format_absorption_event(best, code_to_name))

    # 其他事件摘要
    extra = len(events) - 1
    if extra > 0:
        logs.append(f"另有{extra}次虹吸事件")

    return logs


def _format_absorption_event(e: dict, code_to_name: dict[str, str]) -> str:
    """格式化单个虹吸事件。"""
    t = e.get("time", 0)
    h = 9 + (t + 30) // 60
    m = (t + 30) % 60
    time_str = f"{h:02d}:{m:02d}"

    sectors = e.get("dropping_sectors", [])
    named = [code_to_name.get(s, s) for s in sectors[:3]]
    names = "、".join(named) if named else f"{len(sectors)}个板块"
    avg = e.get("dropping_avg", 0)
    count = e.get("dropping_count", 0)

    rise = e.get("target_rise", 0)
    up = e.get("up_bars", 0)
    retrace = e.get("retrace_pct", 0)

    parts = [f"{time_str} {names}(均跌{avg:.1f}%)等{count}个板块跳水"]
    parts.append(f"目标板块逆势拉升+{rise:.1f}%")
    parts.append(f"6K中{up}阳")
    if retrace < 0.2:
        parts.append("尾盘几乎无回撤")
    else:
        parts.append(f"尾盘回撤{retrace*100:.0f}%")

    return " → ".join(parts)


# ─── 工具函数 ────────────────────────────────────────────

def _fmt_time(t: str) -> str:
    """0935 → 09:35"""
    if len(t) >= 4:
        return f"{t[:2]}:{t[2:4]}"
    return t


def _time_to_index(board_time: str) -> Optional[int]:
    """封板时间 HHMM → 5分钟K线下标。0935=1, 0940=2, ..."""
    if not board_time or board_time in ("", "-", "9999"):
        return None
    try:
        h = int(board_time[:2])
        m = int(board_time[2:4])
        minutes = h * 60 + m - 570  # 570 = 9*60+30
        if minutes < 0:
            return 0
        idx = minutes // 5
        return max(0, idx)
    except (ValueError, IndexError):
        return None
