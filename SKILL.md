---
name: leading-stock-analyzer
description: >
  龙头战法量化分析 — 从带动性、抗跌性、领涨性、资金承接性四个维度评估涨停股的龙头质量。
  东方财富公开 API 驱动，无需登录。运行 python3 scripts/main.py 或 analyze.py 获取评分。
  使用后**原样输出终端结果，不添加任何主观评价、交易建议、角色扮演**。
   Trigger phrases: 龙头分析、龙头战法、涨停分析、带动性、抗跌性、领涨性、资金承接、
   这个票是不是龙头、帮我分析这只股票、排查问题、为什么失败、为什么慢、日志分析、
   今天运行情况、怎么看日志。
---

# 龙头战法量化分析

基于东方财富公开 API 的四维评分系统，用于评估涨停股是否具备龙头属性。

## 🚨 绝对规则 — 必须先读

**禁止 agent 加工脚本输出。** 这是此 skill 唯一的硬规则，触犯会导致用户不满意。

规则：
1. 执行脚本后，**原样输出终端结果**，一个字不改
2. 禁止自行总结、转表格、加点评、加 trading advice、角色扮演
3. 禁止省略或截断四维日志任何一行
4. 终端输出本身就是最终答案
5. 如果你觉得需要"加点说明"——**不需要。** 输出原文就好
6. **违规示例（禁止）**：
   - ❌ "根据分析..."、"该股..."、"建议关注..."
   - ❌ 自己写表格替代日志
   - ❌ 只挑"重点"输出
   - ❌ "杨老师点评：..."

## 快速使用

```bash
# 批量筛选（推荐）：自动拉榜→排序→并行分析→Top N
python3 scripts/main.py                     # 默认 top 5，候选 10，2并发
python3 scripts/main.py --top 10            # 输出前 10
python3 scripts/main.py --candidates 20     # 更大候选池
python3 scripts/main.py --top 5 --json      # JSON 格式（供定时任务使用）
python3 scripts/main.py --workers 1         # 串行（风控严格时使用）

# 单票深度分析
python3 scripts/analyze.py 002xxx           # 基础分析
python3 scripts/analyze.py 002xxx -v        # 详细报告
python3 scripts/analyze.py 002xxx --json    # JSON 输出
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
| 🐔 杂毛 | < 50 | 跟风货，远离 |

## 数据来源

全部来自东方财富公开 JSONP 接口（免费，无需登录）：

- `push2.eastmoney.com/api/qt/clist/get` — 涨停榜、行业成分股
- `push2.eastmoney.com/api/qt/stock/get` — 个股实时行情
- `push2his.eastmoney.com/api/qt/stock/kline/get` — 日K线、5分钟K线

详见 [references/api_reference.md](references/api_reference.md)。

## 输出格式（严格模板）

终端输出已内置对齐此模板。不需要 agent 自己排版。

```
======================================================================
  🐉 龙头战法批量筛选 — 最新交易日
======================================================================

<股票名>(<代码>)——<行业>——<N>连板
    1. 综合评分: <分数>，<评级>
    - 🐉 带动性(<分>): <日志原文>
    - 🛡️ 抗跌性(<分>): <日志原文>
    - 📊 领涨性(<分>): <日志原文>
    - 💰 资金承接(<分>): <日志原文>
    2. 买点建议：
    - xxx 后续迭代
