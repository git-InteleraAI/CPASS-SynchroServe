import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def find_wide_elements():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='msedge', headless=True)
        ctx = await b.new_context(viewport={'width': 800, 'height': 900})
        page = await ctx.new_page()
        await page.goto('http://localhost:5173')
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.locator('form#lf button.btn').first.click()
        await page.wait_for_timeout(2000)
        await page.locator('#sel-state').select_option(label='ANDHRA PRADESH')
        await page.wait_for_timeout(800)
        await page.locator('#sel-tc').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-order').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-batch').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-cand').select_option(index=1)
        await page.wait_for_timeout(1500)
        await page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first.click()
        await page.wait_for_timeout(1500)

        await page.emulate_media(media='print')

        wide = await page.evaluate('''() => {
            const elements = document.querySelectorAll('.cpass-statement-sheet *');
            const sheet = document.querySelector('.cpass-statement-sheet');
            const results = [];
            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                if (rect.width > 720 || el.scrollWidth > 720) {
                    results.push({
                        tag: el.tagName,
                        className: el.className,
                        width: rect.width,
                        scrollWidth: el.scrollWidth,
                        minWidth: style.minWidth,
                        maxWidth: style.maxWidth,
                    });
                }
            });
            return {
                sheetWidth: sheet.getBoundingClientRect().width,
                sheetScrollWidth: sheet.scrollWidth,
                wideElements: results.slice(0, 15)
            };
        }''')

        import pprint
        pprint.pprint(wide)
        await b.close()

if __name__ == '__main__':
    asyncio.run(find_wide_elements())

