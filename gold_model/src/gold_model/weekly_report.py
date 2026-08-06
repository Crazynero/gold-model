"""GOLD COMMAND V6 — 周报生成器
输出 PDF 周报到 outputs/weekly_reports/

用法：
  python3 -m gold_model.weekly_report
  # 或通过 API: GET /api/report/weekly
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 字体注册（macOS: Songti .ttc 需 subfontIndex | Linux: Noto/DejaVu）
def _register(name, candidates):
    for path, idx in candidates:
        if os.path.exists(path):
            try:
                if idx is None:
                    pdfmetrics.registerFont(TTFont(name, path))
                else:
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
                return
            except Exception:
                continue
    print(f'[font] no usable font for {name}', file=sys.stderr)

_register('CJK', [('/System/Library/Fonts/Supplemental/Songti.ttc', 3),
                  ('/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf', None)])
_register('CJK-Bold', [('/System/Library/Fonts/Supplemental/Songti.ttc', 1),
                       ('/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf', None)])
_register('Mono', [('/System/Library/Fonts/Menlo.ttc', 0),
                   ('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', None)])

# 数据路径（统一走 paths.py）
from gold_model.paths import DASHBOARD_JSON, EXECUTION_JSON, DRIFT_HISTORY, WEEKLY_REPORTS_DIR

DASHBOARD = DASHBOARD_JSON
EXECUTION = EXECUTION_JSON
DRIFT = DRIFT_HISTORY
OUT_DIR = WEEKLY_REPORTS_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

# V6 配色
C_BG = HexColor('#04060a')
C_ACCENT = HexColor('#00d4ff')
C_POS = HexColor('#00ff9c')
C_NEG = HexColor('#ff3860')
C_WARN = HexColor('#ffb800')
C_GOLD = HexColor('#ffb020')
C_TEXT = HexColor('#e6edf3')
C_MUTED = HexColor('#8b949e')


def load_data():
    with open(DASHBOARD, 'r', encoding='utf-8') as f:
        dash = json.load(f)
    with open(EXECUTION, 'r', encoding='utf-8') as f:
        exec_ = json.load(f)
    drift = []
    if DRIFT.exists():
        with open(DRIFT, 'r', encoding='utf-8') as f:
            drift = json.load(f)
    return dash, exec_, drift


def make_styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle('Base', parent=ss['Normal'], fontName='CJK', fontSize=10, leading=15, textColor=C_TEXT)
    styles = {
        'title': ParagraphStyle('T', parent=base, fontName='CJK-Bold', fontSize=32, leading=42, alignment=TA_CENTER, textColor=C_ACCENT, spaceAfter=8),
        'subtitle': ParagraphStyle('S', parent=base, fontName='Mono', fontSize=11, alignment=TA_CENTER, textColor=C_MUTED, spaceAfter=20, letterSpacing=2),
        'h1': ParagraphStyle('H1', parent=base, fontName='CJK-Bold', fontSize=18, leading=28, textColor=C_ACCENT, spaceBefore=16, spaceAfter=8),
        'h2': ParagraphStyle('H2', parent=base, fontName='CJK-Bold', fontSize=13, leading=20, textColor=C_TEXT, spaceBefore=10, spaceAfter=6),
        'body': base,
        'meta': ParagraphStyle('M', parent=base, fontName='Mono', fontSize=9, textColor=C_MUTED, alignment=TA_CENTER, spaceAfter=12),
    }
    return styles


def section_divider():
    """// 装饰分隔符"""
    return Paragraph('<font color="#00d4ff">//</font>', make_styles()['meta'])


def safe(v):
    if v is None: return '--'
    s = str(v)
    if s in ('nan', 'NaN', 'None', ''): return '--'
    return s


