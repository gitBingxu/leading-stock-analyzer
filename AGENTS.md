# AGENTS.md

A 股龙头战法四维量化筛选工具。纯 Python 3 标准库，零外部依赖。

## 项目概览

- **目的**：从涨停股中量化识别"真龙头"，评估能力（带动板块）、抗跌能力（大盘跳水时表现）、领涨能力（行业排名）、资金承接（跨板块虹吸）
- **数据源**：雪球（优先）+ 新浪财经（兜底）+ 东方财富（辅助）+ 腾讯（日K线），无需登录。东财 push2his K 线 API 已封禁
- **入口**：`python3 scripts/main.py`（批量筛选）、`python3 scripts/analyze.py <code>`（单票分析）
- **无测试/无 lint/无 build**：直接 `python3` 运行即可

## 运行命令

```bash
python3 scripts/main.py                     # 默认 top 5，候选 20，2 并发
python3 scripts/main.py --top 10 --json     # JSON 输出前 10
python3 scripts/main.py --workers 1         # 串行模式（防风控）
python3 scripts/analyze.py 002192           # 单票分析
python3 scripts/analyze.py 002192 -v -j     # 详细 + JSON
python3 scripts/preload.py                  # 独立预加载共享数据到 /tmp
```

## 架构

```
main.py (编排器)
 ├─ Step 0: preload 共享数据 → /tmp/lsa_YYYYMMDD.json（自动清理 >3 天旧文件）
 ├─ Step 1: 过滤 30*/68* 开头股 + ST 股
 ├─ Step 2: 推算连板数 → 按连板降序取前 --candidates 只
 ├─ Step 3: subprocess.run(analyze.py --shared-data) 并行分析（ThreadPoolExecutor）
 └─ Step 4: 按 composite_score 排序 → 输出 Top N

analyze.py (单票子进程, 60s 超时)
 ├─ 复用共享数据（验证 10 分钟内有效），失效时回退实时抓取
 ├─ 四维评分：带动性(35%)+抗跌性(15%)+领涨性(25%)+资金承接(25%)
 ├─ 加载 5-min K 线（个股+板块+同伴股）用于日志
 └─ 输出 JSON 到 stdout（terminal 模式时有格式化报告）
```

## 关键文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `scripts/eastmoney_api.py` | 781+ | 所有 HTTP 调用：涨停榜、K 线、行情、成分股。5-min K 线多源 fallback（雪球→新浪→东财） |
| `scripts/xueqiu_api.py` | ~180 | 雪球 API 客户端：5 分钟 K 线、日 K 线、cookie 管理、数据归一化 |
| `scripts/xq_cookie_refresh.py` | ~100 | Cookie 刷新工具：手动/Playwright/状态检查 |
| `scripts/main.py` | 296 | 批量筛选编排、subprocess 并行调度 |
| `scripts/analyze.py` | 443 | 单票四维分析、综合评分、结果打印 |
| `scripts/drive_analysis.py` | 173 | 维度一：带动性（板块共鸣/跟风/封板决策力） |
| `scripts/anti_drop.py` | 204 | 维度二：抗跌性（跳水日超额收益/日内支撑/反弹弹性） |
| `scripts/leadership.py` | 133 | 维度三：领涨性（行业排名 + 历史估计排名） |
| `scripts/absorption.py` | 146 | 维度四：资金承接性（跨板块虹吸事件检测） |
| `scripts/log_builder.py` | 273 | 四维日志文本生成 |
| `scripts/persist_logger.py` | ~150 | JSON Lines 持久化打点（每日滚动、线程安全、写入失败静默降级） |
| `scripts/preload.py` | ~50 | 共享数据预加载，输出 JSON 路径到 stdout |
| `references/api_reference.md` | — | 东方财富 API 字段文档 |

## eastmoney_api.py 核心函数

| 函数 | 行号 | 签名 | 说明 |
|------|------|------|------|
| `_fetch` | 19 | `(url, max_retries=3) -> dict` | 统一 HTTP GET，自动去 JSONP 包装、3 次重试（0.5s/1.0s/1.5s）、检查 rc 错误码。**每次调用自动记录到 `_API_CALL_LOG`** |
| `get_api_calls_and_clear` | 22 | `() -> list[dict]` | 获取并清空本进程的 API 调用记录。每次记录含 `{url, elapsed_ms, ok, attempts, reason, last_http_status, last_body_snippet}` |
| `get_limit_up_list` | 47 | `(date=None) -> list[dict]` | 涨停榜，返回 `[{code, name, pct, date, board_time, consecutive, industry_name, industry_code, turnover, amount}]` |
| `infer_consecutive_boards` | 125 | `(code, kline) -> int` | 从 K 线推算连板数，阈值主板 9.5%、双创 19.9% |
| `get_industry_components` | 309 | `(industry_code_or_name) -> list[dict]` | 行业成分股列表，自动补全 BK 前缀 |
| `get_stock_kline` | 355 | `(code, days=20) -> list[dict]` | 日 K 线，腾讯优先 → 东方财富备用 |
| `get_stock_quote` | 479 | `(code) -> dict` | 实时行情，东方财富优先 → 腾讯备用。价格需 /100 |
| `get_sector_5min_kline` | 557 | `(industry_code, bars=48) -> list[dict]` | 板块 5 分钟 K 线 |
| `get_stock_5min_kline` | 600 | `(code, bars=48) -> list[dict]` | 个股 5 分钟 K 线 |
| `get_market_index_kline` | 713 | `(index_code="1.000001", days=20) -> list[dict]` | 大盘指数日 K 线 |
| `get_all_active_sector_5min` | 658 | `() -> dict[str, list[dict]]` | 50+ 活跃板块 5-min K 线批量加载 |
| `get_stock_concept_map` | 243 | `(limit_up_list, candidate_codes) -> dict` | 将涨停股映射到概念板块 |

