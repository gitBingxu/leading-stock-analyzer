#!/usr/bin/env python3
"""
东方财富公开 API 封装

所有接口均为公开 JSONP 接口，无需登录，免费使用。
详情见 references/api_reference.md
"""

import json
import re
import time
import urllib.request
import urllib.parse
from typing import Optional, Any
from datetime import datetime, timedelta

BASE_URL = "https://push2.eastmoney.com/api/qt"

def _fetch(url: str, max_retries: int = 3) -> dict:
    """带重试的 HTTP GET，自动去掉 JSONP 包装。"""
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://quote.eastmoney.com/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
            # 去 JSONP 包装
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError(f"no JSON in response: {raw[:200]}")
            data = json.loads(match.group())
            if isinstance(data, dict) and data.get("rc") is not None and data["rc"] != 0:
                raise ValueError(f"API error rc={data.get('rc')} msg={data.get('msg','')}")
            return data
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
    raise last_err


# ─── 涨停榜 ────────────────────────────────────────────

def get_limit_up_list(date: Optional[str] = None) -> list[dict]:
    """
    获取某日涨停板列表。
    date: "2026-05-03" 或 None（最新交易日）
    返回: [{"code":"002xxx","name":"...","pct":10.0,"board_time":"0932",
            "consecutive":2,"industry_code":"BK0429","industry_name":"半导体",
            "turnover":5.2,"amount":523000000}, ...]
    """
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f3,f8,f6,f100,f26,f184,f186",
    }
    qs = urllib.parse.urlencode(params)
    _load_industry_map()
    data = _fetch(f"{BASE_URL}/clist/get?{qs}")

    results = []
    for diff in data.get("data", {}).get("diff", []):
        pct = diff.get("f3", 0)
        if isinstance(pct, str):
            try: pct = float(pct)
            except ValueError: continue
        code = diff.get("f12", "")
        
        # 涨停阈值：主板 9.9%，科创板/创业板 19.8%（取20%的-0.2%避免边界问题）
        if code.startswith(("30", "68")):
            threshold = 19.8
        else:
            threshold = 9.9
            
        if pct < threshold:
            continue
            
        # 日期：使用最新K线日期而非 f26（f26 可能是上市日期）
        raw_date = str(diff.get("f26", ""))
        date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 else ""
        ind_name = diff.get("f100", "") or ""

        # 忽略明显是历史日期（上市日期）的条目，使用当前交易日
        if date_str and date_str < datetime.now().strftime("%Y-%m-%d"):
            date_str = ""

        # 封板时间处理
        board_time = diff.get("f186")
        if isinstance(board_time, int):
            board_time = f"{board_time:04d}"
        elif board_time is not None:
            board_time = str(board_time)
            
        # 连板数
        consecutive = diff.get("f184", 1)
        if isinstance(consecutive, str):
            try:
                consecutive = int(consecutive)
            except ValueError:
                consecutive = 1
        elif consecutive is None:
            consecutive = 1

        results.append({
            "code": code,
            "name": diff.get("f14", ""),
            "pct": pct,
            "date": date_str,
            "board_time": board_time,
            "consecutive": consecutive,
            "industry_name": ind_name,
            "industry_code": _INDUSTRY_NAME_TO_CODE.get(ind_name, ""),
            "turnover": diff.get("f8", 0) or 0,
            "amount": diff.get("f6", 0) or 0,
        })
    return results


def infer_consecutive_boards(code: str, kline: list[dict]) -> int:
    """从K线数据推算连板数。"""
    if not kline or len(kline) < 2:
        return 1
    cons = 1
    threshold = 19.9 if code.startswith(("30", "68")) else 9.5
    # 从最近一天往回数
    for i in range(len(kline) - 1, 0, -1):
        if kline[i]["pct"] >= threshold:
            cons += 1
        else:
            break
    return cons


# ─── 行业成分股 ─────────────────────────────────────────

# 行业名称 → 编码映射（常用板块，运行时动态扩展）
_INDUSTRY_NAME_TO_CODE: dict[str, str] = {}
_INDUSTRY_CODE_TO_NAME: dict[str, str] = {}
_INDUSTRY_MAP_LOADED = False


