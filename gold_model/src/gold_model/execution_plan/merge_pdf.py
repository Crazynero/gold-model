#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并封面+正文 → 最终方案PDF

用法：
  python3 -m gold_model.execution_plan.merge_pdf
依赖：先跑 generate_cover.py（cover.pdf）和 generate_pdf.py（body.pdf）
"""
from pypdf import PdfReader, PdfWriter

from gold_model.paths import EXECUTION_PLAN_DIR

COVER_PDF = EXECUTION_PLAN_DIR / 'cover.pdf'
BODY_PDF = EXECUTION_PLAN_DIR / 'body.pdf'
FINAL_PDF = EXECUTION_PLAN_DIR / '黄金ETF+期货组合仓位管理方案.pdf'


def main():
    writer = PdfWriter()
    for path in (COVER_PDF, BODY_PDF):
        if not path.exists():
            raise FileNotFoundError(f"缺少 {path.name}，请先运行对应的生成脚本")
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
        print(f"  + {path.name} ({len(reader.pages)}页)")

    with open(FINAL_PDF, 'wb') as f:
        writer.write(f)
    print(f"✅ 最终方案PDF: {FINAL_PDF}")


if __name__ == '__main__':
    main()
