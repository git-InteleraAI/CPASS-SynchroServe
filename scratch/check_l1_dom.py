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
        
        selectors = [
            ".l1-dashboard",
            ".app-layout",
            ".top",
            ".l1-selector-panel",
            ".content-container",
            "select",
        ]
        for sel in selectors:
            cnt = await page.locator(sel).count()
            print(f"Selector '{sel}': {cnt} found")

        # Print all select IDs
        selects = await page.locator("select").all()
        for s in selects:
            sid = await s.get_attribute("id")
            scls = await s.get_attribute("class")
            print(f"Select: id='{sid}', class='{scls}'")

        await browser.close()

asyncio.run(run())