```

## 排查问题（日志分析）

系统每次运行自动写入结构化日志到 `./logs/lsa_YYYYMMDD.jsonl`（JSON Lines，每行一条独立 JSON）。agent 排查时优先读日志而非重跑脚本。

### 日志结构速查

| 事件类型 | 含义 | 关键字段 |
|---------|------|---------|
| `session_start` | 运行开始 | `command`, `args`, `pid` |
| `session_end` | 运行结束 | `success`, `failed`, `top_scores`, `total_elapsed_ms`(在顶层) |
| `pipeline_stage` | 流水线阶段 | `stage`(preload/filter/rank/analyze), `elapsed_ms`(在顶层), `candidates`, `success`, `failed` |
| `api_call` | 每次 HTTP 调用 | `name`(url), `elapsed_ms`(在顶层), `ok`, `attempts`, `reason`, `last_http_status`, `last_body_snippet` |
| `subprocess` | 子进程分析 | `code`, `status`(ok/timeout/error/non_zero_rc/json_error), `elapsed_ms`(在顶层), `reason` |
| `dimension_score` | 维度得分 | `code`, `dim`(drive/anti_drop/leading/absorption), `score`, `fallback` |
| `error` | 异常 | `context`, `error_type`, `message`, `stack_summary` |

注：`elapsed_ms` 在顶层而非 `meta` 中；`ok` 也在顶层。

### 常用排查命令

```bash
LOG="./logs/lsa_$(date +%Y%m%d).jsonl"

# 1. 一目了然：今天总体情况
tail -1 "$LOG" | python3 -m json.tool

# 2. 哪些 API 最慢（取 top 5）
grep '"api_call"' "$LOG" | python3 -c "
import sys, json
calls = [json.loads(l) for l in sys.stdin]
for c in sorted(calls, key=lambda x: x['elapsed_ms'], reverse=True)[:5]:
    m = c['meta']
    print(f\"{c['elapsed_ms']:>6}ms  {'OK' if c['ok'] else 'FAIL'}  {m['name'][:80]}\")
"

# 3. 失败的 API 调用及原因
grep '"ok":false' "$LOG" | grep '"api_call"' | python3 -c "
import sys, json
for l in sys.stdin:
    c = json.loads(l)
    m = c['meta']
    print(f\"{m['name'][:80]}\")
    print(f\"  耗时{c['elapsed_ms']}ms  重试{m['attempts']}次  reason={m.get('reason','')[:120]}\")
    if m.get('last_http_status') is not None:
        print(f\"  HTTP {m['last_http_status']}\")
    if m.get('last_body_snippet'):
        print(f\"  body: {m['last_body_snippet'][:100]}\")
"

# 4. 子进程成功率
grep '"subprocess"' "$LOG" | python3 -c "
import sys, json
total, ok, fail = 0, 0, 0
for l in sys.stdin:
    c = json.loads(l)
    total += 1
    if c['ok']: ok += 1
    else: fail += 1
print(f'子进程: {total} 只, 成功 {ok}, 失败 {fail}')
"

# 5. 哪些票的分是 fallback 降级分
grep '"dimension_score"' "$LOG" | python3 -c "
import sys, json
for l in sys.stdin:
    c = json.loads(l)
    m = c['meta']
    if m.get('fallback'):
        print(f\"{m['code']} {m['dim']:12s} score={m['score']:.0f}  reason={m.get('reason','')[:100]}\")
"
```

### 排查流程

1. **用户说"为什么脚本失败了？"** → `tail -1 $LOG` 看 session_end 汇总；再 `grep '"error"' $LOG` 看具体错误
2. **用户说"为什么这么慢？"** → 用命令 2 找慢 API；用命令 5 看是否有大量 fallback（说明 API 取数失败触发了耗时长等待）
3. **用户说"为什么某票分低？"** → `grep 'dimension_score' $LOG | grep '该股票代码'` 逐维度查看
4. **用户说"今天运行情况怎么样？"** → 做命令 1+4 给概览
5. **日志文件不存在** → 说明脚本还没运行过，或已被清理（>7 天）；直接跑一次脚本生成新日志

### 输出规则

排查类问题与普通分析不同：**不需要原样输出**。排查时可以解读日志、提供结论和建议。输出格式自由，以可读为准。

## 注意事项

1. 东方财富 API 为公开接口，不承诺 SLA，高峰期可能超时
2. 板块 5 分钟 K 线加载全量板块时较慢（~10s），建议仅在需要时调用
3. 领涨性分析依赖行业成分股数据，无法获取时使用简化的涨幅偏离度估算
4. 科创板、北交所涨跌幅阈值可能超过 10%，涨停判定已做 9.9% 兜底
