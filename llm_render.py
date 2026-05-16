"""
LLM 文案渲染器 — 读取 dragon-quant JSON，调用 LLM 生成文案，渲染为图片

用法:
  python3 llm_render.py <结果json路径> [-o 输出png路径] [--model model-id] [--offline] [--copy copy文件]

依赖: pip3 install requests Pillow
支持任意 OpenAI 兼容 API（OpenAI / DeepSeek / OpenRouter / Ollama / Groq 等）

环境变量:
  LLM_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY    API Key（任一）
  LLM_BASE_URL / OPENAI_BASE_URL                        Base URL（可选，自动反推）
  LLM_MODEL                                             模型名（可选，按 Base URL 自动选）

示例:
  # OpenRouter (默认)
  OPENROUTER_API_KEY=sk-or-... python3 llm_render.py results.json
  # OpenAI 官方
  OPENAI_API_KEY=sk-... python3 llm_render.py results.json
  # DeepSeek 官方
  LLM_API_KEY=sk-... LLM_BASE_URL=https://api.deepseek.com/v1 LLM_MODEL=deepseek-chat \\
    python3 llm_render.py results.json
  # Ollama 本地
  LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b \\
    python3 llm_render.py results.json
  # 离线模式
  python3 llm_render.py results.json --offline
"""

import json, sys, os, re, time
from pathlib import Path
import requests
from render_shared import render_image


LLM_API_KEY = os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENROUTER_API_KEY', '')
LLM_BASE_URL = os.environ.get('LLM_BASE_URL') or os.environ.get('OPENAI_BASE_URL', '')
# 模型默认值：优先环境变量，否则自动选 openrouter 的 deepseek
LLM_MODEL = os.environ.get('LLM_MODEL', '')

# 如果没有显式设 LLM_BASE_URL，用 LLM_API_KEY 来源反推
if not LLM_BASE_URL:
    if os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY'):
        LLM_BASE_URL = 'https://api.openai.com/v1'
    elif os.environ.get('OPENROUTER_API_KEY'):
        LLM_BASE_URL = 'https://openrouter.ai/api/v1'
        if not LLM_MODEL:
            LLM_MODEL = 'deepseek/deepseek-v4-flash'
    else:
        LLM_BASE_URL = 'https://openrouter.ai/api/v1'  # last resort

if not LLM_MODEL:
    # 最后的兜底
    if 'openrouter' in LLM_BASE_URL:
        LLM_MODEL = 'deepseek/deepseek-v4-flash'
    else:
        LLM_MODEL = 'gpt-4o-mini'


def main():
    json_path = None
    out_path = None
    model = LLM_MODEL
    offline = False

    copy_file = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '-o' and i + 1 < len(args):
            out_path = Path(args[i + 1])
            i += 2
        elif args[i] == '--model' and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif args[i] == '--offline':
            offline = True
            i += 1
        elif args[i] == '--copy' and i + 1 < len(args):
            copy_file = Path(args[i + 1])
            i += 2
        elif not json_path:
            json_path = Path(args[i])
            i += 1
        else:
            i += 1

    if not json_path:
        results_dir = Path.home() / "Library" / "Application Support" / "dragon-quant" / "results"
        if results_dir.exists():
            json_files = sorted(results_dir.glob("scan_results_*.json"))
            if json_files:
                json_path = json_files[-1]
                print(f"📂 自动使用最新结果: {json_path}")

    if not json_path or not Path(json_path).exists():
        print("用法: python3 llm_render.py <结果json路径> [-o 输出路径] [--model model-id] [--offline] [--copy copy文件]")
        sys.exit(1)

    if isinstance(json_path, str):
        json_path = Path(json_path)

    if not out_path:
        m = re.search(r'(\d{8})', json_path.name)
        date_str = m.group(1) if m else ""
        out_path = Path.home() / "Desktop" / f"龙头日报_LLM_{date_str}.png"

    with open(json_path) as f:
        data = json.load(f)

    ranking = data['ranking'][:5]
    if not ranking:
        print("❌ ranking 数据为空")
        sys.exit(1)

    # 提取每只股票的紧凑数据
    stock_data = []
    for r in ranking:
        stock_data.append(_extract_stock_payload(r))

    if offline:
        # 离线模式：写 prompt 到文件，等 agent 填充
        prompt_file = json_path.parent / f"llm_prompt_{json_path.stem}.json"
        with open(prompt_file, 'w') as f:
            json.dump({"model": model, "stocks": stock_data}, f, ensure_ascii=False, indent=2)
        print(f"📝 已生成 prompt 文件: {prompt_file}")
        print("   请让 agent 根据此文件生成 copy_blocks，保存为 llm_copy_*.json")
        print(f"   然后运行: python3 llm_render.py {json_path} --copy llm_copy_*.json")
        return

    # 在线模式：调用 LLM
    if copy_file:
        print(f"📋 从 copy 文件加载文案: {copy_file}")
        with open(copy_file) as f:
            copy_data = json.load(f)
        if isinstance(copy_data, list):
            results = copy_data
        else:
            results = copy_data.get('results', [])
        copy_blocks = {}
        for item in results:
            copy_blocks[item['code']] = item['lines']
    else:
        if not LLM_API_KEY:
            print("❌ 缺少 API Key，请设置以下任一环境变量:")
            print("   LLM_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY")
            print("   或使用 --offline 模式")
            sys.exit(1)
        print(f"🤖 调用 LLM 生成文案... (model={model})")
        copy_blocks = _call_llm(stock_data, model)

    # 渲染
    render_image(data, copy_blocks, out_path)


