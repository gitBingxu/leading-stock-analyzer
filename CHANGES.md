# Changeset

## 2026-05-13

### refactor: 迁移至 dragon-quant pip 包

- 删除全部 `scripts/` 目录（12 个文件），功能已完全由 `dragon-quant` 0.1.0 替代
- 重写 AGENTS.md：从旧脚本文档迁移为 dragon-quant 包使用指南（CLI + Python API）
- 重写 README.md：安装方式从 `git clone` 改为 `pip install dragon-quant`，命令改为 `dragon-quant scan` / `dragon-quant logs` / `dragon-quant data`
- 数据源从 4 源（东财+雪球+新浪+腾讯）精简为 3 源（东财+雪球+腾讯），新浪兜底逻辑已内置到包内
- 日志排查从 bash one-liner 改为 `dragon-quant logs query/summary` CLI
- Cookie 管理从 `scripts/xq_cookie_refresh.py` 改为 `dragon-quant data cookie-fetch`

## 2026-05-06

### docs: README 重写 — 纯用户视角

- 移除架构图、项目结构、版本历史、数据源表（转入 AGENTS.md）
- 新增：前提条件、怎么看结果、参数速查、FAQ、日志排查、免责声明
- 文档分工定型：README（用户）→ SKILL.md（agent）→ AGENTS.md（开发者）

### docs: SKILL.md 排查指南

- 新增"排查问题（日志分析）"章节：日志结构速查表、5 条常用排查命令（总体情况/慢 API/失败原因/子进程成功率/fallback 降级分）
- 5 种常见排查场景的流程指引
- 新增触发词：排查问题、为什么失败、为什么慢、日志分析、今天运行情况
- 明确排查类问题不适用"原样输出"规则

### feat: PersistLogger 持久化打点模块

- 新增 `scripts/persist_logger.py`（153 行），JSON Lines 格式，每日滚动，线程安全，写入失败静默降级
- 7 类事件：`session_start/end`、`pipeline_stage`、`api_call`、`subprocess`、`dimension_score`、`error`、`shared_data`
- 日志写入 `./logs/lsa_YYYYMMDD.jsonl`，启动和结束时自动清理 >7 天旧文件

### feat: eastmoney_api 内建 API 打点

- `_fetch()` 每次 HTTP 调用自动记录到 `_API_CALL_LOG`：url、耗时、成败、重试次数、失败原因、HTTP 状态码、响应片段
- 新增 `get_api_calls_and_clear()` 导出调用记录

### feat: analyze.py 传回耗时统计

- 返回 JSON 新增 `_elapsed_ms`（总耗时）、`_dim_times`（四维分段耗时）、`_api_calls`（API 调用记录）

### refactor: main.py 全链路日志

- 接入 PersistLogger，各阶段打点（preload/filter/rank/analyze）
- 子进程结束自动记录 subprocess 事件、维度得分、错误信息
- stderr 精简为 3 行启动/完成消息

### refactor: preload.py 接入日志

### fix: eastmoney_api.py 缺少 `import sys`

- 8 处 `sys.stderr` 引用之前未 import，只在行业映射加载失败等罕见路径触发

### fix: 连板数 off-by-one

- `infer_consecutive_boards()` 循环起始从 `len(kline)-1` 修正为 `len(kline)-2`，消除重复计数

### docs: AGENTS.md

- 首次创建，覆盖项目概览、架构、关键函数索引、权重/阈值速查、代码约定、7 个已知坑点