def _load_industry_map():
    """从东方财富加载全部行业编码→名称映射。"""
    global _INDUSTRY_NAME_TO_CODE, _INDUSTRY_CODE_TO_NAME, _INDUSTRY_MAP_LOADED
    if _INDUSTRY_MAP_LOADED:
        return
    try:
        for pn in [1, 2, 3]:
            params = {
                "pn": str(pn), "pz": "200", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:90+t:2",
                "fields": "f12,f14",
            }
            qs = urllib.parse.urlencode(params)
            data = _fetch(f"{BASE_URL}/clist/get?{qs}")
            raw_diffs = data.get("data", {}).get("diff", [])
            if isinstance(raw_diffs, dict):
                raw_diffs = list(raw_diffs.values())
            if not raw_diffs:
                break
            for item in raw_diffs:
                if isinstance(item, dict):
                    code = item.get("f12", "")
                    name = item.get("f14", "")
                    if code and name:
                        _INDUSTRY_NAME_TO_CODE[name] = code
                        _INDUSTRY_CODE_TO_NAME[code] = name
    except Exception:
        pass
    _INDUSTRY_MAP_LOADED = True


def _industry_name_to_code(name: str) -> str:
    """行业名称 → 编码。"""
    if not name or name == "-":
        return ""
    _load_industry_map()
    return _INDUSTRY_NAME_TO_CODE.get(name, "")


def get_industry_components(industry_code_or_name: str) -> list[dict]:
    """
    获取某行业全量成分股当日行情。
    industry_code_or_name: "BK0429" 或 "半导体"
    返回: [{"code":"002xxx","name":"...","pct":3.5,"turnover":5.0,"amount":1.2e8}, ...]
    """
    # 如果传入的是行业名，先转编码
    if not industry_code_or_name.startswith("BK"):
        code = _industry_name_to_code(industry_code_or_name)
        if not code:
            import sys
            print(f"⚠️ 行业名 '{industry_code_or_name}' 未找到对应BK编码，返回空", file=sys.stderr)
            return []
        industry_code_or_name = code

    params = {
        "pn": "1", "pz": "500", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": f"b:{industry_code_or_name}",
        "fields": "f12,f14,f3,f8,f6",
    }
    qs = urllib.parse.urlencode(params)
    data = _fetch(f"{BASE_URL}/clist/get?{qs}")

    results = []
    raw_diffs = data.get("data", {}).get("diff", [])
    # API 可能返回 dict（有序）或 list
    if isinstance(raw_diffs, dict):
        raw_diffs = list(raw_diffs.values())
    for diff in raw_diffs:
        pct = diff.get("f3", 0)
        if isinstance(pct, str):
            try: pct = float(pct)
            except ValueError: pct = 0
        results.append({
            "code": diff.get("f12", ""),
            "name": diff.get("f14", ""),
            "pct": pct,
            "turnover": diff.get("f8", 0) or 0,
            "amount": diff.get("f6", 0) or 0,
        })
    return results


# ─── 个股日K线 ──────────────────────────────────────────

def get_stock_kline(code: str, days: int = 20) -> list[dict]:
    """
    获取个股日K线（优先使用腾讯 API，东方财富作为备用）。
    code: "600519" 或 "002xxx"
    返回: [{"date":"2026-04-28","open":...,"high":...,"low":...,
            "close":...,"pre_close":...,"pct":...,"volume":...,"amount":...}, ...]
    """
    # 优先尝试腾讯 API（稳定，非交易日也能用）
    results = _get_kline_tencent(code, days)
    if results:
        return results

    # 备用：东方财富 API
    return _get_kline_eastmoney(code, days)


def _get_kline_tencent(code: str, days: int = 20) -> list[dict]:
    """通过腾讯财经 API 获取日K线（内置重试）。"""
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={prefix}{code},day,,,{days},qfq")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://gu.qq.com/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            key = f"{prefix}{code}"
            klines = data.get("data", {}).get(key, {}).get("qfqday", [])
            if not klines:
                klines = data.get("data", {}).get(key, {}).get("day", [])
            if klines:
                break
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
            else:
                return []
    if not klines:
        return []

    results = []
    pre_close = None
    for line in klines:
        if isinstance(line, dict):
            continue
        if len(line) < 6:
            continue
        open_p  = float(line[1])
        close_p = float(line[2])
        high_p  = float(line[3])
        low_p   = float(line[4])
        vol     = float(line[5])
        amt     = float(line[6]) if len(line) > 6 else 0
        pct = (close_p - pre_close) / pre_close * 100 if pre_close else 0
        results.append({
            "date": line[0],
            "open": open_p,
            "close": close_p,
            "high": high_p,
            "low": low_p,
            "pre_close": pre_close or open_p,
            "pct": pct,
            "volume": vol,
            "amount": amt,
        })
        pre_close = close_p
    return results


