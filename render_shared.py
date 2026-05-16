"""
共享渲染模块 — 将 dragon-quant 的 ranking 数据 + 文案渲染为图片

供 render_report.py 和 llm_render.py 共用。

导出:
  render_image(data, copy_blocks, out_path)  — 主入口
"""

import json, re, os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CARD_H = 170  # 卡片高度 (SCALE 乘数)


def render_image(data, copy_blocks, out_path):
    """
    渲染龙头战法日报图片。

    参数:
      data:         dragon-quant scan_results JSON 的完整 dict
      copy_blocks:  {code: [line1, line2, ...]}  每只股票的文案列表
      out_path:     输出 PNG 路径 (Path or str)
    """
    ranking = data['ranking'][:5]

    # ── 字体 ──
    font_path = find_font()
    ctx = RenderCtx(font_path)
    draw = ctx.draw

    # ── 标题 ──
    date_str = data.get('timestamp', '')
    if len(date_str) >= 8:
        display_date = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
    else:
        display_date = ''

    draw.text((ctx.PADDING, 15 * ctx.SCALE), '🐉 龙头战法日报', font=ctx.title_font, fill=ctx.TITLE_C)
    draw.text((ctx.PADDING + ctx.tw('🐉 龙头战法日报', ctx.title_font) + 12 * ctx.SCALE, 24 * ctx.SCALE),
              display_date, font=ctx.date_font, fill=ctx.DATE_C)
    draw.text((ctx.PADDING, 50 * ctx.SCALE), 'TOP5 四维评分排名', font=ctx.sub_font, fill=ctx.SUB_C)

    # ── 颜色图例 ──
    legend_y = 50 * ctx.SCALE
    title_w = ctx.tw('TOP5 四维评分排名', ctx.sub_font)
    legend_x = ctx.PADDING + title_w + 40 * ctx.SCALE
    legend_items = [
        (ctx.C_DRIVE, '带动性 35%'),
        (ctx.C_ANTI, '抗跌性 15%'),
        (ctx.C_LEAD, '领涨性 25%'),
        (ctx.C_ABSORB, '资金承接 25%'),
    ]
    lx = legend_x
    for color, label in legend_items:
        ctx.draw.rectangle([lx, legend_y + 2 * ctx.SCALE, lx + 12 * ctx.SCALE, legend_y + 14 * ctx.SCALE], fill=color)
        ctx.draw.text((lx + 16 * ctx.SCALE, legend_y), label, font=ctx.note_font, fill=ctx.SUB_C)
        lx += ctx.tw(label, ctx.note_font) + 35 * ctx.SCALE

    # ── 表格 ──
    t1_y = 80 * ctx.SCALE
    _draw_table(ctx, ranking, t1_y)

    # ── 个股卡片 ──
    detail_y = int(t1_y + ctx.header_h + ctx.row_h * 5 + 20 * ctx.SCALE)
    _draw_cards(ctx, ranking, copy_blocks, detail_y)

    # ── 脚注 ──
    card_h = CARD_H * ctx.SCALE
    footer_y = int(detail_y + 5 * (card_h + 12 * ctx.SCALE) + 10 * ctx.SCALE)
    _draw_footer(ctx, data, footer_y)

    ctx.img.save(out_path, 'PNG')
    print(f'✅ 报告已生成: {out_path}')


# ═══════════════════════════════════════════════════════════════
# 渲染上下文
# ═══════════════════════════════════════════════════════════════

