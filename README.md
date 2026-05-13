# 龙头战法量化分析

从当日涨停股中，通过四维量化评分找出真龙头。基于 [dragon-quant](https://pypi.org/project/dragon-quant/) pip 包。

## 前提条件

- Python 3.8+
- 安装：`pip install dragon-quant`
- 无需注册/登录，数据来自东方财富、雪球、腾讯公开接口
- **推荐** 配置雪球 Cookie 以获得最佳效果：`dragon-quant data cookie-fetch`

## 快速开始

### 每日扫榜（推荐）

```bash
dragon-quant scan                     # 输出 Top 25
dragon-quant scan --top 10            # 输出 Top 10
dragon-quant scan --top 5 --workers 1 # 串行模式，低风控
```

### 数据查询

```bash
dragon-quant data sector                          # 板块涨幅榜
dragon-quant data components --sector BK0487      # 板块成分股
dragon-quant data kline --code 600172 --days 30   # 个股日K线
dragon-quant data quote --code 600172             # 实时行情
dragon-quant data batch-quote --codes 600172,000001,002409  # 批量行情
```

### Cookie 管理

```bash
dragon-quant data cookie-status      # 查看状态
dragon-quant data cookie-fetch       # 刷新全部 Cookie
dragon-quant data cookie-fetch --source xueqiu  # 只刷新雪球
```

### 定时任务（cron / 自动化）

```bash
dragon-quant scan --top 10           # JSON 输出，适合写入数据库或发消息
dragon-quant scan --workers 1        # 串行模式，API 风控友好
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

## 参数速查

| 参数 | 默认值 | 说明 |
|------|:--:|------|
| `--top N` | 25 | 输出前 N 名 |
| `--candidates N` | 5 | 每个板块取前 N 只 |
| `--workers N` | 2 | 并行分析数，设 1 为串行（防风控） |

## 常见问题

**怎么看今天跑得怎么样？**

```bash
dragon-quant logs summary     # 一目了然
dragon-quant logs tail -n 20  # 最近 20 条日志
```

**会过滤哪些股票？**

- 科创板（688xxx）、创业板（300xxx）— 涨跌幅规则不同，自动跳过
- 含 "ST" 的股票 — 风险警示股，自动跳过

**资金承接性为什么总是 50 分？**

说明近期未检测到"其他板块跳水 + 本板块拉升"的跨板块虹吸事件，或 5 分钟 K 线数据源暂时不可用。配置雪球 cookie 可提升数据稳定性。

**数据准确吗？**

涨停榜、K 线、实时行情全部来自公开接口（东方财富、雪球、腾讯），与行情软件数据源一致。

## 日志排查

系统每次运行自动生成结构化日志，存放在 `~/Library/Application Support/dragon-quant/`。

```bash
dragon-quant logs summary                    # 扫描摘要：API 统计、错误数
dragon-quant logs tail -n 50                 # 最近 50 条日志
dragon-quant logs query --code 600172        # 某只股票的评分细节
dragon-quant logs query --level error        # 只看错误
dragon-quant logs query --category scorer:drive --code 600172  # 带动性评分细节
dragon-quant logs clear --days 7             # 清理 7 天前日志
```

## 是什么 / 不是什么

- **是**：一个量化辅助工具，帮你从几十只涨停股里快速锁定值得关注的标的
- **不是**：买卖建议。所有评分仅供参考，不构成投资建议。投资有风险，入市需谨慎
