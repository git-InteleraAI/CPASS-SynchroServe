import asyncio
import os
import sys
import pypdf
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')
ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"

ROLES_CONFIG = [
    {
        "role_key": "l1",
        "role_name": "L1 – Placement Coordinator",
        "tab": "L1",
        "email": "appe@synchroserve.com",
        "password": "appe@cpass",
        "is_l1": True,
    },
    {
        "role_key": "l2",
        "role_name": "L2 – Center Head",
        "tab": "L2",
        "email": "apch@synchroserve.com",
        "password": "apch@cpass",
        "is_l1": False,
    },
    {
        "role_key": "l3",
        "role_name": "L3 – COPS Auditor",
        "tab": "L3",
        "email": "cops@synchroserve.com",
        "password": "jsubWTVkgGo9&_xuq0",
        "is_l1": False,
    },
    {
        "role_key": "l4",
        "role_name": "L4 – Business Leader (AP)",
        "tab": "L4",
        "email": "sowbhagya.bl@synchroserve.com",
        "password": "Hz^wdeeZnuBhr@=Z*2",
        "is_l1": False,
    },
    {
        "role_key": "l5",
        "role_name": "L5 – Chief Executive Officer",
        "tab": "L5",
        "email": "ceo@synchroserve.com",
        "password": "Kxfzu6*^@BzpRPKH!V",
        "is_l1": False,
    },
]

DASHBOARD_METRIC_STRINGS = [
    "Candidate Summary Statistics",
    "Candidate Review Summary",
    "Candidate Selection Pipeline",
    "Select a Candidate to Begin",
    "Dashboard Metrics Unavailable",
    "Retry Metrics",
    "In Progress candidates",
    "Uploaded candidates",
    "Approved candidates",
    "Rejected candidates",
    "Pending candidates",
]

