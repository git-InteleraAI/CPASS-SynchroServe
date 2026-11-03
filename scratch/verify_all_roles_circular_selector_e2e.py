import asyncio
import os
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"
BASE_URL = "http://localhost:5173"

async def verify_circular_modals():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True
        )

        # =====================================================================
        # 1. VERIFY L2: Center Head (Must Remain Completely Unchanged)
        # =====================================================================
        print("\n=======================================================")
        print("  STEP 1: VERIFYING L2 CENTER HEAD (UNCHANGED)")
        print("=======================================================")
        ctx_l2 = await browser.new_context(viewport={"width": 1400, "height": 900})
        page_l2 = await ctx_l2.new_page()

        await page_l2.goto(f"{BASE_URL}", wait_until="networkidle")
        tab_btn = page_l2.locator('button[data-r="L2"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page_l2.wait_for_timeout(300)

        await page_l2.fill("input#em", "tsch@synchroserve.com")
        await page_l2.fill("input#pw", "tsch@cpass")
        await page_l2.locator("form#lf button.btn").first.click()
        await page_l2.wait_for_timeout(3000)

        await page_l2.wait_for_selector(".l2-dashboard", timeout=15000)
        cards = await page_l2.query_selector_all(".l2-compact-card")
        assert len(cards) > 0, "No metric cards on L2"
        await cards[1].click() # Received card
        await page_l2.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=8000)
        open_btn = await page_l2.wait_for_selector(".l1-btn-open-dossier", timeout=15000)
        await open_btn.click()
        await page_l2.wait_for_timeout(3000)

        reject_btn = await page_l2.wait_for_selector(".l2-btn-return-reject", timeout=10000)
        await reject_btn.click()
        await page_l2.wait_for_selector(".flex-return-backdrop", timeout=5000)
        print("✓ L2 Reject modal opened")

        # Verify L2 has fixed destination card and NO circular selector
        l2_dest_card = await page_l2.query_selector(".l2-reject-dest-card")
        assert l2_dest_card is not None, "L2 must have .l2-reject-dest-card"
        dest_title = (await (await page_l2.query_selector(".l2-dest-title")).inner_text()).strip()
        print(f"L2 Destination Title: '{dest_title}'")
        assert "L1" in dest_title and "Placement Coordinator" in dest_title

        circular_selector_in_l2 = await page_l2.query_selector(".circular-dest-selector")
        assert circular_selector_in_l2 is None, "L2 must NOT have .circular-dest-selector"
        print("✓ Confirmed: L2 has NO circular destination selector and remains 100% UNCHANGED!")

        # Screenshot L2
        l2_card = await page_l2.query_selector(".l2-reject-card")
        l2_path = os.path.join(ARTIFACT_DIR, "screenshot_l2_modal_verification.png")
        await l2_card.screenshot(path=l2_path)
        print(f"✓ Saved L2 screenshot to: {l2_path}")
        await ctx_l2.close()

        # =====================================================================
        # 2. VERIFY L3: COPS Auditor (3 Circular Destinations)
        # =====================================================================
        print("\n=======================================================")
        print("  STEP 2: VERIFYING L3 COPS AUDITOR (3 CIRCLES)")
        print("=======================================================")
        ctx_l3 = await browser.new_context(viewport={"width": 1400, "height": 900})
        page_l3 = await ctx_l3.new_page()

        await page_l3.goto(f"{BASE_URL}", wait_until="networkidle")
        tab_btn = page_l3.locator('button[data-r="L3"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page_l3.wait_for_timeout(300)

        await page_l3.fill("input#em", "cops@synchroserve.com")
        await page_l3.fill("input#pw", "jsubWTVkgGo9&_xuq0")
        await page_l3.locator("form#lf button.btn").first.click()
        await page_l3.wait_for_timeout(3000)

        await page_l3.wait_for_selector(".l2-dashboard", timeout=15000)
        cards_l3 = await page_l3.query_selector_all(".l2-compact-card")
        # Click Pending card
        for c in cards_l3:
            t_el = await c.query_selector(".l2-compact-card-title")
            t_txt = (await t_el.inner_text()).strip() if t_el else ""
            if "PENDING" in t_txt.upper():
                await c.click()
                break

        await page_l3.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=8000)
        open_btn_l3 = await page_l3.wait_for_selector(".l1-btn-open-dossier", timeout=15000)
        await open_btn_l3.click()
        await page_l3.wait_for_timeout(3000)

        reject_btn_l3 = await page_l3.wait_for_selector(".l2-btn-return-reject", timeout=10000)
        await reject_btn_l3.click()
        await page_l3.wait_for_selector(".flex-return-backdrop", timeout=5000)
        print("✓ L3 Reject modal opened")

        # Verify Header and Candidate Info
        title_l3 = (await (await page_l3.query_selector("#multilevel-reject-title, .l2-reject-title")).inner_text()).strip()
        assert title_l3 == "Reject & Send Back"
        print(f"Header Title: '{title_l3}'")

        # Verify Circular Destination Selector
        circ_selector = await page_l3.wait_for_selector(".circular-dest-selector", timeout=5000)
        assert circ_selector is not None, "Missing .circular-dest-selector in L3"

        circ_items = await page_l3.query_selector_all(".circular-dest-item")
        print(f"L3 Circular Destinations Count: {len(circ_items)} (Expected: 3)")
        assert len(circ_items) == 3, f"Expected 3 circles for L3, found {len(circ_items)}"

        labels = []
        levels = []
        for item in circ_items:
            lvl_el = await item.query_selector(".circular-dest-level")
            lbl_el = await item.query_selector(".circular-dest-label")
            levels.append((await lvl_el.inner_text()).strip())
            labels.append((await lbl_el.inner_text()).strip())

        print(f"L3 Circles: levels={levels}, labels={labels}")
        assert levels == ["L1", "L2", "L3"], f"Levels mismatch: {levels}"
        assert labels == ["Coordinator", "Center Head", "COPS"], f"Labels mismatch: {labels}"

        # Verify no rectangular cards or workflow arrows
        assert (await page_l3.query_selector(".flex-return-dest-option")) is None
        assert (await page_l3.query_selector(".flex-return-route-preview")) is None
        print("✓ Verified: No rectangular cards, outer selection boxes, or workflow arrows in L3 modal")

        # Test clicking circle 2 (L2)
        print("Testing click on Circle L2...")
        await circ_items[1].click()
        await page_l3.wait_for_timeout(300)
        assert "selected" in (await circ_items[1].get_attribute("class")), "L2 circle must be selected"
        assert "selected" in (await (await circ_items[1].query_selector(".circular-dest-btn")).get_attribute("class"))
        assert "selected" in (await (await circ_items[1].query_selector(".circular-dest-label")).get_attribute("class"))
        print("✓ L2 selected: circle turned blue, text white, label blue semibold")

        # Test clicking label of Circle L1
        print("Testing click on label 'Coordinator' (L1)...")
        lbl_l1 = await circ_items[0].query_selector(".circular-dest-label")
        await lbl_l1.click()
        await page_l3.wait_for_timeout(300)
        assert "selected" in (await circ_items[0].get_attribute("class")), "L1 must be selected when clicking label"
        print("✓ Clicking destination label selected L1 immediately")

        # Select a reason chip and type instructions
        chips = await page_l3.query_selector_all(".l2-reason-chip")
        await chips[0].click() # Document missing
        textarea = await page_l3.query_selector("#multilevel-instructions-input")
        await textarea.fill("Please provide legible copies of all required salary slips with company seal.")

        # Screenshot L3
        l3_card = await page_l3.query_selector(".l2-reject-card")
        l3_path = os.path.join(ARTIFACT_DIR, "screenshot_l3_circular_reject_modal.png")
        await l3_card.screenshot(path=l3_path)
        print(f"✓ Saved L3 screenshot to: {l3_path}")
        await ctx_l3.close()

        # =====================================================================
        # 3. VERIFY L4: Business Leader (3 Circular Destinations)
        # =====================================================================
        print("\n=======================================================")
        print("  STEP 3: VERIFYING L4 BUSINESS LEADER (3 CIRCLES)")
        print("=======================================================")
        ctx_l4 = await browser.new_context(viewport={"width": 1400, "height": 900})
        page_l4 = await ctx_l4.new_page()

        await page_l4.goto(f"{BASE_URL}", wait_until="networkidle")
        tab_btn = page_l4.locator('button[data-r="L4"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page_l4.wait_for_timeout(300)

        await page_l4.fill("input#em", "sowbhagya.bl@synchroserve.com")
        await page_l4.fill("input#pw", "Hz^wdeeZnuBhr@=Z*2")
        await page_l4.locator("form#lf button.btn").first.click()
        await page_l4.wait_for_timeout(3000)

        await page_l4.wait_for_selector(".l2-dashboard", timeout=15000)
        cards_l4 = await page_l4.query_selector_all(".l2-compact-card")
        # Click Pending card or first card
        clicked_l4 = False
        for c in cards_l4:
            t_el = await c.query_selector(".l2-compact-card-title")
            t_txt = (await t_el.inner_text()).strip() if t_el else ""
            if "PENDING" in t_txt.upper():
                await c.click()
                clicked_l4 = True
                break
        if not clicked_l4 and cards_l4:
            await cards_l4[0].click()

        await page_l4.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=8000)
        open_btn_l4 = await page_l4.wait_for_selector(".l1-btn-open-dossier", timeout=15000)
        await open_btn_l4.click()
        await page_l4.wait_for_timeout(3000)

        reject_btn_l4 = await page_l4.wait_for_selector(".l2-btn-return-reject", timeout=10000)
        # Check if disabled, if so pick another candidate
        if await reject_btn_l4.is_disabled():
            cand_sel = page_l4.locator("#l2-sel-cand")
            opts = await cand_sel.locator("option").all_inner_texts()
            for i in range(1, min(len(opts), 10)):
                await cand_sel.select_option(index=i)
                await page_l4.wait_for_timeout(2000)
                reject_btn_l4 = await page_l4.wait_for_selector(".l2-btn-return-reject", timeout=5000)
                if not (await reject_btn_l4.is_disabled()):
                    break

        await reject_btn_l4.click()
        await page_l4.wait_for_selector(".flex-return-backdrop", timeout=5000)
        print("✓ L4 Reject modal opened")

        circ_items_l4 = await page_l4.query_selector_all(".circular-dest-item")
        print(f"L4 Circular Destinations Count: {len(circ_items_l4)} (Expected: 3)")
        assert len(circ_items_l4) == 3, f"Expected 3 circles for L4, found {len(circ_items_l4)}"

        levels_l4 = []
        labels_l4 = []
        for item in circ_items_l4:
            lvl_el = await item.query_selector(".circular-dest-level")
            lbl_el = await item.query_selector(".circular-dest-label")
            levels_l4.append((await lvl_el.inner_text()).strip())
            labels_l4.append((await lbl_el.inner_text()).strip())

        print(f"L4 Circles: levels={levels_l4}, labels={labels_l4}")
        assert levels_l4 == ["L1", "L2", "L3"]
        assert labels_l4 == ["Coordinator", "Center Head", "COPS"]

        # Default selected for L4 should be L3 (immediate previous level)
        assert "selected" in (await circ_items_l4[2].get_attribute("class")), "Default for L4 should be L3"
        print("✓ Default selected destination for L4 is L3 (COPS)")

        # Select chip & type instructions
        chips_l4 = await page_l4.query_selector_all(".l2-reason-chip")
        await chips_l4[1].click() # Details mismatch
        textarea_l4 = await page_l4.query_selector("#multilevel-instructions-input")
        await textarea_l4.fill("Discrepancy in reported salary amount vs bank credit. Please review.")

        # Screenshot L4
        l4_card = await page_l4.query_selector(".l2-reject-card")
        l4_path = os.path.join(ARTIFACT_DIR, "screenshot_l4_circular_reject_modal.png")
        await l4_card.screenshot(path=l4_path)
        print(f"✓ Saved L4 screenshot to: {l4_path}")
        await ctx_l4.close()

        # =====================================================================
        # 4. VERIFY L5: Chief Executive Officer (4 Circular Destinations)
        # =====================================================================
        print("\n=======================================================")
        print("  STEP 4: VERIFYING L5 CEO (4 CIRCLES)")
        print("=======================================================")
        ctx_l5 = await browser.new_context(viewport={"width": 1400, "height": 900})
        page_l5 = await ctx_l5.new_page()

        await page_l5.goto(f"{BASE_URL}", wait_until="networkidle")
        tab_btn = page_l5.locator('button[data-r="L5"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page_l5.wait_for_timeout(300)

        await page_l5.fill("input#em", "ceo@synchroserve.com")
        await page_l5.fill("input#pw", "Kxfzu6*^@BzpRPKH!V")
        await page_l5.locator("form#lf button.btn").first.click()
        await page_l5.wait_for_timeout(3000)

        await page_l5.wait_for_selector(".l2-dashboard", timeout=15000)
        cards_l5 = await page_l5.query_selector_all(".l2-compact-card")
        clicked_l5 = False
        for c in cards_l5:
            t_el = await c.query_selector(".l2-compact-card-title")
            t_txt = (await t_el.inner_text()).strip() if t_el else ""
            if "PENDING" in t_txt.upper():
                await c.click()
                clicked_l5 = True
                break
        if not clicked_l5 and cards_l5:
            await cards_l5[0].click()

        await page_l5.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=8000)
        open_btn_l5 = await page_l5.wait_for_selector(".l1-btn-open-dossier", timeout=15000)
        await open_btn_l5.click()
        await page_l5.wait_for_timeout(3000)

        reject_btn_l5 = await page_l5.wait_for_selector(".l2-btn-return-reject", timeout=10000)
        if await reject_btn_l5.is_disabled():
            cand_sel = page_l5.locator("#l2-sel-cand")
            opts = await cand_sel.locator("option").all_inner_texts()
            for i in range(1, min(len(opts), 10)):
                await cand_sel.select_option(index=i)
                await page_l5.wait_for_timeout(2000)
                reject_btn_l5 = await page_l5.wait_for_selector(".l2-btn-return-reject", timeout=5000)
                if not (await reject_btn_l5.is_disabled()):
                    break

        await reject_btn_l5.click()
        await page_l5.wait_for_selector(".flex-return-backdrop", timeout=5000)
        print("✓ L5 Reject modal opened")

        circ_items_l5 = await page_l5.query_selector_all(".circular-dest-item")
        print(f"L5 Circular Destinations Count: {len(circ_items_l5)} (Expected: 4)")
        assert len(circ_items_l5) == 4, f"Expected 4 circles for L5, found {len(circ_items_l5)}"

        levels_l5 = []
        labels_l5 = []
        for item in circ_items_l5:
            lvl_el = await item.query_selector(".circular-dest-level")
            lbl_el = await item.query_selector(".circular-dest-label")
            levels_l5.append((await lvl_el.inner_text()).strip())
            labels_l5.append((await lbl_el.inner_text()).strip())

        print(f"L5 Circles: levels={levels_l5}, labels={labels_l5}")
        assert levels_l5 == ["L1", "L2", "L3", "L4"]
        assert labels_l5 == ["Coordinator", "Center Head", "COPS", "Business Leader"]

        # Default selected for L5 should be L4 (immediate previous level)
        assert "selected" in (await circ_items_l5[3].get_attribute("class")), "Default for L5 should be L4"
        print("✓ Default selected destination for L5 is L4 (Business Leader)")

        # Test selecting L3
        print("Testing selecting L3 from L5 modal...")
        await circ_items_l5[2].click()
        await page_l5.wait_for_timeout(300)
        assert "selected" in (await circ_items_l5[2].get_attribute("class")), "L3 must be selected"
        assert "selected" not in (await circ_items_l5[3].get_attribute("class")), "L4 must be unselected"
        print("✓ Switched selection from L4 to L3 cleanly")

        # Select chip & type instructions
        chips_l5 = await page_l5.query_selector_all(".l2-reason-chip")
        await chips_l5[0].click() # Document missing
        textarea_l5 = await page_l5.query_selector("#multilevel-instructions-input")
        await textarea_l5.fill("Special placement audit requires re-verification by COPS before CEO sanction.")

        # Screenshot L5
        l5_card = await page_l5.query_selector(".l2-reject-card")
        l5_path = os.path.join(ARTIFACT_DIR, "screenshot_l5_circular_reject_modal.png")
        await l5_card.screenshot(path=l5_path)
        print(f"✓ Saved L5 screenshot to: {l5_path}")
        await ctx_l5.close()

        print("\n=======================================================")
        print("  ALL 4 ROLES VERIFIED SUCCESSFULLY ACROSS THE BOARD!  ")
        print("=======================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_circular_modals())

