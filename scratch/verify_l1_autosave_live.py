import asyncio
import os
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"
BASE_URL = "http://localhost:5173"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True
        )

        ctx = await browser.new_context(viewport={"width": 1440, "height": 950})
        page = await ctx.new_page()

        print("\n=======================================================")
        print("  STEP 1: LOGIN AS L1 PLACEMENT COORDINATOR")
        print("=======================================================")
        await page.goto(f"{BASE_URL}", wait_until="networkidle")

        tab_btn = page.locator('button[data-r="L1"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page.wait_for_timeout(300)

        await page.fill("input#em", "appe@synchroserve.com")
        await page.fill("input#pw", "appe@cpass")
        await page.locator("form#lf button.btn").first.click()
        await page.wait_for_timeout(3000)

        await page.wait_for_selector(".l1-dashboard", timeout=15000)
        print("✓ Logged into L1 Dashboard successfully")

        print("\n=======================================================")
        print("  STEP 2: SELECT CANDIDATE VIA CASCADE")
        print("=======================================================")
        tc_select = page.locator("select#sel-tc")
        await tc_select.wait_for(state="visible", timeout=8000)
        await tc_select.select_option(value="1000595")
        await page.wait_for_timeout(1000)

        order_select = page.locator("select#sel-order")
        await order_select.wait_for(state="visible", timeout=8000)
        await order_select.select_option(index=1)
        await page.wait_for_timeout(1000)

        batch_select = page.locator("select#sel-batch")
        await batch_select.wait_for(state="visible", timeout=8000)
        await batch_select.select_option(index=1)
        await page.wait_for_timeout(1000)

        cand_select = page.locator("select#sel-cand")
        await cand_select.wait_for(state="visible", timeout=8000)
        cand_opts = await cand_select.locator("option").all_inner_texts()
        print(f"Loaded {len(cand_opts)} candidate options")
        
        # Select first candidate in batch
        await cand_select.select_option(index=1)
        selected_cand_val = await cand_select.input_value()
        selected_cand_text = await cand_select.locator(f"option[value='{selected_cand_val}']").inner_text()
        print(f"Selected Candidate: {selected_cand_text} (ID: {selected_cand_val})")
        
        # Wait for candidate summary card to be visible
        await page.wait_for_selector(".l1-cand-summary-card", timeout=15000)
        print("✓ Candidate summary card loaded on screen")

        print("\n=======================================================")
        print("  STEP 3: FILL EMPLOYER DETAILS & TRIGGER DEBOUNCED AUTOSAVE")
        print("=======================================================")
        emp_name_input = page.locator("input[placeholder='e.g. Acme Tech Solutions']").first
        await emp_name_input.wait_for(state="visible", timeout=5000)
        await emp_name_input.fill("Apex Technologies Private Limited")
        print("✓ Filled Employer Name: 'Apex Technologies Private Limited'")

        desig_input = page.locator("input[placeholder='e.g. Junior Technician']").first
        await desig_input.fill("Junior Quality Analyst")
        print("✓ Filled Designation: 'Junior Quality Analyst'")

        ctc_input = page.locator("input[placeholder='0']").first
        await ctc_input.fill("26500")
        print("✓ Filled Monthly CTC: '26500'")

        # Wait 2.5 seconds for debounced autosave to trigger and complete
        print("Waiting 2.5s for debounced autosave (1.5s debounce + network)...")
        await page.wait_for_timeout(2500)

        # Verify Autosave badge in UI
        badge = page.locator(".l1-autosave-badge")
        await badge.first.wait_for(state="visible", timeout=5000)
        badge_text = await badge.first.inner_text()
        print(f"✓ Autosave UI Badge Text: '{badge_text}'")
        assert "All changes saved" in badge_text, f"Expected 'All changes saved' in badge, got '{badge_text}'"

        # Capture screenshot of autosaved badge
        screenshot_autosave_path = os.path.join(ARTIFACT_DIR, "screenshot_l1_autosave_badge.png")
        await page.screenshot(path=screenshot_autosave_path, full_page=False)
        print(f"✓ Saved screenshot: {screenshot_autosave_path}")

        print("\n=======================================================")
        print("  STEP 4: EDIT SALARY DETAILS & VERIFY NET SALARY CALCULATION & AUTOSAVE")
        print("=======================================================")
        gross_input = page.locator("input[aria-label='Month 1 Gross Salary']").first
        await gross_input.wait_for(state="visible", timeout=5000)
        await gross_input.fill("24000")
        print("✓ Filled Gross Salary: 24000")

        ded_input = page.locator("input[aria-label='Month 1 Deductions']").first
        await ded_input.fill("1800")
        print("✓ Filled Deductions: 1800")

        # Verify net salary auto-calculated
        net_input = page.locator("input[aria-label='Month 1 Net Salary']").first
        net_val = await net_input.input_value()
        print(f"✓ Auto-calculated Net Salary: {net_val}")
        assert net_val == "22200", f"Expected Net Salary 22200, got {net_val}"

        # Wait for debounced autosave
        await page.wait_for_timeout(2500)
        badge_text_sal = await badge.first.inner_text()
        print(f"✓ Autosave UI Badge After Salary Edit: '{badge_text_sal}'")
        assert "All changes saved" in badge_text_sal

        print("\n=======================================================")
        print("  STEP 5: REFRESH PAGE & VERIFY DATA PERSISTENCE ACROSS SESSIONS")
        print("=======================================================")
        print("Reloading page to simulate fresh browser session...")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(3000)

        # Re-select Candidate
        tc_sel = page.locator("select#sel-tc")
        await tc_sel.select_option(value="1000595")
        await page.wait_for_timeout(1000)

        ord_sel = page.locator("select#sel-order")
        await ord_sel.select_option(index=1)
        await page.wait_for_timeout(1000)

        bat_sel = page.locator("select#sel-batch")
        await bat_sel.select_option(index=1)
        await page.wait_for_timeout(1000)

        c_sel = page.locator("select#sel-cand")
        await c_sel.select_option(value=selected_cand_val)
        await page.wait_for_selector(".l1-cand-summary-card", timeout=15000)
        await page.wait_for_timeout(2000)

        # Verify persisted values
        restored_emp = await page.locator("input[placeholder='e.g. Acme Tech Solutions']").first.input_value()
        print(f"Restored Employer Name after refresh: '{restored_emp}'")
        assert restored_emp == "Apex Technologies Private Limited", f"Expected 'Apex Technologies Private Limited', got '{restored_emp}'"

        restored_desig = await page.locator("input[placeholder='e.g. Junior Technician']").first.input_value()
        print(f"Restored Designation after refresh: '{restored_desig}'")
        assert restored_desig == "Junior Quality Analyst", f"Expected 'Junior Quality Analyst', got '{restored_desig}'"

        restored_ctc = await page.locator("input[placeholder='0']").first.input_value()
        print(f"Restored Monthly CTC after refresh: '{restored_ctc}'")
        assert restored_ctc == "26500", f"Expected '26500', got '{restored_ctc}'"

        restored_gross = await page.locator("input[aria-label='Month 1 Gross Salary']").first.input_value()
        print(f"Restored Month 1 Gross Salary: '{restored_gross}'")
        assert restored_gross == "24000", f"Expected '24000', got '{restored_gross}'"

        restored_ded = await page.locator("input[aria-label='Month 1 Deductions']").first.input_value()
        print(f"Restored Month 1 Deductions: '{restored_ded}'")
        assert restored_ded == "1800", f"Expected '1800', got '{restored_ded}'"

        restored_net = await page.locator("input[aria-label='Month 1 Net Salary']").first.input_value()
        print(f"Restored Month 1 Net Salary: '{restored_net}'")
        assert restored_net == "22200", f"Expected '22200', got '{restored_net}'"

        print("✓ VERIFIED: All Employer and Salary information successfully persisted without manual save!")

        screenshot_restored_path = os.path.join(ARTIFACT_DIR, "screenshot_l1_draft_restored.png")
        await page.screenshot(path=screenshot_restored_path, full_page=False)
        print(f"✓ Saved screenshot: {screenshot_restored_path}")

        print("\n=======================================================")
        print("  ALL LIVE L1 AUTOSAVE & PERSISTENCE VERIFICATIONS PASSED (100%)")
        print("=======================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
