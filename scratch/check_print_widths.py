import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def check():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='msedge', headless=True)
        ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await page.goto('http://localhost:5173')
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.locator('form#lf button.btn').first.click()
        await page.wait_for_timeout(2500)
        await page.locator('#sel-state').select_option(label='ANDHRA PRADESH')
        await page.wait_for_timeout(800)
        await page.locator('#sel-tc').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-order').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-batch').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-cand').select_option(index=1)
        await page.wait_for_timeout(2000)
        await page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first.click()
        await page.wait_for_timeout(2000)

        await page.emulate_media(media='print')
        info = await page.evaluate('''() => {
            const h = document.querySelector('.cpass-statement-header');
            const s = document.querySelector('.cpass-statement-sheet');
            const m = document.querySelector('.l1-statement-modal-card');
            const b = document.body;
            const logo = document.querySelector('.cpass-header-logo');
            const title = document.querySelector('.cpass-header-title');
            const meta = document.querySelector('.cpass-header-meta');

            const getRect = (el) => el ? {
                x: el.getBoundingClientRect().x,
                width: el.getBoundingClientRect().width,
                left: el.getBoundingClientRect().left,
                right: el.getBoundingClientRect().right
            } : null;

            return {
                bodyW: b.getBoundingClientRect().width,
                modalCard: getRect(m),
                sheet: getRect(s),
                header: getRect(h),
                logo: getRect(logo),
                title: getRect(title),
                meta: getRect(meta),
                headerComputedDisplay: window.getComputedStyle(h).display,
                sheetComputedPadding: window.getComputedStyle(s).padding,
            };
        }''')
        import pprint
        pprint.pprint(info)
        await b.close()

if __name__ == '__main__':
    asyncio.run(check())