class RenderCtx:
    def __init__(self, font_path):
        self.SCALE = 3
        self.SP = 30 * self.SCALE
        self.PADDING = self.SP

        self._font_path = font_path
        self.title_font = self._get_font(24)
        self.date_font = self._get_font(14)
        self.sub_font = self._get_font(16)
        self.header_font = self._get_font(13)
        self.cell_font = self._get_font(12)
        self.note_font = self._get_font(11)
        self.detail_title_font = self._get_font(13)
        self.detail_text_font = self._get_font(10)

        # 颜色
        self.BG = '#0F0F23'
        self.TITLE_C = '#FFFFFF'
        self.DATE_C = '#8888AA'
        self.SUB_C = '#C0C0D0'
        self.HEADER_BG = '#1A1A3E'
        self.HEADER_C = '#E0E0F0'
        self.ROW_BG_EVEN = '#161636'
        self.ROW_BG_ODD = '#1C1C44'
        self.CELL_C = '#D0D0E0'
        self.ACCENT_CYAN = '#00BCD4'
        self.ACCENT_GOLD = '#FFD54F'
        self.BORDER_C = '#2A2A5E'
        self.DETAIL_BG = '#121230'
        self.CARD_BORDER = '#3A3A6E'
        self.FOOTER_C = '#555577'
        self.PROGRESS_BG = '#222244'
        self.TAG_BG = '#1E3A5F'

        self.C_DRIVE = '#E53935'
        self.C_ANTI = '#FB8C00'
        self.C_LEAD = '#43A047'
        self.C_ABSORB = '#1E88E5'
        self.C_RANK = ['#FFD700', '#C0C0C0', '#CD7F32', '#FF8A65', '#64B5F6']

        self.score_colors = [self.C_DRIVE, self.C_ANTI, self.C_LEAD, self.C_ABSORB, '#8E24AA']
        self.emojis = ['🥇', '🥈', '🥉', '4', '5']
        self.dim_colors = {
            'drive': self.C_DRIVE, 'anti': self.C_ANTI,
            'lead': self.C_LEAD, 'absorb': self.C_ABSORB,
        }
        self.dim_labels = {
            'drive': '带动性', 'anti': '抗跌性',
            'lead': '领涨性', 'absorb': '资金承接',
        }

        # 列宽 / 表格尺寸
        self.col_widths = [w * self.SCALE for w in [50, 100, 90, 85, 85, 85, 85, 100]]
        self.table_w = sum(self.col_widths)
        self.page_w = self.table_w + self.SP * 2
        self.header_h = 36 * self.SCALE
        self.row_h = 34 * self.SCALE
        self.radius = 10 * self.SCALE

        total_h = int(self.PADDING + 55 * self.SCALE + self.header_h + self.row_h * 5
                      + 30 * self.SCALE + CARD_H * self.SCALE * 5 + 50 * self.SCALE)
        self.img = Image.new('RGB', (self.page_w, total_h), self.BG)
        self.draw = ImageDraw.Draw(self.img)

    def _get_font(self, sz):
        if self._font_path:
            return ImageFont.truetype(self._font_path, sz * 3)
        return ImageFont.load_default()

    def tw(self, text, font):
        return font.getlength(text)

    def rounded_rect(self, xy, fill, r=None):
        x1, y1, x2, y2 = xy
        rr = r if r else self.radius
        d = self.draw
        d.pieslice([x1, y1, x1 + rr*2, y1 + rr*2], 180, 270, fill=fill)
        d.pieslice([x2 - rr*2, y1, x2, y1 + rr*2], 270, 360, fill=fill)
        d.pieslice([x1, y2 - rr*2, x1 + rr*2, y2], 90, 180, fill=fill)
        d.pieslice([x2 - rr*2, y2 - rr*2, x2, y2], 0, 90, fill=fill)
        d.rectangle([x1 + rr, y1, x2 - rr, y2], fill=fill)
        d.rectangle([x1, y1 + rr, x2, y2 - rr], fill=fill)


# ═══════════════════════════════════════════════════════════════
# 子绘制函数
# ═══════════════════════════════════════════════════════════════

