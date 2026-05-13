# AGENTS.md

A 股龙头战法四维量化筛选工具。基于 [dragon-quant](https://pypi.org/project/dragon-quant/) pip 包，零配置。

## 项目概览

- **目的**：从涨停股中量化识别"真龙头"，评估带动能力（带动板块）、抗跌能力（大盘跳水时表现）、领涨能力（行业排名）、资金承接（跨板块虹吸）
- **数据源**：东方财富 + 雪球 + 腾讯，无需登录
- **入口**：`dragon-quant scan`（CLI）或 `dragon_quant.scan()`（Python API）
- **安装**：`pip install dragon-quant`

## 运行命令

```bash
dragon-quant scan                               # 默认 top 25，候选 5，2 并发
dragon-quant scan --top 10                      # 输出前 10
dragon-quant scan --workers 1                   # 串行模式（防风控）

# 日志查询
dragon-quant logs tail -n 20                    # 最近 20 条日志
dragon-quant logs summary                       # 最新扫描摘要
dragon-quant logs query --code 600172           # 按股票代码查日志
dragon-quant logs clear --days 7                # 清除 7 天前日志

# 数据查询
dragon-quant data sector                        # 板块涨幅榜
dragon-quant data components --sector BK0487    # 板块成分股
dragon-quant data kline --code 600172           # 个股日K线
dragon-quant data quote --code 600172           # 实时行情

# Cookie 管理
dragon-quant data cookie-status                 # 检查 Cookie 状态
dragon-quant data cookie-fetch                  # 刷新全部 Cookie
```

## 架构

```
dragon_quant/
├── __init__.py          # 公共 API 导出（scan, data, logging）
├── cli.py               # CLI 命令（scan/logs/data/storage）
├── orchestrator.py      # 编排器（Phase A→F 全流程）
├── data.py              # 原子数据查询 API
├── providers/           # 数据源适配器
│   ├── base.py          # StockProvider 抽象接口
│   ├── eastmoney.py     # 东方财富
│   ├── xueqiu.py        # 雪球
│   └── tencent.py       # 腾讯
├── scorers/             # 四维评分器
│   ├── drive.py         # 带动性
│   ├── anti_drop.py     # 抗跌性
│   ├── leadership.py    # 领涨性
│   └── absorption.py    # 资金承接
├── cache/               # 内存+本地双缓存
├── logging/             # ScanLogger + ReportBuilder + 查询 API
├── storage/             # 数据目录管理
├── rate_limit.py        # 并发限流器
└── models/types.py      # 数据模型
```

## Programmatic API

### 编排器

```python
import dragon_quant

result = dragon_quant.scan(top_n=5, candidates_n=5, workers=2)
# 返回 dict:
# {
#   "timestamp": "20260513_160000",
#   "elapsed_s": 38.2,
#   "sectors": {"up": [...], "down": [...]},
#   "ranking": [
#     {
#       "code": "600172", "name": "黄河旋风",
#       "concepts": ["培育钻石"], "board_count": 3,
#       "composite_score": 71.8,
#       "dimensions": {
#         "drive": {"score": 99.0, "weight": 0.35, "details": {...}},
#         "anti_drop": {"score": 61.0, "weight": 0.15, "details": {...}},
#         "leadership": {"score": 50.0, "weight": 0.25, "details": {...}},
#         "absorption": {"score": 62.0, "weight": 0.25, "details": {...}},
#       }
#     },
#     ...
#   ],
#   "api_stats": {...},
#   "report_text": "..."
# }
```

### 原子数据查询

```python
from dragon_quant.data import (
    get_sector_ranking, get_sector_components, get_kline,
    get_minute_kline, get_quote, batch_get_quotes,
    cookie_status, fetch_cookies,
)

sectors = get_sector_ranking()                 # 板块涨幅榜
stocks = get_sector_components("BK0487")       # 板块成分股
kline = get_kline("600172", source="xueqiu")   # 个股日K线
mline = get_minute_kline("600172")             # 1分K线
quote = get_quote("600172")                    # 实时行情
quotes = batch_get_quotes(["600172", "000001"]) # 批量行情

status = cookie_status()                       # Cookie 状态
fetch_cookies()                                # 刷新 cookie
```

### 日志查询

```python
from dragon_quant.logging.query import (
    tail_logs, query_logs, clear_logs, list_logs, log_summary,
)

entries = tail_logs(20)                        # 最近 20 条
errors = query_logs(level="error")             # 按级别查
drive = query_logs(category="scorer:drive", code="600172")
summary = log_summary()                        # 扫描摘要
files = list_logs()                            # 列出日志文件
result = clear_logs(days=7)                    # 清理旧日志
```

## 关键权重与阈值

```python
# 综合评分权重
DRIVE_W = 0.35       # 带动性
ANTI_DROP_W = 0.15   # 抗跌性
LEADING_W = 0.25     # 领涨性
ABSORPTION_W = 0.25  # 资金承接性

# 评级阈值
≥85: 🐉 真龙
≥70: ⭐ 强票
≥50: 📊 中规中矩
<50: 🐔 杂毛

# 带动性子维度
板块共鸣(Voice): 30%  — 同板块涨停占比 / 10% * 100
跟风(Follow):   30%  — 非涨停股涨幅>3%占比 / 15% * 100
决策力(Board):  40%  — 排序位次(25%) + 绝对时间(25%) + 跟风间距(50%)，一字板×0.85

# 抗跌性子维度
相对回撤(A): 40%  — 个股超额收益 vs 大盘
日内支撑(B): 30%  — 下影线 + 收盘位置，惩罚最大日内跌幅
反弹弹性(C): 30%  — 次日 alpha = 个股涨幅 - 大盘涨幅

# 资金承接事件检测
滑动窗口 6 根 bar(30min)，同时满足：
- ≥2 个其他板块跌 >1%
- 目标板块涨 >0.3%
- ≥4/6 bar 为阳线
- 回撤 <30% 窗口涨幅

# 过滤规则
排除 30*/68* 开头（双创），排除名称含 ST（大小写不敏感）
```

## 数据源映射

| 数据源 | 用途 | 接口数 |
|--------|------|--------|
| 东方财富 | 板块排行、成分股、板块 5 分 K | 3 |
| 雪球 | 日 K 线、1 分 K 线 | 2 |
| 腾讯 | 实时行情、批量行情 | 2 |

## 代码约定

1. **输出流**：进度/错误 → `sys.stderr`，结果 JSON → `sys.stdout`
2. **错误处理**：所有 HTTP 调用 try/except，失败返回空默认值（`[]`、score `50` 或 `0`），不抛出
3. **速率限制**：`RateLimiter` 按 `(provider, endpoint)` 维度串行，不同 key 并发
4. **Provider 抽象**：所有数据源实现 `StockProvider` 接口，评分器只依赖接口
5. **懒加载**：Provider 单例延迟初始化，模块 import 不触发网络请求
6. **结构化日志**：`ScanLogger` 全链路打点，每次扫描自动保存 JSONL + JSON + 文本报告
7. **结果持久化**：写入 `~/Library/Application Support/dragon-quant/`，保留最新快照

## 已知坑点

1. **非交易时段**：5-min K 线为空时，资金承接性直接返回 50 分，需检查是否有数据
2. **大盘跳水判定**：`anti_drop` 阈值为 `market_pct < -0.7%`，太宽容会导致误判太多"跳水日"
3. **雪球 cookie 过期**：约 25 天过期，过期后自动回退。通过 `dragon-quant data cookie-status` 检查
4. **东财 push2his K 线全线封禁**：5 分钟 K 线已改为雪球优先，日 K 线腾讯优先+东财兜底
5. **板块 5 分钟 K 线合成**：通过成分股 Top 3 等权平均生成，不再依赖东财板块指数 API
6. **K 线日期顺序**：日 K 线按时间正序排列（`[0]` 最早），连板推算从末尾 `[-1]` 往回走
7. **缓存位置**：日志和结果存储在 `~/Library/Application Support/dragon-quant/`
8. **提交信息**用中文，Conventional Commits 前缀（`feat:`/`fix:`/`docs:`/`refactor:`）
