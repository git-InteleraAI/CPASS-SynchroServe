import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='msedge', headless=True)
        page = await b.new_page()
        await page.goto('http://localhost:5173')
        await page.wait_for_selector('button[data-r="L1"]')
        await page.locator('button[data-r="L1"]').click()
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.click('button.btn')
        await page.wait_for_selector('.l1-dashboard', timeout=15000)
        print("Logged in")
        
        tc_sel = page.locator('select#sel-tc')
        await tc_sel.select_option(value='1000595')
        await page.wait_for_timeout(1000)
        
        ord_sel = page.locator('select#sel-order')
        await ord_sel.select_option(index=1)
        await page.wait_for_timeout(1000)
        
        bat_sel = page.locator('select#sel-batch')
        bat_opts = await bat_sel.locator('option').all()
        for i, o in enumerate(bat_opts):
            print(f"Batch {i}: val='{await o.get_attribute('value')}', text='{await o.inner_text()}'")
        
        # Select first real batch (index=1)
        await bat_sel.select_option(index=1)
        await page.wait_for_timeout(1500)
        
        cand_sel = page.locator('select#sel-cand')
        cand_opts = await cand_sel.locator('option').all()
        print(f"Candidates count in batch index 1: {len(cand_opts)}")
        for i, o in enumerate(cand_opts[:5]):
            print(f"Cand {i}: val='{await o.get_attribute('value')}', text='{await o.inner_text()}'")
            
        await b.close()

if __name__ == "__main__":
    asyncio.run(run())

