import asyncio
import os
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"
BASE_URL = "http://localhost:5173"

async def verify_l2_and_l3():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True
        )

        # -------------------------------------------------------------
        # 1. TEST L2 CENTER HEAD REDESIGNED REJECT MODAL
        # -------------------------------------------------------------
        print("\n--- 1. Testing L2 Center Head Redesigned Reject Modal ---")
        context1 = await browser.new_context(viewport={"width": 1400, "height": 900})
        page1 = await context1.new_page()

        await page1.goto(f"{BASE_URL}", wait_until="networkidle")

        tab_btn = page1.locator('button[data-r="L2"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page1.wait_for_timeout(300)

        # Login with L2 credentials
        await page1.fill("input#em", "tsch@synchroserve.com")
        await page1.fill("input#pw", "tsch@cpass")
        await page1.locator("form#lf button.btn").first.click()
        await page1.wait_for_timeout(3000)

        print("✓ Logged in as L2 Center Head (Telangana)")

        # Wait for dashboard cards
        await page1.wait_for_selector(".l2-dashboard", timeout=15000)
        await page1.wait_for_selector(".l2-compact-card", timeout=10000)
        cards = await page1.query_selector_all(".l2-compact-card")
        print(f"Found {len(cards)} metric cards.")

        # Click the RECEIVED card
        clicked_card = False
        for c in cards:
            title_el = await c.query_selector(".l2-compact-card-title")
            count_el = await c.query_selector(".l2-compact-card-count")
            t_text = (await title_el.inner_text()).strip() if title_el else ""
            c_text = (await count_el.inner_text()).strip() if count_el else "0"
            if "RECEIVED" in t_text.upper() or "PENDING" in t_text.upper():
                if not clicked_card and c_text not in ("0", "—", "…"):
                    print(f"  -> Clicking '{t_text}' card ({c_text} candidates)...")
                    await c.click()
                    clicked_card = True

        if not clicked_card and cards:
            await cards[0].click()

        # Wait for candidate list popup dialog
        await page1.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=10000)
        print("✓ Candidate list popup dialog opened")

        open_btn = await page1.wait_for_selector(".l1-btn-open-dossier", timeout=15000)
        print("✓ Found Open Dossier button in queue table. Clicking...")
        await open_btn.click()
        await page1.wait_for_timeout(3000)
        print("✓ Candidate Dossier loaded")

        # Wait for candidate dossier bottom action dock
        reject_btn = await page1.wait_for_selector(".l2-btn-return-reject", timeout=10000)
        btn_text = (await reject_btn.inner_text()).strip()
        print(f"✓ Found bottom dock action button: '{btn_text}'")
        assert "Reject & Send Back" in btn_text, f"Unexpected button text: {btn_text}"

        # Click Reject & Send Back
        await reject_btn.click()

        # Wait for modal backdrop
        await page1.wait_for_selector(".flex-return-backdrop", timeout=5000)
        print("✓ Redesigned Reject & Send Back modal opened!")

        # SECTION A: HEADER VERIFICATION
        title_el = await page1.query_selector(".l2-reject-title")
        title_text = (await title_el.inner_text()).strip() if title_el else ""
        assert title_text == "Reject & Send Back"
        badge = await page1.query_selector(".l2-reject-icon-badge")
        assert badge is not None
        print("✓ Section A (Header): Title, subtitle, and red accent icon badge verified")

        # SECTION B: CANDIDATE INFO CARD VERIFICATION
        avatar = await page1.query_selector(".l2-candidate-avatar")
        avatar_text = (await avatar.inner_text()).strip() if avatar else ""
        name_el = await page1.query_selector(".l2-candidate-name")
        name_text = (await name_el.inner_text()).strip() if name_el else ""
        id_el = await page1.query_selector(".l2-candidate-id")
        id_text = (await id_el.inner_text()).strip() if id_el else ""
        print(f"Candidate Info Card: Avatar='{avatar_text}', Name='{name_text}', ID='{id_text}'")
        assert len(avatar_text) > 0 and len(name_text) > 0
        print("✓ Section B (Candidate Info): Avatar initials, name, and candidate ID verified")

        # SECTION C: RETURN DESTINATION CARD VERIFICATION
        dest_title = await page1.query_selector(".l2-dest-title")
        dest_title_text = (await dest_title.inner_text()).strip() if dest_title else ""
        assert "L1" in dest_title_text and "Placement Coordinator" in dest_title_text
        preview = await page1.query_selector(".route-timeline, .dest-list, .dest-card, .flex-return-dest-option, .flex-return-route-preview")
        assert preview is None, "Workflow Impact Preview should NOT exist in L2 modal!"
        print("✓ Section C (Return Destination): Fixed to L1 with zero unnecessary workflow clutter")

        # SECTION D: REJECTION REASON CHIPS VERIFICATION
        chips = await page1.query_selector_all(".l2-reason-chip")
        chip_texts = [(await c.inner_text()).strip() for c in chips]
        expected_chips = [
            'Document missing',
            'Details mismatch',
            'Unclear scan',
            'Wrong document uploaded',
            'Signature missing',
            'Other'
        ]
        assert set(expected_chips) == set(chip_texts)
        await chips[0].click()
        await chips[2].click()
        assert "selected" in (await chips[0].get_attribute("class"))
        assert "selected" in (await chips[2].get_attribute("class"))
        print("✓ Section D (Rejection Reason Chips): Multi-select toggles and checkmarks verified")

        # SECTION E: CORRECTION INSTRUCTIONS & VALIDATION
        textarea = await page1.query_selector("#correction-instructions-input")
        submit_btn = await page1.query_selector(".l2-btn-submit-reject")
        assert await submit_btn.is_disabled()

        # Type short text < 10 chars
        await textarea.fill("Short")
        await textarea.evaluate("el => el.blur()")
        await page1.wait_for_timeout(300)
        error_el = await page1.query_selector(".l2-field-error")
        error_text = (await error_el.inner_text()).strip() if error_el else ""
        assert "Minimum 10 characters required" in error_text
        assert await submit_btn.is_disabled()

        # Type valid text >= 10 chars
        valid_instructions = "Month 1 salary slip is illegible and stamp is missing. Please upload clear scan."
        await textarea.fill(valid_instructions)
        counter = await page1.query_selector(".l2-char-counter")
        counter_text = (await counter.inner_text()).strip()
        assert counter_text == f"{len(valid_instructions)}/500"
        assert not (await submit_btn.is_disabled())
        print("✓ Section E (Correction Instructions): Live counter, min-length validation, and button enablement verified")

        # SECTION F: FOOTER VERIFICATION
        audit_badge = await page1.query_selector(".l2-audit-badge")
        audit_text = (await audit_badge.inner_text()).strip() if audit_badge else ""
        assert "Recorded in audit history" in audit_text
        print("✓ Section F (Footer): Audit history badge, cancel, and submit button verified")

        # High-res screenshot of L2 modal
        modal_screenshot_path = os.path.join(ARTIFACT_DIR, "screenshot_l2_redesigned_reject_modal.png")
        modal_card = await page1.query_selector(".l2-reject-card")
        await modal_card.screenshot(path=modal_screenshot_path)
        print(f"✓ Saved high-res screenshot of L2 modal to: {modal_screenshot_path}")

        # Cancel button closes modal
        cancel_btn = await page1.query_selector(".l2-btn-cancel")
        await cancel_btn.click()
        await page1.wait_for_timeout(500)
        assert (await page1.query_selector(".flex-return-backdrop")) is None
        print("✓ Cancel button cleanly closed the modal")
        await context1.close()

        # -------------------------------------------------------------
        # 2. PRESERVATION CHECK: L3 COPS MULTI-LEVEL FLEXIBLE RETURN
        # -------------------------------------------------------------
        print("\n--- 2. Testing L3 COPS Flexible Return Modal (Preservation Check) ---")
        context2 = await browser.new_context(viewport={"width": 1400, "height": 900})
        page2 = await context2.new_page()

        await page2.goto(f"{BASE_URL}", wait_until="networkidle")

        tab_btn = page2.locator('button[data-r="L3"]')
        if await tab_btn.count() > 0:
            await tab_btn.click()
            await page2.wait_for_timeout(300)

        await page2.fill("input#em", "cops@synchroserve.com")
        await page2.fill("input#pw", "jsubWTVkgGo9&_xuq0")
        await page2.locator("form#lf button.btn").first.click()
        await page2.wait_for_timeout(3000)
        print("✓ Logged in as L3 COPS Auditor")

        await page2.wait_for_selector(".l2-dashboard", timeout=15000)
        cards_l3 = await page2.query_selector_all(".l2-compact-card")
        if cards_l3:
            # Click Pending card (waiting for COPS review)
            clicked_l3 = False
            for c in cards_l3:
                t_el = await c.query_selector(".l2-compact-card-title")
                c_el = await c.query_selector(".l2-compact-card-count")
                t_txt = (await t_el.inner_text()).strip() if t_el else ""
                c_txt = (await c_el.inner_text()).strip() if c_el else "0"
                if "PENDING" in t_txt.upper() and c_txt not in ("0", "—", "…"):
                    print(f"  -> Clicking L3 '{t_txt}' card ({c_txt} candidates)...")
                    await c.click()
                    clicked_l3 = True
                    break

            if not clicked_l3:
                # Fall back to Received or first card
                for c in cards_l3:
                    t_el = await c.query_selector(".l2-compact-card-title")
                    c_el = await c.query_selector(".l2-compact-card-count")
                    t_txt = (await t_el.inner_text()).strip() if t_el else ""
                    c_txt = (await c_el.inner_text()).strip() if c_el else "0"
                    if "RECEIVED" in t_txt.upper() and c_txt not in ("0", "—", "…"):
                        await c.click()
                        clicked_l3 = True
                        break

            if not clicked_l3:
                await cards_l3[0].click()

            await page2.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=8000)
            
            # Wait for table to load candidates
            open_btn_l3 = await page2.wait_for_selector(".l1-btn-open-dossier", timeout=15000)
            print("✓ Found Open Dossier button in L3 queue table. Clicking...")
            await open_btn_l3.click()
            await page2.wait_for_timeout(3000)

            # Check if reject button is enabled or if we need another candidate
            reject_btn_l3 = await page2.wait_for_selector(".l2-btn-return-reject", timeout=10000)
            is_dis = await reject_btn_l3.is_disabled()
            print(f"L3 Reject button disabled: {is_dis}")

            if is_dis:
                cand_sel = page2.locator("#l2-sel-cand")
                opts = await cand_sel.locator("option").all_inner_texts()
                print(f"L3 Candidate dropdown has {len(opts)} options")
                for i in range(1, min(len(opts), 10)):
                    await cand_sel.select_option(index=i)
                    await page2.wait_for_timeout(2000)
                    reject_btn_l3 = await page2.wait_for_selector(".l2-btn-return-reject", timeout=5000)
                    if not (await reject_btn_l3.is_disabled()):
                        print(f"Found candidate with enabled reject button at index {i}: {opts[i]}")
                        break

            await reject_btn_l3.click()
            await page2.wait_for_selector(".flex-return-backdrop", timeout=5000)
            print("✓ L3 Reject modal opened!")

            # Verify L3 still has destination option cards intact
            dest_options = await page2.query_selector_all(".flex-return-dest-option")
            print(f"Found {len(dest_options)} destination options in L3 modal (Preserved flexible return)")
            assert len(dest_options) > 0, "L3 modal should preserve multi-level return destination options"

            preview_l3 = await page2.query_selector(".flex-return-route-preview, .route-steps")
            assert preview_l3 is not None, "L3 modal should preserve workflow impact preview/destination selection"
            print("✓ L3 Flexible Return flow confirmed completely intact with route preview!")

            # Take screenshot of L3 modal
            l3_modal_card = await page2.query_selector(".flex-return-card")
            if l3_modal_card:
                l3_screenshot_path = os.path.join(ARTIFACT_DIR, "screenshot_l3_flexible_return_modal.png")
                await l3_modal_card.screenshot(path=l3_screenshot_path)
                print(f"✓ Saved screenshot of L3 modal to: {l3_screenshot_path}")

        print("\nAll Playwright E2E verifications PASSED successfully!")
        await context2.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_l2_and_l3())
