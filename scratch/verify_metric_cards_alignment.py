import asyncio
import os
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"
BASE_URL = "http://localhost:5173"

ROLES_TO_VERIFY = [
    {
        "role": "L2",
        "name": "L2 Center Head (CH)",
        "tab": "L2",
        "email": "tsch@synchroserve.com",
        "password": "tsch@cpass",
        "expected_order": ["TOTAL", "RECEIVED", "RECOMMENDED", "REJECTED", "PENDING"],
        "screenshot_name": "screenshot_l2_metric_cards_aligned.png",
        "is_reference": True
    },
    {
        "role": "L3",
        "name": "L3 COPS Auditor",
        "tab": "L3",
        "email": "cops@synchroserve.com",
        "password": "jsubWTVkgGo9&_xuq0",
        "expected_order": ["TOTAL", "RECEIVED", "VERIFIED", "REJECTED", "PENDING"],
        "screenshot_name": "screenshot_l3_metric_cards_aligned.png",
        "is_reference": False
    },
    {
        "role": "L4",
        "name": "L4 Business Leader (BL)",
        "tab": "L4",
        "email": "sowbhagya.bl@synchroserve.com",
        "password": "Hz^wdeeZnuBhr@=Z*2",
        "expected_order": ["TOTAL", "RECEIVED", "BL APPROVED", "REJECTED", "PENDING"],
        "screenshot_name": "screenshot_l4_metric_cards_aligned.png",
        "is_reference": False
    },
    {
        "role": "L5",
        "name": "L5 CEO",
        "tab": "L5",
        "email": "ceo@synchroserve.com",
        "password": "Kxfzu6*^@BzpRPKH!V",
        "expected_order": ["TOTAL", "RECEIVED", "SANCTIONED", "REJECTED", "PENDING"],
        "screenshot_name": "screenshot_l5_metric_cards_aligned.png",
        "is_reference": False
    }
]

async def verify_metric_cards():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True
        )

        overall_results = []

        for config in ROLES_TO_VERIFY:
            role = config["role"]
            role_name = config["name"]
            print(f"\n=======================================================")
            print(f"  VERIFYING: {role_name}")
            print(f"=======================================================")

            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # Login
            await page.goto(f"{BASE_URL}", wait_until="networkidle")
            tab_btn = page.locator(f'button[data-r="{config["tab"]}"]')
            if await tab_btn.count() > 0:
                await tab_btn.click()
                await page.wait_for_timeout(300)

            await page.fill("input#em", config["email"])
            await page.fill("input#pw", config["password"])
            await page.locator("form#lf button.btn").first.click()
            await page.wait_for_timeout(3000)

            # Wait for dashboard cards
            await page.wait_for_selector(".l2-dashboard", timeout=15000)
            await page.wait_for_selector(".l2-compact-summary-row", timeout=15000)
            cards = await page.query_selector_all(".l2-compact-card")
            print(f"Found {len(cards)} compact metric cards.")
            assert len(cards) == 5, f"Expected exactly 5 cards, got {len(cards)}"

            # 1. Inspect titles and values
            card_data = []
            for i, card in enumerate(cards):
                title_el = await card.query_selector(".l2-compact-card-title")
                value_el = await card.query_selector(".l2-compact-card-count")
                title = (await title_el.inner_text()).strip() if title_el else ""
                value = (await value_el.inner_text()).strip() if value_el else ""
                box = await card.bounding_box()
                card_data.append({
                    "index": i + 1,
                    "title": title,
                    "value": value,
                    "box": box
                })
                print(f"  Card {i+1}: '{title}' | Count: {value} | x={box['x']:.1f}, y={box['y']:.1f}, w={box['width']:.1f}, h={box['height']:.1f}")

            actual_titles = [c["title"].upper() for c in card_data]
            expected_titles = [t.upper() for t in config["expected_order"]]

            print(f"  Actual Order  : {actual_titles}")
            print(f"  Expected Order: {expected_titles}")
            assert actual_titles == expected_titles, f"Order mismatch in {role}!\nActual: {actual_titles}\nExpected: {expected_titles}"
            print(f"  ✓ CARD ORDER MATCHES PERFECTLY!")

            # 2. Check desktop single-row alignment
            # In a single row, all cards have virtually the same Y (within 2px)
            y_coords = [c["box"]["y"] for c in card_data]
            y_diff = max(y_coords) - min(y_coords)
            assert y_diff < 3.0, f"Cards not on single row! Max y-diff: {y_diff}"
            print(f"  ✓ Single row alignment verified (Y coordinate variance: {y_diff:.2f}px)")

            # Check equal widths (within 2px for subpixel/grid rounding)
            widths = [c["box"]["width"] for c in card_data]
            w_diff = max(widths) - min(widths)
            assert w_diff < 3.0, f"Card widths not equal! Widths: {widths}"
            print(f"  ✓ Equal card widths verified (Widths: {[round(w, 1) for w in widths]}, max variance: {w_diff:.2f}px)")

            # Check consistent heights
            heights = [c["box"]["height"] for c in card_data]
            h_diff = max(heights) - min(heights)
            assert h_diff < 3.0, f"Card heights not consistent! Heights: {heights}"
            print(f"  ✓ Consistent card heights verified (Height: {round(heights[0], 1)}px)")

            # 3. Verify interactive card clicking / filter popup
            # Click the 5th card (PENDING) and check popup opens
            pending_card = cards[4]
            await pending_card.click()
            await page.wait_for_selector(".l1-modal-backdrop, .l1-cand-popup-dialog", timeout=8000)
            popup_title_el = await page.query_selector("#review-popup-title")
            popup_title = (await popup_title_el.inner_text()).strip() if popup_title_el else ""
            print(f"  Clicked 5th Card (PENDING): Modal popup opened with title: '{popup_title}'")
            assert "PENDING" in popup_title.upper(), f"Popup title did not contain PENDING: {popup_title}"

            # Close popup
            close_btn = await page.query_selector(".l1-popup-close-btn")
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(500)
            print(f"  ✓ PENDING card interaction & filter popup works seamlessly")

            # 4. Capture screenshot of the summary row
            summary_row = await page.query_selector(".l2-compact-summary-row")
            screenshot_path = os.path.join(ARTIFACT_DIR, config["screenshot_name"])
            await summary_row.screenshot(path=screenshot_path)
            print(f"  ✓ Saved screenshot: {screenshot_path}")

            # 5. Test Responsive Viewport (Mobile 390px)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.wait_for_timeout(600)
            mobile_cards = await page.query_selector_all(".l2-compact-card")
            mob_boxes = [await c.bounding_box() for c in mobile_cards]
            # On mobile, cards stack vertically (y coordinates strictly increase)
            is_stacked = all(mob_boxes[i]["y"] < mob_boxes[i+1]["y"] for i in range(len(mob_boxes)-1))
            assert is_stacked, "Mobile cards did not stack vertically!"
            print(f"  ✓ Responsive mobile view verified: Cards neatly stack into single-column layout")

            overall_results.append({
                "role": role,
                "name": role_name,
                "order": actual_titles,
                "width": round(widths[0], 1),
                "height": round(heights[0], 1),
                "screenshot": config["screenshot_name"]
            })

            await context.close()

        print("\n=======================================================")
        print("  ALL ROLES (L2, L3, L4, L5) VERIFIED SUCCESSFULLY!")
        print("=======================================================")
        for res in overall_results:
            print(f"- {res['name']}: {' -> '.join(res['order'])} | Dimensions: {res['width']}x{res['height']}px | Screenshot: {res['screenshot']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_metric_cards())