def _get_kline_eastmoney(code: str, days: int = 20) -> list[dict]:
    """通过东方财富 API 获取日K线（备用）。"""
    market = _get_market(code)
    secid = f"{market}.{code}"
    params = {
        "secid": secid,
        "klt": "101",
        "lmt": str(days),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfbfdc4",
        "fqt": "1",
    }
    qs = urllib.parse.urlencode(params)
    try:
        data = _fetch(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{qs}")
    except Exception:
        return []

    results = []
    klines = data.get("data", {}).get("klines", [])
    pre_close = None
    for line in klines:
        if isinstance(line, dict):
            continue
        parts = line.split(",")
        if len(parts) < 11:
            continue
        open_p  = float(parts[1])
        close_p = float(parts[2])
        high_p  = float(parts[3])
        low_p   = float(parts[4])
        vol     = float(parts[5])
        amt     = float(parts[6])
        pct = (close_p - pre_close) / pre_close * 100 if pre_close else 0
        results.append({
            "date": parts[0],
            "open": open_p,
            "close": close_p,
            "high": high_p,
            "low": low_p,
            "pre_close": pre_close or open_p,
            "pct": pct,
            "volume": vol,
            "amount": amt,
        })
        pre_close = close_p
    return results


# ─── 个股实时行情 ────────────────────────────────────────

def get_stock_quote(code: str) -> dict:
    """
    获取个股实时行情。
    返回: {"code":"600519","name":"贵州茅台","price":1400,"pct":1.5,
           "open":1380,"high":1405,"low":1375,"volume":50000,"amount":7e9}
    """
    market = _get_market(code)
    secid = f"{market}.{code}"
    params = {
        "secid": secid,
        "fields": "f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f170",
    }
    qs = urllib.parse.urlencode(params)
    data = _fetch(f"{BASE_URL}/stock/get?{qs}")
    d = data.get("data", {})
    return {
        "code": d.get("f57", code),
        "name": d.get("f58", ""),
        "price": d.get("f43", 0) / 100 if d.get("f43") else 0,
        "pct": d.get("f170", 0) / 100 if d.get("f170") else 0,
        "open": d.get("f44", 0) / 100 if d.get("f44") else 0,
        "high": d.get("f45", 0) / 100 if d.get("f45") else 0,
        "low": d.get("f46", 0) / 100 if d.get("f46") else 0,
        "volume": d.get("f47", 0),
        "amount": d.get("f48", 0),
    }


# ─── 板块指数 5 分钟 K 线 ────────────────────────────────

def get_sector_5min_kline(industry_code: str, bars: int = 48) -> list[dict]:
    """
    获取板块指数 5 分钟 K 线（优先尝试东方财富，失败返回空）。
    industry_code: "BK0429"
    bars: 默认 48（一天 4h × 12 根/小时）
    返回: [{"time":"0935","open":...,"close":...,"high":...,"low":...,"volume":...,"amount":...}, ...]
    """
    secid = f"90.{industry_code}"
    params = {
        "secid": secid,
        "klt": "5",
        "lmt": str(bars),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfbfdc4",
        "fqt": "1",
    }
    qs = urllib.parse.urlencode(params)
    try:
        data = _fetch(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{qs}")
    except Exception:
        return []

    results = []
    klines = data.get("data", {}).get("klines", [])
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        results.append({
            "time": parts[0].split(" ")[-1][:4] if " " in parts[0] else parts[0],
            "open":  float(parts[1]),
            "close": float(parts[2]),
            "high":  float(parts[3]),
            "low":   float(parts[4]),
            "volume":float(parts[5]),
            "amount":float(parts[6]),
        })
    return results


# ─── 个股 5 分钟 K 线 ────────────────────────────────────

def get_stock_5min_kline(code: str, bars: int = 48) -> list[dict]:
    """
    获取个股 5 分钟 K 线。
    code: "002192" 或 "600519"
    bars: 默认 48（一天 4h × 12 根/小时）
    返回: [{"time":"0935","open":...,"close":...,"high":...,"low":...,"volume":...,"amount":...}, ...]
    """
    market = _get_market(code)
    secid = f"{market}.{code}"
    params = {
        "secid": secid,
        "klt": "5",
        "lmt": str(bars),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfbfdc4",
        "fqt": "1",
    }
    qs = urllib.parse.urlencode(params)
    try:
        data = _fetch(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{qs}")
    except Exception:
        return []

    results = []
    klines = data.get("data", {}).get("klines", [])
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        results.append({
            "time": parts[0].split(" ")[-1][:4] if " " in parts[0] else parts[0],
            "open":  float(parts[1]),
            "close": float(parts[2]),
            "high":  float(parts[3]),
            "low":   float(parts[4]),
            "volume":float(parts[5]),
            "amount":float(parts[6]),
        })
    return results


# ─── 全量板块 5 分钟 K 线 ────────────────────────────────

# 申万二级行业编码列表（精选 50+ 个活跃板块，避免全量 130+ 个请求）
ACTIVE_SECTORS = [
    "BK0429", "BK0431", "BK0433", "BK0435", "BK0437", "BK0439",
    "BK0441", "BK0443", "BK0445", "BK0447", "BK0449", "BK0451",
    "BK0453", "BK0455", "BK0457", "BK0459", "BK0461", "BK0463",
    "BK0465", "BK0467", "BK0469", "BK0471", "BK0473", "BK0475",
    "BK0477", "BK0479", "BK0481", "BK0483", "BK0485", "BK0487",
    "BK0489", "BK0491", "BK0493", "BK0495", "BK0497", "BK0499",
    "BK0501", "BK0503", "BK0505", "BK0507", "BK0509", "BK0511",
    "BK0513", "BK0515", "BK0517", "BK0519", "BK0521", "BK0523",
    "BK0525", "BK0527",
]


def get_all_active_sector_5min() -> dict[str, list[dict]]:
    """
    获取所有活跃板块的 5 分钟 K 线。
    返回: {"BK0429": [{...}, ...], "BK0431": [{...}, ...], ...}
    """
    result = {}
    for code in ACTIVE_SECTORS:
        try:
            kline = get_sector_5min_kline(code, bars=48)
            if kline:
                result[code] = kline
            time.sleep(0.05)  # 限速
        except Exception:
            continue
    return result


# ─── 工具函数 ────────────────────────────────────────────

def _get_market(code: str) -> str:
    """根据代码前缀判断市场。"""
    c = str(code)[:3]
    if c in ("600", "601", "603", "605"):
        return "1"   # 上海
    elif c in ("000", "001", "002", "003"):
        return "0"   # 深圳
    elif c.startswith("30"):
        return "0"   # 创业板，深圳
    elif c.startswith("68"):
        return "1"   # 科创板，上海
    else:
        return "0"


def parse_board_minutes(board_time: Optional[str]) -> Optional[int]:
    """
    将 HHMM 封板时间转为当日分钟数（从 9:30 起算）。
    0932 → 2, None → None
    """
    if board_time is None:
        return None
    try:
        h = int(board_time[:2])
        m = int(board_time[2:4])
        return h * 60 + m
    except (ValueError, IndexError):
        return None


def get_market_index_kline(index_code: str = "1.000001", days: int = 20) -> list[dict]:
    """
    获取大盘指数日K线（优先腾讯，失败时回退东方财富）。
    index_code: "1.000001"（上证）, "0.399001"（深成指）, "0.399006"（创业板指）
    """
    # 腾讯 API: sh000001, sz399001, sz399006
    if index_code == "1.000001":
        qq_code = "sh000001"
    elif index_code == "0.399001":
        qq_code = "sz399001"
    elif index_code == "0.399006":
        qq_code = "sz399006"
    elif index_code == "1.000688":
        qq_code = "sh000688"
    else:
        qq_code = f"sh{index_code.split('.')[-1]}"

    # 优先腾讯
    results = _try_tencent_index_kline(qq_code, days)
    if results:
        return results

    # 备用：东方财富
    return _get_kline_eastmoney(index_code, days)


def _try_tencent_index_kline(qq_code: str, days: int) -> list[dict]:
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={qq_code},day,,,{days},qfq")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://gu.qq.com/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            klines = data.get("data", {}).get(qq_code, {}).get("qfqday", [])
            if not klines:
                klines = data.get("data", {}).get(qq_code, {}).get("day", [])
            if klines:
                break
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
            else:
                return []

    results = []
    pre_close = None
    for line in klines:
        if len(line) < 6:
            continue
        open_p  = float(line[1])
        close_p = float(line[2])
        high_p  = float(line[3])
        low_p   = float(line[4])
        pct = (close_p - pre_close) / pre_close * 100 if pre_close else 0
        results.append({
            "date": line[0],
            "open": open_p,
            "close": close_p,
            "high": high_p,
            "low": low_p,
            "pre_close": pre_close or open_p,
            "pct": pct,
        })
        pre_close = close_p
    return results
