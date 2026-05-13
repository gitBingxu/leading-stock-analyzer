---
name: leading-stock-analyzer
description: >
  龙头战法量化分析 — 从带动性、抗跌性、领涨性、资金承接性四个维度评估涨停股的龙头质量。
  基于 dragon-quant pip 包（东方财富 + 雪球 + 腾讯公开 API），无需登录。
  使用后**原样输出终端结果，不添加任何主观评价、交易建议、角色扮演**。
  Trigger phrases: 龙头分析、龙头战法、涨停分析、带动性、抗跌性、领涨性、资金承接、
  这个票是不是龙头、帮我分析这只股票、排查问题、为什么失败、为什么慢、日志分析、
  今天运行情况、怎么看日志、板块热度、龙头排行、top龙头。
---

# 龙头战法量化分析

基于 [dragon-quant](https://pypi.org/project/dragon-quant/) 的四维评分系统，用于评估涨停股是否具备龙头属性。

## 🚨 绝对规则 — 必须先读

**禁止 agent 加工 scan 输出。** 这是此 skill 唯一的硬规则。

规则：
1. 执行 `dragon-quant scan` 后，**原样输出终端结果**，一个字不改
2. 禁止自行总结、转表格、加点评、加 trading advice、角色扮演
3. `dragon-quant scan` 输出的 `report_text` 本身就是最终答案
4. 如果你觉得需要"加点说明" —— **不需要。** 输出原文就好
5. **违规示例（禁止）**：
   - ❌ "根据分析..."、"该股..."、"建议关注..."
   - ❌ 自己写表格替代 scan 输出
   - ❌ 只挑"重点"输出
   - ❌ "杨老师点评：..."

## 安装

```bash
pip install "dragon-quant>=0.1.2"
```

## 快速使用

### 每日扫榜（推荐）

```bash
dragon-quant scan                     # 默认 top 25
dragon-quant scan --top 10            # 输出前 10
dragon-quant scan --top 5 --workers 1 # 串行模式，防风控
```

### 日志查询

```bash
dragon-quant logs summary                       # 最新扫描摘要
dragon-quant logs tail -n 20                    # 最近 20 条日志
dragon-quant logs query --code 600172           # 按股票代码查评分日志
dragon-quant logs query --level error            # 只看错误
dragon-quant logs query --category scorer:drive --code 600172  # 带动性评分细节
dragon-quant logs clear --days 7                # 清理旧日志
```

### 数据查询

```bash
dragon-quant data sector                        # 板块涨幅榜
dragon-quant data components --sector BK0487    # 板块成分股
dragon-quant data kline --code 600172 --days 30 # 个股日K线
dragon-quant data quote --code 600172           # 实时行情
dragon-quant data batch-quote --codes 600172,000001  # 批量行情
dragon-quant data minute --code 600172          # 1分钟K线
```

### Cookie 管理

```bash
dragon-quant data cookie-status                 # 查看 Cookie 状态（东财/雪球）
dragon-quant data cookie-fetch                  # 刷新全部 Cookie
dragon-quant data cookie-fetch --source xueqiu  # 只刷新雪球
```

## 四个维度

| # | 维度 | 权重 | 核心问题 |
|---|---|---|---|
| 一 | 带动性 | 35% | 封板后小弟跟不跟？跟多紧？ |
| 二 | 抗跌性 | 15% | 大盘跳水时扛不扛得住？ |
| 三 | 领涨性 | 25% | 平时在同行业排第几？ |
| 四 | 资金承接性 | 25% | 别板块跳水时资金是否涌入并持续到收盘？ |

## 评级

| 评级 | 分数 | 含义 |
|---|---|---|
| 🐉 真龙 | 85-100 | 四维共振，引领板块 |
| ⭐ 强票 | 70-84 | 某方面突出，可持续跟踪 |
| 📊 中规中矩 | 50-69 | 还行但缺少亮点 |
| 🐔 杂毛 | < 50 | 跟风货 |

## 数据来源

全部来自公开 API（免费，无需登录）：

| 数据源 | 用途 | 接口数 |
|--------|------|--------|
| 东方财富 | 板块排行、成分股、板块 5 分 K | 3 |
| 雪球 | 日 K 线、1 分 K 线 | 2 |
| 腾讯 | 实时行情、批量行情 | 2 |

## 输出格式

`dragon-quant scan` 输出包含板块涨跌排行、Top N 候选股四维评分表格、自然语言详细报告，以及 `report_text` 字段。**Agent 原样输出即可。**

## Agent 集成指南 — 常见场景

### 场景 1：今日龙头扫榜 + 输出报告

```python
import dragon_quant

result = dragon_quant.scan(top_n=5, candidates_n=5, workers=2)

print(f"🐉 今日龙头 TOP5 | 耗时 {result['elapsed_s']}s")
print()
print(f"{'排名':4s} {'代码':8s} {'名称':8s} {'综合':>6s} {'带动':>6s} {'抗跌':>6s} {'领涨':>6s} {'承接':>6s}")
print("-" * 56)
for i, r in enumerate(result["ranking"], 1):
    dims = r.get("dimensions", {})
    print(f"{i:4d} {r['code']:8s} {r['name']:8s} "
          f"{r['composite_score']:6.1f}  "
          f"{dims.get('drive',{}).get('score',0):6.1f}  "
          f"{dims.get('anti_drop',{}).get('score',0):6.1f}  "
          f"{dims.get('leadership',{}).get('score',0):6.1f}  "
          f"{dims.get('absorption',{}).get('score',0):6.1f}")

print()
print(result["report_text"])
```

### 场景 2：只取排行数据，不打印（Agent 内部消费）

```python
import dragon_quant

result = dragon_quant.scan(top_n=10)

for r in result["ranking"]:
    code = r["code"]
    name = r["name"]
    score = r["composite_score"]
    concepts = r.get("concepts", [])
    boards = r.get("board_count", 0)
    if score >= 80:
        grade = "🐲 龙头"
    elif score >= 65:
        grade = "🔥 强票"
    else:
        grade = "📊 一般"
    print(f"{grade} {code} {name} | {boards}连板 | {', '.join(concepts)} | 综合{score}")
```

### 场景 3：查某只股票的 K 线和实时行情

```python
from dragon_quant.data import get_kline, get_minute_kline, get_quote

code = "600172"

kline = get_kline(code, days=30)
print(f"{code} 最近 30 日 K 线:")
for k in kline[-5:]:
    print(f"  {getattr(k, 'time', '?')} | "
          f"开{getattr(k, 'open', 0):.2f} 收{getattr(k, 'close', 0):.2f} "
          f"涨{getattr(k, 'pct', 0):.2f}%")

quote = get_quote(code)
if quote:
    print(f"当前价: {quote.price} | 涨跌幅: {quote.pct}% | 换手率: {getattr(quote, 'turnover', 0):.2f}%")
```

### 场景 4：scan 返回空数据/报错 → 刷新 Cookie

```python
from dragon_quant.data import cookie_status, fetch_cookies
import dragon_quant

status = cookie_status()
for source, info in status.items():
    print(f"{source}: {'✅ 有效' if info['ok'] else '❌ 过期'} ({info['length']}字符)")

if not status["eastmoney"]["ok"] or not status["xueqiu"]["ok"]:
    print("Cookie 过期，正在刷新...")
    fetch_cookies()
    new_status = cookie_status()
    for source, info in new_status.items():
        print(f"  {source}: {'✅' if info['ok'] else '❌'} ({info['length']}字符)")

result = dragon_quant.scan(top_n=5)
print(f"扫描成功，{len(result['ranking'])} 只候选")
```

### 场景 5：查板块热度（哪个方向最强）

```python
from dragon_quant.data import get_sector_ranking, get_sector_components

sectors = get_sector_ranking(asc=False)[:5]
print("今日最强板块:")
for s in sectors:
    print(f"  {s.name} ({s.code}) | +{s.pct:.2f}%")

if sectors:
    stocks = get_sector_components(sectors[0].code)
    up_limit = [s for s in stocks if s.pct and s.pct >= 9.9]
    print(f"\n{sectors[0].name} 涨停股 ({len(up_limit)} 只):")
    for s in up_limit:
        print(f"  {s.code} {s.name} | +{s.pct:.2f}%")
```

### 场景 6：排查问题 — 查看扫描日志

```python
from dragon_quant.logging.query import list_logs, tail_logs, query_logs, log_summary

files = list_logs()
print(f"共 {len(files)} 个日志文件")

summary = log_summary()
print(f"\n最新扫描: {summary['file']}")
print(f"  阶段: {list(summary['phases'].keys())}")
print(f"  API 调用: {summary['api_stats']['total']} 次 | 成功 {summary['api_stats']['ok']} | 失败 {summary['api_stats']['error']}")
print(f"  评分: {summary['scorer_count']} 次")
print(f"  错误: {summary['error_count']} 条")

if summary['error_count'] > 0:
    errors = query_logs(level="error", tail=10)
    print(f"\n最近 10 条错误:")
    for e in errors:
        print(f"  [{e.get('category', '')}] {e.get('message', '')}")

entries = query_logs(category="scorer", code="600172")
for e in entries:
    print(f"  {e['category']} → score={e.get('data',{}).get('score',0)}")
```

### 场景 7：清理日志

```python
from dragon_quant.logging.query import clear_logs, list_logs

before = list_logs()
print(f"清理前: {len(before)} 个日志文件")

result = clear_logs(days=3)
print(f"删除了 {result['cleared']} 个文件 | 保留 {result['kept']} 个")
```

### 场景 8：拿上一次扫描结果（无需重新跑）

```python
import json
from pathlib import Path

latest_path = Path.home() / "Library" / "Application Support" / "dragon-quant" / "results" / "latest.json"

if latest_path.exists():
    with open(latest_path) as f:
        data = json.load(f)
    print(f"上次扫描: {data['timestamp']} | 耗时 {data['elapsed_s']}s")
    for r in data["ranking"]:
        print(f"  {r['code']} {r['name']} — {r['composite_score']}分 — {r.get('board_count', 0)}连板")
else:
    print("暂无扫描缓存，运行一次 scan() 即可生成")
```

### 场景 9：批量获取多只票的行情对比

```python
from dragon_quant.data import batch_get_quotes

codes = ["600172", "605589", "603052", "603203", "603126"]
quotes = batch_get_quotes(codes)

print(f"{'代码':8s} {'价格':>8s} {'涨跌幅':>8s} {'换手率':>8s} {'量比':>6s}")
print("-" * 44)
for q in quotes:
    if q:
        price = getattr(q, 'price', 0)
        pct = getattr(q, 'pct', 0)
        turnover = getattr(q, 'turnover', 0)
        volume_ratio = getattr(q, 'volume_ratio', 0)
        print(f"{q.code:8s} {price:8.2f} {pct:+7.2f}% {turnover:7.2f}% {volume_ratio:6.2f}")
```

## 排查流程

### 用 Python API 排查（推荐）

1. **用户说"为什么失败了？"** → `log_summary()` 看总体；`query_logs(level="error")` 看具体错误
2. **用户说"为什么这么慢？"** → `log_summary()` 看 phase 耗时；`query_logs(category="api_call")` 找慢 API
3. **用户说"为什么某票分低？"** → `query_logs(category="scorer", code="600xxx")` 逐维度查看
4. **用户说"今天运行情况怎么样？"** → `log_summary()` 给概览
5. **日志不存在** → 说明还没运行过 scan，直接跑一次生成新日志

### 用 CLI 排查

```bash
dragon-quant logs summary                                    # 总体情况
dragon-quant logs query --level error --tail 10              # 最近 10 条错误
dragon-quant logs query --category scorer --code 600172      # 某票评分细节
dragon-quant logs query --category api_call                   # 全部 API 调用记录
```

### 排查输出规则

排查类问题与普通分析不同：**不需要原样输出**。排查时可以解读日志、提供结论和建议。输出格式自由，以可读为准。

## 注意事项

1. 数据来自东方财富、雪球、腾讯公开接口，不承诺 SLA，高峰期可能超时
2. 非交易时段 5-min K 线为空，资金承接性直接返回 50 分
3. 东财 push2his K 线 API 已全线封禁，5 分钟 K 线已改为雪球优先
4. 板块 5 分钟 K 线通过成分股 Top 3 等权平均合成
5. 科创板（688/300 开头）、ST 股自动过滤
6. 日志和结果存储在 `~/Library/Application Support/dragon-quant/`

## Cookie 管理

雪球 API 需要浏览器 cookie，过期后自动回退到其他数据源。

### Agent 处理流程

1. 先检查状态：`dragon-quant data cookie-status` 或 `from dragon_quant.data import cookie_status`
2. 如果过期，执行 `dragon-quant data cookie-fetch` 自动刷新
3. 如果自动刷新失败，告知用户手动从浏览器复制 cookie

### Cookie 提取方法（给用户看）

1. 浏览器打开 https://xueqiu.com 并登录
2. F12 → Application → Cookies → 复制 `xq_a_token` 和 `xq_id_token`
3. 运行 `dragon-quant data cookie-fetch --source xueqiu` 自动处理