def _extract_stock_payload(r):
    """从 ranking 条目提取 LLM 需要的紧凑数据"""
    d = r['dimensions']
    drive_d = d['drive']['details']
    anti_d = d['anti_drop']['details']
    lead_d = d['leadership']['details']
    absorb_d = d['absorption']['details']

    payload = {
        'code': r['code'],
        'name': r['name'],
        'concepts': r.get('concepts', []),
        'board_count': r.get('board_count', 0),
        'composite_score': r['composite_score'],
        'primary_sector': r.get('primary_sector_name', ''),
        'drive': {'score': d['drive']['score']},
        'anti_drop': {'score': d['anti_drop']['score']},
        'leadership': {'score': d['leadership']['score']},
        'absorption': {'score': d['absorption']['score']},
    }

    # 带动性细节
    if drive_d.get('best_day_detail'):
        bd = drive_d['best_day_detail']
        vd = bd.get('board_detail', {})
        vr = bd.get('voice_raw', {})
        fr = bd.get('follow_raw', {})
        payload['drive']['voice'] = bd.get('voice', 0)
        payload['drive']['follow'] = bd.get('follow', 0)
        payload['drive']['sector_total'] = vr.get('total', 0)
        payload['drive']['limit_up_count'] = vr.get('limit_up', 0)
        payload['drive']['strong_count'] = fr.get('strong', 0)
        payload['drive']['down_count'] = fr.get('down', 0)
        bt = vd.get('board_time')
        payload['drive']['board_time'] = bt if bt else '非最先涨停'
        payload['drive']['seal_rank'] = vd.get('seal_rank', 99)

    # 抗跌性细节
    plunge_days = anti_d.get('plunge_days', [])
    payload['anti_drop']['plunge_count'] = len(plunge_days)
    if plunge_days:
        payload['anti_drop']['recent_plunge_dates'] = plunge_days[-5:]
        payload['anti_drop']['day_details'] = anti_d.get('day_details', [])[-5:]

    # 领涨性细节
    if lead_d.get('sector_median_pct') is not None:
        rank_pct = lead_d.get('intraday_percentile', 0) * 100
        payload['leadership']['rank_top_pct'] = round(100 - rank_pct, 1)
        payload['leadership']['sector_median_pct'] = lead_d['sector_median_pct']
        payload['leadership']['deviation'] = lead_d.get('deviation', 0)
        payload['leadership']['sector_total'] = lead_d.get('total_components', 0)

    # 资金承接细节
    event_count = absorb_d.get('event_count', 0)
    payload['absorption']['event_count'] = event_count
    if event_count > 0:
        best = absorb_d.get('best_event', {})
        payload['absorption']['best_target_pct'] = best.get('target_pct', 0)
        payload['absorption']['best_dive_time'] = best.get('dive_time', '')
        payload['absorption']['fleeing_count'] = best.get('fleeing_count', 0)
        payload['absorption']['yang_count'] = best.get('yang_count', 0)
    else:
        payload['absorption']['fallback_reason'] = absorb_d.get('fallback_reason', '')

    return payload


def _call_llm(stock_data, model):
    """调用 LLM API 生成文案，返回 copy_blocks {code: [lines]}"""

    system_prompt = """你是龙虎榜量化分析师。根据给定的股票四维评分数据，为每只股票生成 6 行分析文案。

输出要求：
- 严格输出 JSON，格式：{"results":[{"code":"...","lines":[6行文案]},...]}
- 每只股票 6 行文案，顺序固定：
  1. 板块共鸣：描述板块涨停情况、该股在板块中的带动作用
  2. 小弟跟风：描述跟风股数量、板块联动强度
  3. 封板力度：描述涨停时间、是否最先涨停
  4. 抗跌性：描述大盘跳水日的抗跌表现
  5. 领涨性：描述板块内排名、跑赢中位数幅度、偏离度
  6. 资金承接：描述跨板块资金虹吸信号（如无则写"暂无显著的跨板块资金虹吸信号"）

文案风格：
- 每条以 "• " 开头
- 简洁有力，50-100 字，不啰嗦
- 用中文逗号/分号
- 数字保留 1 位小数
- 不要使用 emoji（除了已经有的数据数字）"""

    user_prompt = f"""请根据以下股票四维评分数据，为每只股票生成6行分析文案。

```json
{json.dumps(stock_data, ensure_ascii=False, indent=2)}
```

严格返回 JSON，只包含 JSON，不要任何解释文字。"""

    resp = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        },
        timeout=120,
    )

    if resp.status_code != 200:
        print(f"❌ LLM API 返回错误: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)

    try:
        body = resp.json()
    except json.JSONDecodeError:
        print(f"❌ LLM API 返回非 JSON: {resp.text[:200]}")
        sys.exit(1)
    content = body['choices'][0]['message']['content']
    print(f"📡 LLM 耗时: {body.get('usage', {}).get('total_tokens', '?')} tokens")

    # 提取 JSON
    json_str = content
    if '```json' in json_str:
        json_str = json_str.split('```json')[1].split('```')[0]
    elif '```' in json_str:
        json_str = json_str.split('```')[1].split('```')[0]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        print(f"❌ LLM 返回非 JSON，原始内容: {content[:500]}")
        sys.exit(1)

    # 兼容两种格式：{"results": [...]} 或纯数组 [...]
    if isinstance(parsed, list):
        results = parsed
    else:
        results = parsed.get('results', [])
    copy_blocks = {}
    for item in results:
        copy_blocks[item['code']] = item['lines']

    return copy_blocks


if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f"⏱ 总耗时: {time.time() - t0:.1f}s")
