import asyncio
import os
import sys
import pypdf
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"

GRID_CSS = """
.cpass-statement-sheet .cpass-statement-header,
.cpass-statement-header {
  display: grid !important;
  grid-template-columns: 200px 1fr 200px !important;
  align-items: center !important;
  gap: 12px !important;
  width: 100% !important;
}
.cpass-header-logo {
  justify-self: start !important;
  display: flex !important;
  align-items: center !important;
}
.cpass-header-title {
  justify-self: center !important;
  text-align: center !important;
  width: 100% !important;
}
.cpass-header-meta {
  justify-self: end !important;
  text-align: right !important;
  width: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 2px !important;
}
"""

async def test_grid_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        for role, email, pw, is_l1 in [
            ("L1", "appe@synchroserve.com", "appe@cpass", True),
            ("L2", "apch@synchroserve.com", "apch@cpass", False),
        ]:
            print(f"\n================ Testing {role} ================")
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            await page.goto("http://localhost:5173", wait_until="networkidle")

            # Login
            await page.fill('input#em', email)
            await page.fill('input#pw', pw)
            await page.locator('form#lf button.btn').first.click()
            await page.wait_for_timeout(2500)

            # Select Candidate 1076631
            prefix = "" if is_l1 else "l2-"
            state_sel = page.locator(f"#{prefix}sel-state")
            opts = await state_sel.locator("option").all_inner_texts()
            for st in ["ANDHRA PRADESH", "TELANGANA", "ODISHA"]:
                matched = [o for o in opts if st in o]
                if matched:
                    await state_sel.select_option(label=matched[0])
                    await page.wait_for_timeout(1000)
                    break

            await page.locator(f"#{prefix}sel-tc").select_option(index=1)
            await page.wait_for_timeout(800)
            await page.locator(f"#{prefix}sel-order").select_option(index=1)
            await page.wait_for_timeout(800)
            await page.locator(f"#{prefix}sel-batch").select_option(index=1)
            await page.wait_for_timeout(800)
            await page.locator(f"#{prefix}sel-cand").select_option(index=1)
            await page.wait_for_timeout(2000)

            if is_l1:
                await page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first.click()
                await page.wait_for_timeout(2000)

            await page.wait_for_selector(".cpass-statement-sheet")

            # Inject the grid CSS
            await page.add_style_tag(content=GRID_CSS)
            await page.wait_for_timeout(500)

            # Generate PDF
            pdf_path = os.path.join(ARTIFACT_DIR, f"test_grid_{role.lower()}.pdf")
            await page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
            )
            print(f"  ✓ PDF generated: {pdf_path}")

            # Inspect PDF positions
            reader = pypdf.PdfReader(pdf_path)
            first_page = reader.pages[0]
            print(f"  PDF Page Box: Width={first_page.mediabox.width}, Height={first_page.mediabox.height}")

            def visitor(text, cm, tm, font_dict, font_size):
                t = text.strip()
                if any(k in t for k in ["SYNCHROSERVE", "C-PASS", "DDU-GKY", "Doc Ref", "Overall Status"]):
                    print(f"    Text: '{t[:35]}' | X: {tm[4]:.2f} | Y: {tm[5]:.2f} | Font size: {font_size}")

            print("  --- Extracted Header Text Elements ---")
            first_page.extract_text(visitor_text=visitor)

            await context.close()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_grid_pdf())

