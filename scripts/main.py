#!/usr/bin/env python3
"""
龙头战法批量筛选 — 主流程 (v2 subprocess并行版)

工作流：
  0. 预加载共享数据 → /tmp/lsa_YYYYMMDD.json（自动清理3天前旧文件）
  1. 拉取当日涨停榜，过滤出主板 + 非ST
  2. 按连板数排序，取前 N 候选
  3. subprocess 并行调 analyze.py --shared-data（默认2并发）
  4. 按加权综合分排序，取前 N
  5. 输出报告

用法:
  python3 main.py                    # 终端输出报告（默认 top 5，候选 10）
  python3 main.py --json             # JSON 输出
  python3 main.py --top 10           # 自定义 Top N
  python3 main.py --workers 3        # 并行数（默认2，防风控）
  python3 main.py --workers 1        # 串行（风控严格时使用）
"""

import sys
import json
import argparse
import time
import os
import glob
import subprocess
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from eastmoney_api import (
    get_limit_up_list,
    get_stock_kline,
    infer_consecutive_boards,
    get_market_index_kline,
)

OUTPUT_DIR = "/tmp"
MAX_AGE_DAYS = 3


# ─── Step 0: 预加载共享数据 ──────────────────────────

def _preload_shared_data():
    """清理旧文件 + 拉取涨停榜/大盘K线 → 写 /tmp/lsa_YYYYMMDD.json。"""
    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    for f in glob.glob(os.path.join(OUTPUT_DIR, "lsa_*.json")):
        try:
            if datetime.fromtimestamp(os.path.getmtime(f)) < cutoff:
                os.remove(f)
                print(f"  🗑️ 清理: {f}", file=sys.stderr)
        except OSError:
            pass

    print("📡 拉取涨停榜...", file=sys.stderr)
    try:
        limit_up_list = get_limit_up_list()
        print("📈 拉取大盘K线...", file=sys.stderr)
        market_kline = get_market_index_kline("1.000001", 20)
    except Exception as e:
        print(f"❌ 拉取数据失败 ({type(e).__name__}): {e}", file=sys.stderr)
        sys.exit(1)

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
    return filepath, limit_up_list


# ─── Step 1: 过滤涨停榜 ──────────────────────────

def fetch_and_filter(limit_up_list):
    """过滤：主板 + 非ST。返回 filtered_list。"""
    filtered = []
    for s in limit_up_list:
        code = s["code"]
        name = s["name"]
        if code.startswith(("30", "68")):
            continue
        if "ST" in name.upper():
            continue
        filtered.append(s)

    print(f"📡 涨停榜: {len(limit_up_list)} 只 → 主板非ST: {len(filtered)} 只", file=sys.stderr)
    return filtered


# ─── Step 2: 推算连板、排序 ──────────────────

def rank_by_consecutive(stocks):
    """推算连板数，按连板降序排列。"""
    for s in stocks:
        try:
            kl = get_stock_kline(s["code"], 20)
            time.sleep(0.05)
            s["est_cons"] = infer_consecutive_boards(s["code"], kl) if kl else 1
        except Exception:
            s["est_cons"] = 1

    stocks.sort(key=lambda x: (x["est_cons"], x.get("pct", 0)), reverse=True)
    return stocks


# ─── Step 3: 并行 subprocess 调 analyze.py ───