def build_weekly(dash, exec_, drift, styles):
    """构造周报内容"""
    ov = dash.get('overview', {})
    strategies = dash.get('strategies', [])
    features = dash.get('features', [])[:10]
    ml_models = dash.get('ml_models', [])
    holdout = dash.get('v5_holdout', [])
    regression = dash.get('v5_regression', [])
    v3e = next((s for s in strategies if 'V3.0-E' in (s.get('策略') or '')), {})
    v3e_holdout = next((s for s in holdout if 'V3.0-E' in (s.get('strategy') or '')), {})

    story = []

    # === 封面 ===
    story.append(Spacer(1, 80 * mm))
    story.append(Paragraph('GOLD COMMAND', styles['title']))
    story.append(Paragraph('WEEKLY REPORT', styles['title']))
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph(f"V6.0 // {datetime.now().strftime('%Y-%m-%d')}", styles['subtitle']))
    story.append(Spacer(1, 30 * mm))

    # 封面关键指标摘要
    summary_data = [
        ['预测基准日', safe(ov.get('预测基准日'))],
        ['当前金价', safe(ov.get('当前金价'))],
        ['当前 Regime', safe(ov.get('当前Regime'))],
        ['建议操作', safe(ov.get('建议操作'))],
        ['加权集成概率', safe(ov.get('加权集成概率'))],
        ['最优夏普 (V3.0-E)', safe(v3e.get('夏普'))],
        ['Holdout 衰减', f"{(1 - (v3e_holdout.get('sharpe', 0) / float(v3e.get('夏普') or 1))) * 100:.0f}%" if v3e and v3e_holdout else '--'],
    ]
    t = Table(summary_data, colWidths=[60*mm, 60*mm])
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'CJK', 10),
        ('TEXTCOLOR', (0, 0), (0, -1), C_MUTED),
        ('TEXTCOLOR', (1, 0), (1, -1), C_ACCENT),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, HexColor('#232328')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(PageBreak())

    # === Page 2: 策略表现 ===
    story.append(Paragraph('// 策略表现对比', styles['h1']))
    story.append(Spacer(1, 6))
    strat_data = [['策略', '年化收益', '夏普', '最大回撤', '胜率', 'Calmar']]
    for s in strategies:
        strat_data.append([
            safe(s.get('策略'))[:18],
            safe(s.get('年化收益')),
            safe(s.get('夏普')),
            safe(s.get('最大回撤')),
            safe(s.get('胜率')),
            safe(s.get('Calmar')),
        ])
    t2 = Table(strat_data, colWidths=[45*mm, 22*mm, 18*mm, 22*mm, 18*mm, 20*mm])
    t2.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'CJK', 9),
        ('FONT', (0, 0), (-1, 0), 'CJK-Bold', 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), C_ACCENT),
        ('TEXTCOLOR', (0, 1), (-1, -1), C_TEXT),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, C_ACCENT),
        ('LINEBELOW', (0, 1), (-1, -1), 0.2, HexColor('#232328')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [None, HexColor('#0a0e16')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t2)

    # ML 模型表现
    story.append(Spacer(1, 12))
    story.append(Paragraph('// ML 模型表现', styles['h1']))
    ml_data = [['周期', '准确率', 'AUC', 'IC']]
    for m in ml_models:
        ml_data.append([safe(m.get('period')), safe(m.get('accuracy')), safe(m.get('auc')), safe(m.get('ic'))])
    t3 = Table(ml_data, colWidths=[30*mm, 30*mm, 30*mm, 30*mm])
    t3.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'CJK', 9),
        ('FONT', (0, 0), (-1, 0), 'CJK-Bold', 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), C_ACCENT),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, C_ACCENT),
        ('LINEBELOW', (0, 1), (-1, -1), 0.2, HexColor('#232328')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t3)

    story.append(PageBreak())

    # === Page 3: 特征 + Holdout ===
    story.append(Paragraph('// 特征重要性 TOP10', styles['h1']))
    feat_data = [['#', '因子', '重要性']]
    for i, f in enumerate(features, 1):
        feat_data.append([str(i), safe(f.get('name'))[:30], f"{f.get('avg', 0):.2f}"])
    t4 = Table(feat_data, colWidths=[15*mm, 80*mm, 30*mm])
    t4.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'CJK', 9),
        ('FONT', (0, 0), (-1, 0), 'CJK-Bold', 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), C_ACCENT),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, C_ACCENT),
        ('LINEBELOW', (0, 1), (-1, -1), 0.2, HexColor('#232328')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t4)

    story.append(Spacer(1, 12))
    story.append(Paragraph('// Holdout 验证', styles['h1']))
    h_data = [['策略', 'Full Sharpe', 'OOS Sharpe', '衰减%', 'OOS 回撤']]
    for h in holdout:
        full_s = next((s.get('夏普') for s in strategies if s.get('策略') == h.get('strategy')), '--')
        try:
            full = float(full_s)
            oos = float(h.get('sharpe', 0))
            decay = f"{(1 - oos / full) * 100:.0f}%" if full > 0 else '--'
        except:
            decay = '--'
        h_data.append([
            safe(h.get('strategy'))[:18],
            safe(full_s),
            f"{h.get('sharpe', 0):.2f}",
            decay,
            safe(h.get('max_dd')),
        ])
    t5 = Table(h_data, colWidths=[45*mm, 28*mm, 28*mm, 22*mm, 22*mm])
    t5.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'CJK', 9),
        ('FONT', (0, 0), (-1, 0), 'CJK-Bold', 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), C_ACCENT),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, C_ACCENT),
        ('LINEBELOW', (0, 1), (-1, -1), 0.2, HexColor('#232328')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t5)

    story.append(PageBreak())

    # === Page 4: 告警 + 操作建议 ===
    story.append(Paragraph('// 异常告警汇总', styles['h1']))
    if len(drift) >= 2:
        latest = drift[-1]
        prev = drift[-2]
        ts = latest.get('timestamp') or latest.get('run_date') or '--'
        sb = latest.get('signal_backtest', {})
        hit = sb.get('recent_20_hit_rate')
        wf = sb.get('wf_baseline_acc')
        if hit is not None and wf is not None:
            dev = hit - wf
            if dev < -0.20:
                story.append(Paragraph(f'<font color="#ff3860"><b>HIGH</b></font> 命中率 {hit*100:.0f}% 远低于基准 (偏差 {dev*100:.0f}%)', styles['body']))
                story.append(Spacer(1, 4))
        cur = latest.get('current_state', {})
        prev_cur = prev.get('current_state', {})
        if cur.get('regime') and prev_cur.get('regime') and cur.get('regime') != prev_cur.get('regime'):
            story.append(Paragraph(f'<font color="#ff3860"><b>HIGH</b></font> Regime 切换: {prev_cur.get("regime")} → {cur.get("regime")}', styles['body']))
            story.append(Spacer(1, 4))
        # 特征变化
        cur_top5 = list(latest.get('feature_importance_top10', {}).keys())[:5]
        prev_top5 = list(prev.get('feature_importance_top10', {}).keys())[:5]
        new_e = [f for f in cur_top5 if f not in prev_top5]
        if new_e:
            story.append(Paragraph(f'<font color="#00d4ff"><b>LOW</b></font> TOP5 特征排名变化 - 新进: {", ".join(new_e)}', styles['body']))
    else:
        story.append(Paragraph('无足够历史数据生成告警', styles['body']))

    story.append(Spacer(1, 16))
    story.append(Paragraph('// 本周操作建议', styles['h1']))
    advice = []
    advice.append(f"<b>当前信号</b>: {safe(ov.get('建议操作'))}")
    advice.append(f"<b>Regime</b>: {safe(ov.get('当前Regime'))} (熊市做空风险高，非对称仓位生效)")
    advice.append(f"<b>加权概率</b>: {safe(ov.get('加权集成概率'))} (低于 60% 不建仓)")
    advice.append(f"<b>命中率熔断</b>: {'生效中' if hit and wf and hit - wf < -0.10 else '正常'}")
    advice.append(f"<b>建议 ETF 配置</b>: GLD/IAU 65%")
    advice.append(f"<b>建议期货配置</b>: GC=F 35% (杠杆 ≤ 1x)")
    advice.append(f"<b>止损位</b>: 金价 -3% 或跌破 MA50")
    advice.append(f"<b>止盈位</b>: +5% 或 Regime 转熊")
    for a in advice:
        story.append(Paragraph(f"• {a}", styles['body']))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 20))
    story.append(Paragraph(f'// 报告生成于 {datetime.now().strftime("%Y-%m-%d %H:%M")} | GOLD COMMAND V6.0', styles['meta']))

    return story


