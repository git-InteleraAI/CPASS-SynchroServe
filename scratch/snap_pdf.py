import asyncio
from playwright.async_api import async_playwright

async def snap():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='msedge', headless=True)
        page = await b.new_page(viewport={'width': 1200, 'height': 1600})
        await page.goto(r'file:///C:/Users/Manu Mansoor/.gemini/antigravity/brain/be024e12-79ef-49d3-85b4-648e5272182d/statement_prefer_css.pdf')
        await page.wait_for_timeout(2500)
        await page.screenshot(path=r'C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d\pdf_preview_prefer_css.png')
        await b.close()
        print('Saved pdf_preview_prefer_css.png')

asyncio.run(snap())