def _run_single_analysis(code, shared_path, timeout=60):
    """子进程调用 analyze.py --shared-data --json，返回解析后的 dict 或 None。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze.py")
    cmd = [sys.executable, script, code, "--shared-data", shared_path, "--json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            err = result.stderr.strip()[-300:] if result.stderr else "unknown error"
            print(f"  ⚠️ {code} analyze.py 非零退出 (rc={result.returncode}): {err}", file=sys.stderr)
            return None
        data = json.loads(result.stdout)
        return data
    except subprocess.TimeoutExpired:
        print(f"  ❌ {code} 分析超时 ({timeout}s)", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"  ❌ {code} JSON 解析失败: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ❌ {code} 子进程异常 ({type(e).__name__}): {e}", file=sys.stderr)
        return None


def run_parallel(candidates, shared_path, max_workers=2):
    """并行 subprocess 分析所有候选股。返回结果列表（已排序）。"""
    results = []
    total = len(candidates)
    cons_map = {s["code"]: s.get("est_cons", 1) for s in candidates}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, stock in enumerate(candidates):
            code = stock["code"]
            name = stock["name"]
            cons = cons_map.get(code, 1)
            ind_name = stock.get("industry_name", "")
            print(f"  [{i+1}/{total}] 启动 {code} {name} ({ind_name}) {cons}连板...",
                  file=sys.stderr)
            futures[executor.submit(_run_single_analysis, code, shared_path)] = stock
            time.sleep(0.3)

        for future in as_completed(futures):
            stock = futures[future]
            code = stock["code"]
            name = stock["name"]
            ind_name = stock.get("industry_name", "")
            cons = cons_map.get(code, 1)

            try:
                data = future.result()
            except Exception as e:
                data = None
                print(f"  ❌ {code} future 异常: {e}", file=sys.stderr)

            if data is None:
                results.append({
                    "code": code,
                    "name": name,
                    "industry": ind_name,
                    "est_cons": cons,
                    "pct": stock.get("pct", 0),
                    "composite_score": 0,
                    "rating": "❌ 分析失败",
                    "drive": {"score": 0},
                    "anti_drop": {"score": 0},
                    "leading": {"score": 0},
                    "absorption": {"score": 0},
                    "logs": {},
                    "_errors": [("分析", "子进程失败或超时")],
                    "_fallback": True,
                })
            else:
                data["est_cons"] = data.get("est_cons", cons)
                results.append(data)

    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results


# ─── 输出 ──────────────────────────────────────────────

def print_results(results):
    """终端格式化输出 Top N。"""
    print()
    print("=" * 70)
    print("  🐉 龙头战法批量筛选 — 最新交易日")
    print("=" * 70)

    for rank, r in enumerate(results, 1):
        name = r["name"]
        code = r["code"]
        ind = r.get("industry", "")
        cons = r.get("est_cons", 1)
        score = r["composite_score"]
        rating = r["rating"].replace("🐉 ", "").replace("⭐ ", "").replace("📊 ", "").replace("🐔 ", "")

        print(f"\n{name}({code})——{ind}——{cons}连板")
        print(f"    1. 综合评分: {score:.1f}，{rating}")

        ds = r["drive"]["score"]
        dl = r.get("logs", {}).get("drive", "")
        print(f"    - 🐉 带动性({ds:.0f}): {dl}")

        ads = r["anti_drop"]["score"]
        al = r.get("logs", {}).get("anti_drop", "")
        print(f"    - 🛡️ 抗跌性({ads:.0f}): {al}")

        lds = r["leading"]["score"]
        ll = r.get("logs", {}).get("leading", "")
        print(f"    - 📊 领涨性({lds:.0f}): {ll}")

        abs_ = r["absorption"]["score"]
        abl = r.get("logs", {}).get("absorption", "")
        print(f"    - 💰 资金承接({abs_:.0f}): {abl}")

        print(f"    2. 买点建议：")
        print(f"    - xxx 后续迭代")


# ─── 主流程 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="龙头战法批量筛选")
    parser.add_argument("--top", type=int, default=5, help="输出前 N 名（默认5）")
    parser.add_argument("--candidates", type=int, default=20,
                        help="分析候选数（默认10）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--workers", type=int, default=2,
                        help="并行分析进程数（默认2，防风控）")
    args = parser.parse_args()

    t_start = time.time()

    # Step 0: 预加载共享数据
    print("🔍 预加载共享数据...", file=sys.stderr)
    shared_path, limit_up_list = _preload_shared_data()

    # Step 1: 过滤
    stocks = fetch_and_filter(limit_up_list)
    if not stocks:
        print("⚠️ 无符合条件的涨停股", file=sys.stderr)
        sys.exit(1)

    # Step 2: 推算连板 + 排序
    print("📊 推算连板数...", file=sys.stderr)
    stocks = rank_by_consecutive(stocks)

    # 取前 N 候选
    candidates = stocks[:args.candidates]
    if not candidates:
        print("⚠️ 无候选股", file=sys.stderr)
        sys.exit(1)

    print(f"🎯 候选池: {len(candidates)} 只 (连板 {candidates[0].get('est_cons',1)}"
          f"→{candidates[-1].get('est_cons',1)})", file=sys.stderr)

    # Step 3: 并行分析
    print(f"🐉 并行分析 ({len(candidates)} 只, workers={args.workers})...", file=sys.stderr)
    analyzed = run_parallel(candidates, shared_path, max_workers=args.workers)

    # Step 4: 取前 N
    top_n = analyzed[:args.top]
    elapsed = time.time() - t_start
    print(f"\n✅ 完成 ({elapsed:.0f}s)", file=sys.stderr)

    # Step 5: 输出
    if args.json:
        print(json.dumps(top_n, ensure_ascii=False, indent=2, default=str))
    else:
        print_results(top_n)


if __name__ == "__main__":
    main()
