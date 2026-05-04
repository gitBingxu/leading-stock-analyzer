# 龙头战法量化分析

基于东方财富公开 API 的 A 股龙头筛选工具，从四个维度量化评估涨停股的龙头质量。纯 Python 标准库实现，零外部依赖，无需登录。

## 快速开始

```bash
# 批量筛选（推荐）：自动拉榜→排序→并行分析→Top N
python3 scripts/main.py                     # 默认 top 5，候选 10，2 并发
python3 scripts/main.py --top 10            # 输出前 10
python3 scripts/main.py --candidates 20     # 更大候选池
python3 scripts/main.py --top 5 --json      # JSON 格式（定时任务）
python3 scripts/main.py --workers 1         # 串行（风控严格时使用）

# 单票深度分析
python3 scripts/analyze.py 002xxx           # 基础分析
python3 scripts/analyze.py 002xxx -v        # 详细报告
python3 scripts/analyze.py 002xxx --json    # JSON 输出
```

## 四维评分体系

| # | 维度 | 权重 | 衡量什么 |
|---|------|:--:|------|
| 一 | 带动性 | 35% | 封板后同板块小弟跟不跟、跟多紧 |
| 二 | 抗跌性 | 15% | 大盘跳水时扛不扛得住 |
| 三 | 领涨性 | 25% | 平时在同行业里排第几 |
| 四 | 资金承接性 | 25% | 其他板块跳水时资金是否涌入并持续 |

## 评级

| 评级 | 分数 | 含义 |
|------|:--:|------|
| 🐉 真龙 | 85-100 | 四维共振，引领板块 |
| ⭐ 强票 | 70-84 | 某方面突出，可持续跟踪 |
| 📊 中规中矩 | 50-69 | 还行但缺少亮点 |
| 🐔 杂毛 | <50 | 跟风货，回避 |

## 架构

```
main.py (编排器)
│  Step 0: 预加载涨停榜+大盘K线 → /tmp/lsa_YYYYMMDD.json（自动清理3天前）
│  Step 1: 过滤主板+非ST
│  Step 2: 推算连板 → 降序取前 N 候选
│  Step 3: subprocess 并行调 analyze.py --shared-data（默认 2 并发）
│  Step 4: 按综合分排序 → 输出 Top N
│
analyze.py (单票子进程)
  复用共享数据免重复请求 → 四维分析（带动/抗跌/领涨/承接） → JSON
```

`--workers N` 控制并行数：默认 2（防风控），风控严格时设为 1（纯串行）。单票失败不影响其他。

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
    2. 买点建议：
    - xxx 后续迭代
```

## 数据来源

全部来自公开接口（免费，无需登录）：

| 数据 | 主源 | 备用 |
|------|------|------|
| 涨停榜、行业成分股 | 东方财富 `push2.eastmoney.com` | — |
| 个股 / 指数日K线 | 腾讯 `web.ifzq.gtimg.cn` | 东方财富 `push2his.eastmoney.com` |
| 5 分钟 K 线 | 东方财富 `push2his.eastmoney.com` | — |
| 个股实时行情 | 东方财富 `push2.eastmoney.com` | 腾讯 `qt.gtimg.cn` |

详见 `references/api_reference.md`。

## 项目结构

```
scripts/
├── main.py              # 批量筛选入口（subprocess 并行编排）
├── preload.py           # 共享数据预加载（可独立使用）
├── analyze.py           # 单票深度分析
├── eastmoney_api.py     # 东方财富 + 腾讯 API 封装
├── drive_analysis.py    # 带动性分析
├── anti_drop.py         # 抗跌性分析
├── leadership.py        # 领涨性分析
├── absorption.py        # 资金承接性分析
└── log_builder.py       # 四维日志生成
references/
└── api_reference.md     # API 字段说明
SKILL.md                 # AI agent 集成工作流
```

## 注意事项

- API 为公开接口，不承诺 SLA，高峰期可能超时（内置 3 次重试 + 双源备用 + 限速）
- 板块 5 分钟 K 线仅在交易时段可用，非交易日资金承接性维度退化为默认分
- 深圳创业板 / 科创板已自动过滤，关注主板涨停
- AI agent 集成详见 `SKILL.md`
