#!/usr/bin/env python3
"""预加载共享数据，写 /tmp/lsa_YYYYMMDD.json。agent 编排工作流的第一步。"""

import sys
import os
import json
import glob
from datetime import datetime, timedelta

from eastmoney_api import get_limit_up_list, get_market_index_kline

MAX_AGE_DAYS = 3
OUTPUT_DIR = "/tmp"


def cleanup():
    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    for f in glob.glob(os.path.join(OUTPUT_DIR, "lsa_*.json")):
        try:
            if datetime.fromtimestamp(os.path.getmtime(f)) < cutoff:
                os.remove(f)
                print(f"  🗑️ 清理: {f}", file=sys.stderr)
        except OSError:
            pass


def main():
    cleanup()

    print("📡 拉取涨停榜...", file=sys.stderr)
    try:
        limit_up_list = get_limit_up_list()
    except Exception as e:
        print(f"❌ 涨停榜获取失败 ({type(e).__name__}): {e}", file=sys.stderr)
        print("ERROR: limit_up_list_failed", file=sys.stderr)
        sys.exit(1)

    print("📈 拉取大盘K线...", file=sys.stderr)
    try:
        market_kline = get_market_index_kline("1.000001", 20)
    except Exception as e:
        print(f"❌ 大盘K线获取失败 ({type(e).__name__}): {e}", file=sys.stderr)
        print("ERROR: market_kline_failed", file=sys.stderr)
        sys.exit(1)

    if not limit_up_list:
        print("⚠️ 涨停榜为空（可能非交易日），仍生成共享文件", file=sys.stderr)

    trading_date = datetime.now().strftime("%Y%m%d")
    if limit_up_list:
        td = limit_up_list[0].get("date", "")
        if td:
            trading_date = td

    data = {
        "generated_at": datetime.now().isoformat(),
        "trading_date": trading_date,
        "limit_up_list": limit_up_list,
        "market_kline": market_kline,
    }

    filepath = os.path.join(OUTPUT_DIR, f"lsa_{trading_date}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    print(f"✅ 共享数据写入: {filepath}", file=sys.stderr)
    print(filepath)


if __name__ == "__main__":
    main()