def _draw_table(ctx, ranking, t1_y):
    t1_x = ctx.PADDING
    headers = ['排名', '股票名称', '代码', '带动性\n(35%)', '抗跌性\n(15%)',
               '领涨性\n(25%)', '资金承接\n(25%)', '综合评分']

    ctx.rounded_rect([t1_x - 4 * ctx.SCALE, t1_y - 4 * ctx.SCALE,
                      t1_x + ctx.table_w + 4 * ctx.SCALE,
                      t1_y + ctx.header_h + ctx.row_h * 5 + 4 * ctx.SCALE], ctx.CARD_BORDER)
    ctx.rounded_rect([t1_x, t1_y, t1_x + ctx.table_w, t1_y + ctx.header_h], ctx.HEADER_BG)

    cx = t1_x
    for hdr, cw in zip(headers, ctx.col_widths):
        lns = hdr.split('\n')
        ly = t1_y + 4 * ctx.SCALE
        for l in lns:
            lw = ctx.tw(l, ctx.header_font)
            if l == hdr and len(lns) == 1:
                ctx.draw.text((cx + (cw - lw) / 2, ly + 6 * ctx.SCALE), l,
                              font=ctx.header_font, fill=ctx.HEADER_C)
            else:
                ctx.draw.text((cx + (cw - lw) / 2, ly), l,
                              font=ctx.header_font, fill=ctx.HEADER_C)
                ly += 15 * ctx.SCALE
        cx += cw

    ctx.draw.line([(t1_x, t1_y + ctx.header_h), (t1_x + ctx.table_w, t1_y + ctx.header_h)],
                  fill=ctx.BORDER_C, width=2 * ctx.SCALE)

    for ri, r in enumerate(ranking[:5]):
        row_y = t1_y + ctx.header_h + ri * ctx.row_h
        bg = ctx.ROW_BG_EVEN if ri % 2 == 0 else ctx.ROW_BG_ODD
        ctx.draw.rectangle([t1_x, row_y, t1_x + ctx.table_w, row_y + ctx.row_h], fill=bg)

        d = r['dimensions']
        vals = [ctx.emojis[ri], r['name'], r['code'],
                d['drive']['score'], d['anti_drop']['score'],
                d['leadership']['score'], d['absorption']['score'],
                r['composite_score']]
        cx = t1_x
        for ci, (val, cw) in enumerate(zip(vals, ctx.col_widths)):
            if ci == 0:
                ctx.draw.text((cx + (cw - ctx.tw(str(val), ctx.cell_font)) / 2,
                              row_y + 6 * ctx.SCALE), str(val),
                              font=ctx.cell_font, fill=ctx.C_RANK[ri])
            elif ci == 1:
                ctx.draw.text((cx + 8 * ctx.SCALE, row_y + 6 * ctx.SCALE),
                              str(val), font=ctx.cell_font, fill=ctx.CELL_C)
            elif ci == 2:
                ctx.draw.text((cx + 8 * ctx.SCALE, row_y + 6 * ctx.SCALE),
                              str(val), font=ctx.cell_font, fill=ctx.ACCENT_CYAN)
            elif ci < len(ctx.col_widths) - 1:
                sv = f'{val:.1f}'
                ctx.draw.text((cx + cw - ctx.tw(sv, ctx.cell_font) - 10 * ctx.SCALE,
                              row_y + 6 * ctx.SCALE), sv,
                              font=ctx.cell_font, fill=ctx.score_colors[ci - 3])
            else:
                sv = f'{val:.1f}'
                ctx.draw.text((cx + cw - ctx.tw(sv, ctx.cell_font) - 10 * ctx.SCALE,
                              row_y + 6 * ctx.SCALE), sv,
                              font=ctx.cell_font, fill=ctx.C_RANK[ri])
            cx += cw

        # 概念标签
        concepts = r.get('concepts', [])
        if concepts:
            tag_x = t1_x + ctx.col_widths[0] + ctx.col_widths[1] + 8 * ctx.SCALE
            tag_y = row_y + 6 * ctx.SCALE
            for cname in concepts[:2]:
                tag_w = ctx.tw(cname, ctx.note_font) + 10 * ctx.SCALE
                tag_h = 16 * ctx.SCALE
                if tag_x + tag_w < t1_x + ctx.col_widths[0] + ctx.col_widths[1] + ctx.col_widths[2] - 4 * ctx.SCALE:
                    ctx.rounded_rect([tag_x, tag_y, tag_x + tag_w, tag_y + tag_h],
                                    ctx.TAG_BG, r=4 * ctx.SCALE)
                    ctx.draw.text((tag_x + 5 * ctx.SCALE, tag_y + 1 * ctx.SCALE),
                                  cname, font=ctx.note_font, fill=ctx.ACCENT_CYAN)
                    tag_x += tag_w + 4 * ctx.SCALE

        ctx.draw.line([(t1_x, row_y + ctx.row_h), (t1_x + ctx.table_w, row_y + ctx.row_h)],
                      fill=ctx.BORDER_C, width=1 * ctx.SCALE)


