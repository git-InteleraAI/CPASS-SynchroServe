import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page()
        await page.goto('http://localhost:5173')
        tab = page.locator('button[data-r="L1"]')
        if await tab.count() > 0:
            await tab.click()
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.click('button.btn')
        await page.wait_for_timeout(4000)
        print('Current URL:', page.url)
        err = await page.locator('.auth-error-msg').all_inner_texts()
        print('Errors:', err)
        body = await page.locator('body').inner_text()
        print('Body:', body[:300].replace('\n', ' '))
        await browser.close()

asyncio.run(run())