## 关键权重与阈值

```python
# 综合评分权重 (analyze.py:267-270)
DRIVE_W = 0.35       # 带动性
ANTI_DROP_W = 0.15   # 抗跌性
LEADING_W = 0.25     # 领涨性
ABSORPTION_W = 0.25  # 资金承接性

# 评级阈值 (analyze.py:274-280)
≥85: 🐉 真龙
≥70: ⭐ 强票
≥50: 📊 中规中矩
<50: 🐔 杂毛

# 带动性子维度 (drive_analysis.py)
板块共鸣(Voice): 30%  — 同板块涨停占比 / 10% * 100
跟风(Follow):   30%  — 非涨停股涨幅>3%占比 / 15% * 100
决策力(Board):  40%  — 排序位次(25%) + 绝对时间(25%) + 跟风间距(50%)，一字板×0.85

# 抗跌性子维度 (anti_drop.py)
相对回撤(A): 40%  — 个股超额收益 vs 大盘
日内支撑(B): 30%  — 下影线 + 收盘位置，惩罚最大日内跌幅
反弹弹性(C): 30%  — 次日 alpha = 个股涨幅 - 大盘涨幅

# 资金承接事件检测 (absorption.py:66-117)
滑动窗口 6 根 bar(30min)，同时满足：
- ≥2 个其他板块跌 >1%
- 目标板块涨 >0.3%
- ≥4/6 bar 为阳线
- 回撤 <30% 窗口涨幅

# 连板推算 (eastmoney_api.py:130)
主板 9.5%，双创 19.9%

# 过滤规则
排除 30*/68* 开头（双创），排除名称含 ST（大小写不敏感）
```

## 代码约定

1. **输出流**：进度/错误 → `sys.stderr`，结果 JSON → `sys.stdout`
2. **错误处理**：所有 HTTP 调用 try/except，失败返回空默认值（`[]`、score `50` 或 `0`），不抛出
3. **速率限制**：API 调用间 sleep 0.05-0.3s，subprocess 间 0.3s 间隔
4. **私有函数** `_` 前缀，模块顶部有中文 docstring，分隔线 `# ───`
5. **API 双源策略**：K 线用腾讯（更稳），行情用东方财富（更全），互相 fallback
6. **东方财富价格整数**：所有来自 Eastmoney 的价格字段需 `/100`
7. **JSONP 去包装**：`_fetch()` 内 `re.search(r"\{.*\}", raw, re.DOTALL)` 提取纯 JSON
8. **全局延迟加载**：行业映射 `_INDUSTRY_NAME_TO_CODE`、概念映射 `_CONCEPT_CODE_TO_NAME` 首次调用时自动加载
9. **三字股名去空格**：东方财富会在线名中间加空格（如 `贵 州 茅 台`→`贵州茅台`），`_clean_name()` 处理
10. **提交信息**用中文，Conventional Commits 前缀（`feat:`/`fix:`/`docs:`/`refactor:`）

## 已知坑点

1. **连板 off-by-one**：最近一次修复在 `eastmoney_api.py:132`。`cons` 初始化为 1（已计最近一天），循环必须从 `len(kline)-2`（倒数第二天）开始，而非 `len(kline)-1`，否则最近一天重复计数
2. **非交易时段**：5-min K 线为空时，资金承接性直接返回 50 分（`absorption.py:31-42`），需检查是否有数据
3. **大盘跳水判定**：`anti_drop.py:27` 阈值为 `market_pct < -0.7%`，太宽容会导致误判太多"跳水日"。如大盘连续小跌但均 <0.7% 不会触发抗跌分析
4. **东财 push2his K 线全线封禁**：`push2his.eastmoney.com` 返回 rc=102，5 分钟 K 线已改为雪球优先+新浪兜底。日 K 线不受影响（腾讯优先+东财兜底）
5. **雪球 cookie 过期**：`~/.lsa_xq_cookies` 约 25 天过期，过期后自动回退到新浪财经。用户可通过 `python3 scripts/xq_cookie_refresh.py --status` 检查状态
6. **板块 5 分钟 K 线合成**：通过成分股 Top 3 等权平均生成，不再依赖东财板块指数 API
7. **共享数据时效**：`analyze.py:41` 要求共享数据 mtime < 10 分钟，超时则每个子进程独立抓取
8. **subprocess 超时**：单票 60s 超时（`main.py:121`），全量 50 个板块 5-min K 线加载是瓶颈
9. **K 线日期顺序**：日 K 线按时间正序排列（`[0]` 最早），`infer_consecutive_boards()` 从末尾 `[-1]` 往回走
10. **输出格式硬约束**：SKILL.md 要求 agent 原样输出终端内容，禁止自行总结或添加评价。修改 `print_results()` 时不要破坏模板格式