def _draw_cards(ctx, ranking, copy_blocks, detail_y):
    card_width = ctx.table_w + 8 * ctx.SCALE
    card_radius = 12 * ctx.SCALE
    card_h = CARD_H * ctx.SCALE

    for ri, r in enumerate(ranking[:5]):
        code = r['code']
        points = copy_blocks.get(code, [])

        card_x = ctx.PADDING - 4 * ctx.SCALE
        card_y = detail_y + ri * (card_h + 12 * ctx.SCALE)

        # 卡片背景
        ctx.rounded_rect([card_x, card_y, card_x + card_width, card_y + card_h],
                         ctx.CARD_BORDER, r=card_radius)
        ctx.rounded_rect([card_x + 2 * ctx.SCALE, card_y + 2 * ctx.SCALE,
                         card_x + card_width - 2 * ctx.SCALE, card_y + card_h - 2 * ctx.SCALE],
                         ctx.DETAIL_BG, r=card_radius - 2 * ctx.SCALE)

        # 左侧排名色条
        bar_w = 6 * ctx.SCALE
        ctx.draw.rectangle([card_x + 2 * ctx.SCALE, card_y + 2 * ctx.SCALE,
                           card_x + 2 * ctx.SCALE + bar_w, card_y + card_h - 2 * ctx.SCALE],
                           fill=ctx.C_RANK[ri])

        # 标题
        concepts_str = ' · '.join(r.get('concepts', []))
        board_info = f"{r.get('board_count', 0)}连板" if r.get('board_count', 0) > 0 else '未涨停'
        score_info = f"{r['composite_score']:.1f}分"
        score_label = '强票' if r['composite_score'] >= 70 else '中票' if r['composite_score'] >= 60 else '弱票'

        name_part = f"{r['name']}({code})  "
        detail_part = f"{concepts_str} | {board_info}"
        score_part = f"{score_info} - {score_label}"

        lx = card_x + 18 * ctx.SCALE
        ctx.draw.text((lx, card_y + 10 * ctx.SCALE), name_part,
                      font=ctx.detail_title_font, fill=ctx.C_RANK[ri])
        lx += ctx.tw(name_part, ctx.detail_title_font)
        ctx.draw.text((lx, card_y + 10 * ctx.SCALE), detail_part,
                      font=ctx.detail_title_font, fill=ctx.CELL_C)
        lx += ctx.tw(detail_part, ctx.detail_title_font) + 8 * ctx.SCALE
        ctx.draw.text((lx, card_y + 10 * ctx.SCALE), score_part,
                      font=ctx.detail_title_font, fill=ctx.ACCENT_GOLD)

        # ── 四维概览条 ──
        summary_y = card_y + 36 * ctx.SCALE
        dim_names = ['drive', 'anti', 'lead', 'absorb']
        dim_scores = [
            r['dimensions']['drive']['score'],
            r['dimensions']['anti_drop']['score'],
            r['dimensions']['leadership']['score'],
            r['dimensions']['absorption']['score'],
        ]
        bar_start_x = card_x + 18 * ctx.SCALE
        bar_item_w = (card_width - 36 * ctx.SCALE) // 4 - 6 * ctx.SCALE

        for di, (dkey, dscore) in enumerate(zip(dim_names, dim_scores)):
            bx = bar_start_x + di * (bar_item_w + 6 * ctx.SCALE)
            by = summary_y
            dim_label = ctx.dim_labels[dkey]
            ctx.draw.text((bx, by), dim_label, font=ctx.detail_text_font, fill=ctx.dim_colors[dkey])
            ctx.draw.text((bx + ctx.tw(dim_label, ctx.detail_text_font) + 4 * ctx.SCALE, by),
                          f'{dscore:.1f}', font=ctx.detail_text_font, fill=ctx.CELL_C)

            progress_w = bar_item_w - 4 * ctx.SCALE
            progress_h = 6 * ctx.SCALE
            prog_y = by + 18 * ctx.SCALE
            ctx.draw.rectangle([bx, prog_y, bx + progress_w, prog_y + progress_h],
                              fill=ctx.PROGRESS_BG)
            fill_w = int(progress_w * dscore / 100.0)
            if fill_w > 0:
                ctx.draw.rectangle([bx, prog_y, bx + fill_w, prog_y + progress_h],
                                  fill=ctx.dim_colors[dkey])

        # ── 详细描述文字 ──
        desc_y = summary_y + 30 * ctx.SCALE
        desc_x = card_x + 18 * ctx.SCALE
        max_w = card_width - 36 * ctx.SCALE

        dy = desc_y
        for pt in points[:7]:
            pt = pt.replace('    - ', '• ').replace('- ', '• ')
            if not pt.startswith('•'):
                pt = '• ' + pt
            if ctx.tw(pt, ctx.detail_text_font) > max_w:
                while ctx.tw(pt + '...', ctx.detail_text_font) > max_w and len(pt) > 4:
                    pt = pt[:-1]
                pt += '...'
            ctx.draw.text((desc_x, dy), pt, font=ctx.detail_text_font, fill=ctx.CELL_C)
            dy += 16 * ctx.SCALE


def _draw_footer(ctx, data, footer_y):
    up_cnt = len(data.get("sectors", {}).get("up", []))
    down_cnt = len(data.get("sectors", {}).get("down", []))
    elapsed = data.get("elapsed_s", 0)
    api_ok = data.get("api_stats", {}).get("ok", 0)
    api_total = data.get("api_stats", {}).get("total", 0)
    ctx.draw.text((ctx.PADDING, footer_y),
                  f'📊 dragon-quant | 扫描 {up_cnt + down_cnt} 个板块 | {api_ok}/{api_total} API 请求成功 | 耗时 {elapsed:.0f}s',
                  font=ctx.note_font, fill=ctx.FOOTER_C)
    ctx.draw.text((ctx.PADDING, footer_y + 16 * ctx.SCALE),
                  '数据基于四维评分模型（带动性35% | 抗跌性15% | 领涨性25% | 资金承接25%），不构成投资建议',
                  font=ctx.note_font, fill=ctx.FOOTER_C)


# ═══════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════

def find_font():
    candidates = [
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/AppleSDGothicNeo.ttc',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    try:
        import matplotlib.font_manager as fm
        for f in fm.findSystemFonts():
            for kw in ['Heiti', 'PingFang', 'SourceHan']:
                if kw in os.path.basename(f):
                    return f
    except ImportError:
        pass
    return None


