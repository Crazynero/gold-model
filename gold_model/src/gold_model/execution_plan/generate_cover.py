#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成封面PDF（Playwright渲染HTML）"""
import asyncio
from playwright.async_api import async_playwright

from gold_model.paths import ASSETS_DIR, EXECUTION_PLAN_DIR

HTML_PATH = str(ASSETS_DIR / 'cover.html')
PDF_PATH = str(EXECUTION_PLAN_DIR / 'cover.pdf')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(f'file://{HTML_PATH}')
        await page.wait_for_load_state('networkidle')
        await page.pdf(
            path=PDF_PATH,
            width='794px',
            height='1123px',
            print_background=True,
            margin={'top': '0', 'bottom': '0', 'left': '0', 'right': '0'}
        )
        await browser.close()
    print(f"Cover PDF generated: {PDF_PATH}")

asyncio.run(main())