def page_decorations(canvas, doc):
    """页眉页脚装饰"""
    canvas.saveState()
    # 页眉
    canvas.setFont('Mono', 7)
    canvas.setFillColor(C_MUTED)
    canvas.drawString(20*mm, A4[1] - 12*mm, 'GOLD COMMAND V6.0 // WEEKLY REPORT')
    canvas.drawRightString(A4[0] - 20*mm, A4[1] - 12*mm, datetime.now().strftime('%Y-%m-%d'))
    canvas.setStrokeColor(HexColor('#232328'))
    canvas.setLineWidth(0.3)
    canvas.line(20*mm, A4[1] - 14*mm, A4[0] - 20*mm, A4[1] - 14*mm)
    # 页脚
    canvas.drawString(20*mm, 12*mm, 'Z.AI // GOLD COMMAND')
    canvas.drawRightString(A4[0] - 20*mm, 12*mm, f'Page {doc.page}')
    canvas.line(20*mm, 14*mm, A4[0] - 20*mm, 14*mm)
    canvas.restoreState()


def main():
    dash, exec_, drift = load_data()
    styles = make_styles()

    out_path = OUT_DIR / f"gold_weekly_{datetime.now().strftime('%Y%m%d')}.pdf"
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=22*mm, bottomMargin=22*mm,
        title='GOLD COMMAND V6 周报',
        author='Z.AI',
        subject='黄金多因子预测周报',
    )
    story = build_weekly(dash, exec_, drift, styles)
    doc.build(story, onFirstPage=page_decorations, onLaterPages=page_decorations)
    print(f'[weekly] PDF saved: {out_path}')
    return str(out_path)


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