async def run_verification():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        results = []

        for role in ROLES_CONFIG:
            role_key = role["role_key"]
            role_name = role["role_name"]
            is_l1 = role["is_l1"]
            print(f"\n=======================================================")
            print(f"  VERIFYING: {role_name} ({role_key.upper()})")
            print(f"=======================================================")

            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            # 1. Login
            await page.goto("http://localhost:5173", wait_until="networkidle")
            tab_btn = page.locator(f'button[data-r="{role["tab"]}"]')
            if await tab_btn.count() > 0:
                await tab_btn.click()

            await page.fill("input#em", role["email"])
            await page.fill("input#pw", role["password"])
            await page.locator("form#lf button.btn").first.click()
            await page.wait_for_timeout(2500)

            # 2. Select Candidate 1076631
            prefix = "" if is_l1 else "l2-"
            state_sel = page.locator(f"#{prefix}sel-state")
            opts = await state_sel.locator("option").all_inner_texts()
            for st in ["ANDHRA PRADESH", "TELANGANA", "ODISHA"]:
                matched = [o for o in opts if st in o]
                if matched:
                    await state_sel.select_option(label=matched[0])
                    await page.wait_for_timeout(1500)
                    break

            tc_sel = page.locator(f"#{prefix}sel-tc")
            if await tc_sel.count() > 0:
                opts = await tc_sel.locator("option").all_inner_texts()
                if len(opts) > 1:
                    await tc_sel.select_option(index=1)
                    await page.wait_for_timeout(1000)

            order_sel = page.locator(f"#{prefix}sel-order")
            if await order_sel.count() > 0:
                opts = await order_sel.locator("option").all_inner_texts()
                if len(opts) > 1:
                    await order_sel.select_option(index=1)
                    await page.wait_for_timeout(1000)

            batch_sel = page.locator(f"#{prefix}sel-batch")
            if await batch_sel.count() > 0:
                opts = await batch_sel.locator("option").all_inner_texts()
                if len(opts) > 1:
                    await batch_sel.select_option(index=1)
                    await page.wait_for_timeout(1000)

            cand_sel = page.locator(f"#{prefix}sel-cand")
            if await cand_sel.count() > 0:
                opts = await cand_sel.locator("option").all_inner_texts()
                if len(opts) > 1:
                    target_idx = 1
                    for i, opt in enumerate(opts):
                        if "1076631" in opt or "Sandhya" in opt:
                            target_idx = i
                            break
                    await cand_sel.select_option(index=target_idx)
                    await page.wait_for_timeout(2000)

            # In L1, open the statement modal
            if is_l1:
                stmt_btn = page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first
                await stmt_btn.click()
                await page.wait_for_timeout(2000)

            # Ensure statement sheet is rendered
            await page.wait_for_selector(".cpass-statement-sheet", timeout=10000)
            print("  ✓ .cpass-statement-sheet mounted.")

            # ==========================================
            # STEP 1: SCREEN HEADER ALIGNMENT CHECK
            # ==========================================
            screen_align = await page.evaluate("""() => {
                const sheet = document.querySelector('.cpass-statement-sheet');
                const header = document.querySelector('.cpass-statement-header');
                const logo = document.querySelector('.cpass-header-logo');
                const title = document.querySelector('.cpass-header-title');
                const h2 = document.querySelector('.cpass-header-title h2');
                const meta = document.querySelector('.cpass-header-meta');

                const sR = sheet.getBoundingClientRect();
                const hR = header.getBoundingClientRect();
                const lR = logo.getBoundingClientRect();
                const tR = title.getBoundingClientRect();
                const h2R = h2.getBoundingClientRect();
                const mR = meta.getBoundingClientRect();

                const pageMid = sR.left + (sR.width / 2);
                const titleMid = tR.left + (tR.width / 2);
                const h2Mid = h2R.left + (h2R.width / 2);

                return {
                    sheetWidth: sR.width,
                    logoWidth: lR.width,
                    titleWidth: tR.width,
                    h2Width: h2R.width,
                    metaWidth: mR.width,
                    pageMid: pageMid.toFixed(2),
                    titleMid: titleMid.toFixed(2),
                    h2Mid: h2Mid.toFixed(2),
                    offset: Math.abs(titleMid - pageMid).toFixed(2),
                    h2Offset: Math.abs(h2Mid - pageMid).toFixed(2),
                    display: window.getComputedStyle(header).display,
                    logoLeft: (lR.left - sR.left).toFixed(2),
                    metaRight: (sR.right - mR.right).toFixed(2),
                };
            }""")

            print(f"  [SCREEN] Display: {screen_align['display']}")
            print(f"           SheetW: {screen_align['sheetWidth']:.1f}px | LogoW: {screen_align['logoWidth']:.1f}px | MetaW: {screen_align['metaWidth']:.1f}px")
            print(f"           PageMid: {screen_align['pageMid']} | TitleMid: {screen_align['titleMid']} | Offset: {screen_align['offset']}px (H2 Offset: {screen_align['h2Offset']}px)")
            print(f"           Flank Insets: LogoLeftInset={screen_align['logoLeft']}px | MetaRightInset={screen_align['metaRight']}px")

            header_el = page.locator(".cpass-statement-header")
            screen_shot_path = os.path.join(ARTIFACT_DIR, f"header_screen_{role_key}.png")
            await header_el.screenshot(path=screen_shot_path)
            print(f"  ✓ Screen header screenshot saved: {screen_shot_path}")

            assert float(screen_align['offset']) <= 2.0, f"Screen title offset ({screen_align['offset']}px) exceeds tolerance!"

            # ==========================================
            # STEP 2: PRINT MEDIA DOM ALIGNMENT & ISOLATION
            # ==========================================
            print("  Emulating print media (media='print')...")
            await page.emulate_media(media="print")
            await page.wait_for_timeout(1000)

            print_align = await page.evaluate("""() => {
                const sheet = document.querySelector('.cpass-statement-sheet');
                const header = document.querySelector('.cpass-statement-header');
                const logo = document.querySelector('.cpass-header-logo');
                const title = document.querySelector('.cpass-header-title');
                const h2 = document.querySelector('.cpass-header-title h2');
                const meta = document.querySelector('.cpass-header-meta');

                const sR = sheet.getBoundingClientRect();
                const hR = header.getBoundingClientRect();
                const lR = logo.getBoundingClientRect();
                const tR = title.getBoundingClientRect();
                const h2R = h2.getBoundingClientRect();
                const mR = meta.getBoundingClientRect();

                const pageMid = sR.left + (sR.width / 2);
                const titleMid = tR.left + (tR.width / 2);
                const h2Mid = h2R.left + (h2R.width / 2);

                const isVisible = (sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                };

                let metricCardsVisible = false;
                document.querySelectorAll('.l1-compact-card, .l2-compact-card, .l1-compact-summary-row, .l2-compact-summary-row').forEach(el => {
                    if (window.getComputedStyle(el).display !== 'none') metricCardsVisible = true;
                });

                return {
                    sheetWidth: sR.width,
                    logoWidth: lR.width,
                    titleWidth: tR.width,
                    h2Width: h2R.width,
                    metaWidth: mR.width,
                    pageMid: pageMid.toFixed(2),
                    titleMid: titleMid.toFixed(2),
                    h2Mid: h2Mid.toFixed(2),
                    offset: Math.abs(titleMid - pageMid).toFixed(2),
                    h2Offset: Math.abs(h2Mid - pageMid).toFixed(2),
                    display: window.getComputedStyle(header).display,
                    metricCardsVisible: metricCardsVisible,
                    topbarVisible: isVisible('.l2-topbar') || isVisible('header.top'),
                    docPanelVisible: isVisible('.l2-doc-panel'),
                    bottomDockVisible: isVisible('.l2-bottom-dock'),
                };
            }""")

            print(f"  [PRINT]  Display: {print_align['display']}")
            print(f"           SheetW: {print_align['sheetWidth']:.1f}px | LogoW: {print_align['logoWidth']:.1f}px | MetaW: {print_align['metaWidth']:.1f}px")
            print(f"           PageMid: {print_align['pageMid']} | TitleMid: {print_align['titleMid']} | Offset: {print_align['offset']}px (H2 Offset: {print_align['h2Offset']}px)")
            print(f"           Metric Cards Hidden: {not print_align['metricCardsVisible']} | Topbar Hidden: {not print_align['topbarVisible']}")
            print(f"           Doc Panel Hidden: {not print_align['docPanelVisible']} | Bottom Dock Hidden: {not print_align['bottomDockVisible']}")

            print_preview_path = os.path.join(ARTIFACT_DIR, f"screenshot_print_preview_{role_key}.png")
            await page.screenshot(path=print_preview_path, full_page=True)
            print(f"  ✓ Print preview screenshot saved: {print_preview_path}")

            assert float(print_align['offset']) <= 2.0, f"Print title offset ({print_align['offset']}px) exceeds tolerance!"
            assert print_align['metricCardsVisible'] is False, "Metric cards MUST be hidden in print!"
            assert print_align['topbarVisible'] is False, "Topbar MUST be hidden in print!"

            # ==========================================
            # STEP 3: PDF EXPORT & COORDINATES
            # ==========================================
            pdf_path = os.path.join(ARTIFACT_DIR, f"statement_{role_key}.pdf")
            await page.pdf(
                path=pdf_path,
                format="A4",
                prefer_css_page_size=True,
                print_background=True,
            )
            print(f"  ✓ PDF generated: {pdf_path}")

            # Inspect PDF with PyPDF
            reader = pypdf.PdfReader(pdf_path)
            num_pages = len(reader.pages)
            print(f"  [PDF]    Pages: {num_pages} | Page 1 Box: {reader.pages[0].mediabox.width} x {reader.pages[0].mediabox.height}")

            full_text = ""
            for p_idx, pg in enumerate(reader.pages):
                full_text += pg.extract_text() + "\n"

            # Check 0 dashboard metric strings
            found_metrics = [m for m in DASHBOARD_METRIC_STRINGS if m.lower() in full_text.lower()]
            print(f"  [PDF]    Metric Strings Found: {len(found_metrics)}")
            assert len(found_metrics) == 0, f"Found dashboard metrics in PDF: {found_metrics}"

            results.append({
                "role": role_name,
                "role_key": role_key,
                "screen_offset": screen_align['offset'],
                "print_offset": print_align['offset'],
                "metric_cards_hidden": not print_align['metricCardsVisible'],
                "pdf_pages": num_pages,
                "pdf_metrics_found": len(found_metrics),
                "status": "PASSED"
            })

            await context.close()

        await browser.close()

        print("\n=======================================================")
        print("  FINAL 5-ROLE HEADER ALIGNMENT & PRINT SUMMARY")
        print("=======================================================")
        for r in results:
            print(f"  {r['role']}: Screen Offset = {r['screen_offset']}px | Print Offset = {r['print_offset']}px | Metrics Hidden = {r['metric_cards_hidden']} | PDF Metrics = {r['pdf_metrics_found']} | {r['status']}")

if __name__ == "__main__":
    asyncio.run(run_verification())
