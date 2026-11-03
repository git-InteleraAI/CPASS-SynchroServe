import asyncio
from playwright.async_api import async_playwright

async def test_l3():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto("http://localhost:5173", wait_until="networkidle")
        tab = page.locator('button[data-r="L3"]')
        await tab.click()
        await page.wait_for_timeout(500)
        await page.fill("input#em", "cops@synchroserve.com")
        await page.fill("input#pw", "jsubWTVkgGo9&_xuq0")
        await page.locator("form#lf button.btn").first.click()
        await page.wait_for_timeout(4000)
        url = page.url
        print("Page URL:", url)
        content = await page.content()
        if "err" in content:
            err_el = await page.query_selector(".err, .toast")
            if err_el:
                print("Error on page:", await err_el.inner_text())
        has_dash = await page.query_selector(".l2-dashboard")
        print("Has .l2-dashboard:", has_dash is not None)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_l3())

