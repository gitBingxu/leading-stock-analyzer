# 龙头战法量化分析

从当日涨停股中，通过四维量化评分找出真龙头。纯 Python 3 标准库，零配置，下载即用。

## 前提条件

- Python 3.8+
- 无需安装任何依赖（`pip install` / `requirements.txt` 都不需要）
- 无需注册/登录，数据来自东方财富公开接口

```bash
git clone https://github.com/gitBingxu/leading-stock-analyzer.git
cd leading-stock-analyzer
python3 scripts/main.py
```

## 快速开始

### 每日扫榜（推荐）

```bash
python3 scripts/main.py                    # 输出 Top 5，自动拉榜→排序→分析
python3 scripts/main.py --top 10           # 输出 Top 10
python3 scripts/main.py --candidates 30    # 扩大候选池到 30 只
```

### 单票深挖

```bash
python3 scripts/analyze.py 002192          # 分析 002192
python3 scripts/analyze.py 002192 -v       # 详细报告（含买入理由）
```

### 定时任务（cron / 自动化）

```bash
python3 scripts/main.py --top 10 --json    # JSON 输出，适合写入数据库或发消息
python3 scripts/main.py --workers 1        # 串行模式，API 风控友好
```

## 怎么看结果？

每条结果回答四个问题，合起来就是一个龙头画像：

| 维度 | 权重 | 问题 |
|------|:--:|------|
| 🐉 带动性 | 35% | 它一封板，同板块小弟跟不跟？跟得紧不紧？ |
| 🛡️ 抗跌性 | 15% | 大盘跳水的时候它扛不扛得住？ |
| 📊 领涨性 | 25% | 平时它在同行业里排第几？是不是常年的领头羊？ |
| 💰 资金承接 | 25% | 其他板块跳水时，资金是不是涌到它这来？ |

四个分加权合成**综合评分**，对应评级：

| 评级 | 分数 | 一句话 |
|------|:--:|------|
| 🐉 真龙 | 85+ | 四维共振，板块带头大哥 |
| ⭐ 强票 | 70-84 | 某方面突出，值得持续跟踪 |
| 📊 中规中矩 | 50-69 | 还行但缺少亮点 |
| 🐔 杂毛 | <50 | 跟风货 |

## 输出示例

```
======================================================================
  🐉 龙头战法批量筛选 — 最新交易日
======================================================================

融捷股份(002192)——能源金属——3连板
    1. 综合评分: 72.0，强票
    - 🐉 带动性(100): 板块共鸣91/跟风100/决策力75，板块共振强劲
    - 🛡️ 抗跌性(32): 近2次跳水偏弱，警惕系统性风险
    - 📊 领涨性(78): 行业排名前39%，跑赢中位数+2.0%
    - 💰 资金承接(50): 暂无显著跨板块虹吸信号
```

## 参数速查

| 参数 | 默认值 | 说明 |
|------|:--:|------|
| `--top N` | 5 | 输出前 N 名 |
| `--candidates N` | 20 | 从连板前 N 只中筛选，池子越大覆盖越全 |
| `--workers N` | 2 | 并行分析数，设 1 为串行（防风控） |
| `--json` | 否 | 输出 JSON 格式 |
| `-v` / `--verbose` | 否 | （analyze.py）详细报告 |

## 常见问题

**开盘期间跑得很慢甚至失败？**

东方财富公开接口不承诺 SLA，高峰期压力大。系统内置 3 次重试 + 双数据源备用（腾讯/东方财富互备），但极端情况下仍可能超时。建议：
- 非高峰期（如收盘后 1 小时）运行，稳定性更高
- 如必须盘中跑，调小 `--candidates` 和 `--workers 1` 降低并发压力

**怎么看今天跑得怎么样？**

每次运行自动写日志到 `./logs/lsa_YYYYMMDD.jsonl`。快速看总体情况：

```bash
tail -1 ./logs/lsa_$(date +%Y%m%d).jsonl | python3 -m json.tool
```

更多排查命令见下方「日志排查」。

**会过滤哪些股票？**

- 科创板（688xxx）、创业板（300xxx）— 涨跌幅规则不同，自动跳过
- 含 "ST" 的股票 — 风险警示股，自动跳过
- 只分析涨停股，当天没涨停的不在候选池

**数据准确吗？**

涨停榜、K 线、实时行情全部来自东方财富和腾讯公开接口，与行情软件数据源一致。价格、涨跌幅、封板时间均为接口直出，未经篡改。

## 日志排查

系统每次运行自动生成结构化日志（JSON Lines 格式），存放在 `./logs/`，自动清理 7 天前的旧文件。排查问题无需重跑脚本，直接看日志即可。

```bash
LOG="./logs/lsa_$(date +%Y%m%d).jsonl"

# 今天总体：成功/失败数、耗时、Top 分数
tail -1 "$LOG" | python3 -m json.tool

# 哪些 API 最慢？
grep '"api_call"' "$LOG" | python3 -c "
import sys, json
calls = [json.loads(l) for l in sys.stdin]
for c in sorted(calls, key=lambda x: x['elapsed_ms'], reverse=True)[:5]:
    m = c['meta']
    print(f\"{c['elapsed_ms']:>6}ms  {'OK' if c['ok'] else 'FAIL'}  {m['name'][:80]}\")
"

# 哪些票分析失败了？
grep '"subprocess"' "$LOG" | python3 -c "
import sys, json
for l in sys.stdin:
    c = json.loads(l)
    if not c['ok']:
        m = c['meta']
        print(f\"{m['code']}  {m['status']:12s}  {m.get('reason','')[:100]}\")
"
```

## 是什么 / 不是什么

- **是**：一个量化辅助工具，帮你从几十只涨停股里快速锁定值得关注的标的
- **不是**：买卖建议。所有评分仅供参考，不构成投资建议。投资有风险，入市需谨慎
