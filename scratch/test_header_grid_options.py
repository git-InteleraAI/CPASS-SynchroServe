import asyncio
import os
import sys
import json
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def test_grid():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5173", wait_until="networkidle")

        # Login L1
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.locator('form#lf button.btn').first.click()
        await page.wait_for_timeout(2500)

        # Select Candidate 1076631
        await page.locator("#sel-state").select_option(label="ANDHRA PRADESH")
        await page.wait_for_timeout(1000)
        await page.locator("#sel-tc").select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator("#sel-order").select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator("#sel-batch").select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator("#sel-cand").select_option(index=1)
        await page.wait_for_timeout(2000)

        # Open statement modal in L1
        await page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first.click()
        await page.wait_for_timeout(2000)
        await page.wait_for_selector(".cpass-statement-sheet")

        # Test CSS grid configurations:
        # 1. Baseline (Current flexbox)
        # 2. Grid: 200px 1fr 200px
        # 3. Grid: minmax(180px, 1fr) auto minmax(180px, 1fr)
        # 4. Grid: 1fr auto 1fr with minmax(0, 1fr)

        configs = [
            ("Baseline (Flexbox)", ""),
            ("Grid 200px 1fr 200px", """
                .cpass-statement-header {
                    display: grid !important;
                    grid-template-columns: 200px 1fr 200px !important;
                    align-items: center !important;
                    width: 100% !important;
                }
                .cpass-header-logo { justify-self: start !important; }
                .cpass-header-title { justify-self: center !important; text-align: center !important; width: 100% !important; }
                .cpass-header-meta { justify-self: end !important; text-align: right !important; }
            """),
            ("Grid minmax(0, 1fr) auto minmax(0, 1fr)", """
                .cpass-statement-header {
                    display: grid !important;
                    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) !important;
                    align-items: center !important;
                    width: 100% !important;
                }
                .cpass-header-logo { justify-self: start !important; }
                .cpass-header-title { justify-self: center !important; text-align: center !important; }
                .cpass-header-meta { justify-self: end !important; text-align: right !important; }
            """),
            ("Grid minmax(180px, 1fr) auto minmax(180px, 1fr)", """
                .cpass-statement-header {
                    display: grid !important;
                    grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr) !important;
                    align-items: center !important;
                    width: 100% !important;
                }
                .cpass-header-logo { justify-self: start !important; }
                .cpass-header-title { justify-self: center !important; text-align: center !important; }
                .cpass-header-meta { justify-self: end !important; text-align: right !important; }
            """)
        ]

        for name, css in configs:
            print(f"\n--- Testing Config: {name} ---")
            if css:
                await page.add_style_tag(content=css)
                await page.wait_for_timeout(500)

            for media in ["screen", "print"]:
                await page.emulate_media(media=media)
                await page.wait_for_timeout(500)

                meas = await page.evaluate("""() => {
                    const sheet = document.querySelector('.cpass-statement-sheet');
                    const header = document.querySelector('.cpass-statement-header');
                    const logo = document.querySelector('.cpass-header-logo');
                    const title = document.querySelector('.cpass-header-title');
                    const h2 = document.querySelector('.cpass-header-title h2');
                    const meta = document.querySelector('.cpass-header-meta');

                    const sRect = sheet.getBoundingClientRect();
                    const hRect = header.getBoundingClientRect();
                    const lRect = logo.getBoundingClientRect();
                    const tRect = title.getBoundingClientRect();
                    const h2Rect = h2.getBoundingClientRect();
                    const mRect = meta.getBoundingClientRect();

                    const pageMid = sRect.left + (sRect.width / 2);
                    const titleMid = tRect.left + (tRect.width / 2);
                    const h2Mid = h2Rect.left + (h2Rect.width / 2);

                    return {
                        sheetWidth: sRect.width,
                        logoWidth: lRect.width,
                        titleWidth: tRect.width,
                        h2Width: h2Rect.width,
                        h2Lines: Math.round(h2Rect.height / 20),
                        metaWidth: mRect.width,
                        pageMid: pageMid.toFixed(2),
                        titleMid: titleMid.toFixed(2),
                        h2Mid: h2Mid.toFixed(2),
                        titleOffsetFromPageMid: (titleMid - pageMid).toFixed(2),
                        h2OffsetFromPageMid: (h2Mid - pageMid).toFixed(2),
                    };
                }""")
                print(f"  [{media.upper()}] SheetW: {meas['sheetWidth']:.1f}px | LogoW: {meas['logoWidth']:.1f}px | MetaW: {meas['metaWidth']:.1f}px | TitleW: {meas['titleWidth']:.1f}px")
                print(f"           PageMid: {meas['pageMid']} | TitleMid: {meas['titleMid']} | Offset: {meas['titleOffsetFromPageMid']}px | H2 Offset: {meas['h2OffsetFromPageMid']}px")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_grid())

