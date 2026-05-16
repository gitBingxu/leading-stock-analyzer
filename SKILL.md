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
1. 用户要求扫榜/找龙头时，**只执行 CLI**：`dragon-quant scan [--top N]`
2. CLI 输出什么，agent 就原样贴什么，**一个字不改**
3. 禁止用 Python API 自己组装/排版 scan 结果再输出 — 那等于自己写表格替代 scan 输出
4. `dragon-quant scan` 的终端输出本身就是最终答案
5. 如果你觉得需要"加点说明" —— **不需要。** 输出原文就好
6. **违规示例（禁止）**：
   - ❌ 用 `dragon_quant.scan()` Python API 后自己打印/排版
   - ❌ "根据分析..."、"该股..."、"建议关注..."
   - ❌ 自己写表格替代 scan 输出
   - ❌ 只挑"重点"输出
   - ❌ "杨老师点评：..."

**一句话规则：scan 用 CLI，结果原样贴。Python API 只用于排查/数据查询，不用于输出 scan 结果。**

## 安装

```bash
pip install "dragon-quant>=0.1.5"
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

`dragon-quant scan` 执行后会保存三份文件：
- 日志：`~/Library/Application\ Support/dragon-quant/logs/scan_YYYYMMDD_HHMMSS.jsonl`
- 结果 JSON：`~/Library/Application\ Support/dragon-quant/results/scan_results_YYYYMMDD_HHMMSS.json`
- **可读报告**：`~/Library/Application Support/dragon-quant/results/scan_report_YYYYMMDD_HHMMSS.txt`

**Agent 输出规则：**
1. 跑完 scan 后，读取 `.txt` 报告文件，**原样贴出全文**，一个字不改
2. 贴出的内容包含表格（`----` 分隔线）和详细报告，不省略任何行
3. 贴完即止，不加前后文

## Agent 集成指南 — 渲染报告图片（优先于纯文本输出）

> **重要：** scan 完成后，除了输出终端文本，**必须额外生成一张可视化报告图片**。

### 图片渲染流程（Agent 自动完成，无需用户操作）

1. 跑完 `dragon-quant scan` 后，CLI 会打印结果文件路径（类似 `📊 结果已保存: .../scan_results_YYYYMMDD_HHMMSS.json`）
2. Agent 运行 LLM 渲染脚本（支持任意 OpenAI 兼容 API，OpenClaw 已内置 Key）：

```bash
cd ~/.openclaw/workspace/skills/leading-stock-analyzer && python3 llm_render.py
```

3. 脚本调用 LLM 根据原始数据生成自然语言文案，再渲染为图片，在桌面生成 `龙头日报_LLM_YYYYMMDD.png`
4. Agent **在回复中原样贴出 scan 终端输出的同时**，最后附加图片

### 依赖检查

如果 Pillow 或 requests 未安装，先安装：

```bash
pip3 install Pillow requests
```

### 渲染效果

生成一张深色主题的高清 PNG（3x 分辨率），包含：
- 标题栏：龙头战法日报 + 日期 + 四维颜色图例
- 顶部表格：Top 5 四维评分排名（带动性/抗跌性/领涨性/资金承接/综合分）
- 下方卡片：每只股票的标题（名称+代码+概念+连板+评分） + 四维进度条 + LLM 生成的6行自然语言分析文案
- 底部脚注：扫描板块数、API 请求统计、耗时

### 重点说明

- 渲染脚本不依赖特定模型，支持 OpenAI / DeepSeek / OpenRouter / Ollama 等任意 OpenAI 兼容 API
- 通过环境变量 `LLM_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` 配置 Key，`LLM_BASE_URL` + `LLM_MODEL` 覆盖默认值
- 也支持 `--offline` 离线模式：生成 prompt 文件，由 agent 填好文案后再渲染

## Agent 集成指南 — 常见场景

> ⚠️ scan 类场景禁止用 Python API 输出，必须用 CLI。Python API 只用于**内部数据消费**和**排查**。

### 场景 1：输出上次扫描结果（不重新跑）

```python
import json
from pathlib import Path

latest_path = Path.home() / "Library" / "Application Support" / "dragon-quant" / "results" / "latest.json"

if latest_path.exists():
    data = json.load(latest_path)
    print(f"上次扫描: {data['timestamp']} | 耗时 {data['elapsed_s']}s")
else:
    print("暂无缓存")
```

### 场景 2：查某只股票的 K 线和实时行情

```python
from dragon_quant.data import get_kline, get_minute_kline, get_quote

code = "600172"

kline = get_kline(code, days=30)
print(f"{code} 最近 30 日 K 线:")
for k in kline[-5:]:
    print(f"  {getattr(k, 'timestamp', '?')} | "
          f"开{getattr(k, 'open', 0):.2f} 收{getattr(k, 'close', 0):.2f} "
          f"涨{getattr(k, 'pct', 0):.2f}%")

quote = get_quote(code)
if quote:
    print(f"当前价: {quote.price} | 涨跌幅: {quote.pct}% | 换手率: {getattr(quote, 'turnover_rate', 0):.2f}%")
```

### 场景 3：scan 返回空数据或报错 → 刷新 Cookie

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

### 场景 4：查板块热度（哪个方向最强）

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

### 场景 5：排查问题 — 查看扫描日志

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

### 场景 6：清理日志

```python
from dragon_quant.logging.query import clear_logs, list_logs

before = list_logs()
print(f"清理前: {len(before)} 个日志文件")

result = clear_logs(days=3)
print(f"删除了 {result['cleared']} 个文件 | 保留 {result['kept']} 个")
```

### 场景 7：批量获取多只票的行情对比

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
        turnover = getattr(q, 'turnover_rate', 0)
        volume_ratio = getattr(q, 'volume_ratio', 0)
        print(f"{q.code:8s} {price:8.2f} {pct:+7.2f}% {turnover:7.2f}% {volume_ratio:6.2f}")
```

## 排查流程

### 日志查询

```bash
dragon-quant logs summary                                    # 总体情况
dragon-quant logs query --level error --tail 10              # 最近 10 条错误
dragon-quant logs query --category scorer --code 600172      # 某票评分细节
dragon-quant logs query --category api_call                   # 全部 API 调用记录
```

### 排查输出规则

排查类问题与普通分析不同：**不需要原样输出**。排查时可以解读日志、提供结论和建议。输出格式自由，以可读为准。

### 容错重试流程

scan 跑完后，如果报告显示错误数 > 0，按以下流程处理：

1. **先查错误类型**：`dragon-quant logs query --level error --tail 10`

2. **如果错误是 `Remote end closed connection without response`**（东财拒绝连接）：
   - 原因：东财 cookie 过期，请求被拒
   - **修复流程**：
     a. 刷新 cookie（东财和雪球同时刷新）：`dragon-quant data cookie-fetch`
     b. 如果 refresh 没有真正更新 cookie（文件时间戳没变），说明 refresh 接口失效，告知用户手动从浏览器复制 cookie
     c. 刷新后重新跑 scan
     d. 如果还是失败，加 `--workers 1` 串行模式再试

3. **如果错误是雪球相关的 cookie 类错误**（如 401、验证码、空响应）：
   - 运行 `dragon-quant data cookie-status` 检查 cookie 状态
   - 如果过期，运行 `dragon-quant data cookie-fetch` 刷新
   - 刷新后重新跑 scan

4. **如果错误是超时/超时重试耗尽**：
   - 非交易时段（非 9:30-15:00）数据源不稳定，结果仅供参考
   - 交易时段的话，等几分钟后重试即可

## 注意事项

1. 数据来自东方财富、雪球、腾讯公开接口，不承诺 SLA，高峰期可能超时
2. 非交易时段 5-min K 线为空，资金承接性直接返回 50 分
3. 东财 push2his K 线 API 已全线封禁，5 分钟 K 线已改为雪球优先
4. 板块 5 分钟 K 线通过成分股 Top 3 等权平均合成
5. 科创板（688/300 开头）、ST 股自动过滤
6. 日志和结果存储在 `~/Library/Application Support/dragon-quant/`

## Cookie 管理

东财和雪球都需要浏览器 cookie 才能访问，`cookie-fetch` 会同时刷新两者的 cookie。

### Agent 处理流程

1. 先检查状态：`dragon-quant data cookie-status`
2. 如果过期，执行 `dragon-quant data cookie-fetch` 自动刷新（东财 + 雪球同时刷新）
3. 刷新后检查 cookie 文件时间戳是否更新：`ls -la ~/Library/Application\ Support/dragon-quant/cookies/`
4. 如果文件时间戳没变，说明自动刷新失效，告知用户手动处理

### Cookie 提取方法（给用户看）

1. 浏览器打开 https://xueqiu.com 并登录
2. F12 → Application → Cookies → 复制 `xq_a_token` 和 `xq_id_token`
3. 运行 `dragon-quant data cookie-fetch --source xueqiu` 自动处理
