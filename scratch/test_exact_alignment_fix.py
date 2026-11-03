import asyncio
import os
import sys
import pypdf
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"

ALIGNMENT_FIX_CSS = """
/* Scope mobile media queries to screen only */
@media print {
  .cpass-statement-header {
    display: grid !important;
    grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr) !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 12px !important;
    width: 100% !important;
    border-bottom: 2px solid #0a2a7a !important;
    padding-bottom: 8px !important;
    margin-bottom: 10px !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    flex-wrap: nowrap !important;
  }

  .cpass-header-logo {
    order: 1 !important;
    justify-self: start !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
  }

  .cpass-header-logo img {
    height: 38px !important;
    width: auto !important;
    object-fit: contain !important;
    display: block !important;
  }

  .cpass-header-title {
    order: 2 !important;
    justify-self: center !important;
    text-align: center !important;
    width: 100% !important;
    padding: 0 4px !important;
  }

  .cpass-header-title h2 {
    font-size: 11pt !important;
    font-weight: 800 !important;
    color: #0a2a7a !important;
    line-height: 1.2 !important;
    margin: 0 !important;
    text-align: center !important;
  }

  .cpass-header-title h4 {
    font-size: 9.5pt !important;
    font-weight: 800 !important;
    color: #0b4fb8 !important;
    margin: 2px 0 0 !important;
    letter-spacing: 0.05em !important;
    text-align: center !important;
  }

  .cpass-header-title p {
    font-size: 7.5pt !important;
    color: #475569 !important;
    line-height: 1.25 !important;
    margin: 2px 0 0 !important;
    text-align: center !important;
  }

  .cpass-header-meta {
    order: 3 !important;
    justify-self: end !important;
    text-align: right !important;
    width: 100% !important;
    display: flex !important;
    flex-direction: column !important;
    gap: 2px !important;
    font-size: 8.5pt !important;
    line-height: 1.3 !important;
    color: #334155 !important;
  }

  .cpass-header-meta div {
    white-space: nowrap !important;
    text-align: right !important;
  }
}

/* Also apply grid on screen for perfect centering */
.cpass-statement-sheet .cpass-statement-header,
.cpass-statement-header {
  display: grid !important;
  grid-template-columns: minmax(190px, 1fr) auto minmax(190px, 1fr) !important;
  align-items: center !important;
  gap: 16px !important;
  width: 100% !important;
}

.cpass-statement-sheet .cpass-header-logo,
.cpass-header-logo {
  order: 1 !important;
  justify-self: start !important;
  display: flex !important;
  align-items: center !important;
}

.cpass-statement-sheet .cpass-header-title,
.cpass-header-title {
  order: 2 !important;
  justify-self: center !important;
  text-align: center !important;
  width: 100% !important;
  padding: 0 8px !important;
}

.cpass-statement-sheet .cpass-header-meta,
.cpass-header-meta {
  order: 3 !important;
  justify-self: end !important;
  text-align: right !important;
  width: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 3px !important;
}
"""

async def test_alignment():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5173", wait_until="networkidle")

        # Login L1
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.locator('form#lf button.btn').first.click()
        await page.wait_for_timeout(2500)

        # Select Candidate 1076631
        await page.locator("#sel-state").select_option(label="ANDHRA PRADESH")
        await page.wait_for_timeout(1000)
        await page.locator("#sel-tc").select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator("#sel-order").select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator("#sel-batch").select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator("#sel-cand").select_option(index=1)
        await page.wait_for_timeout(2000)

        # Open statement modal in L1
        await page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first.click()
        await page.wait_for_timeout(2000)
        await page.wait_for_selector(".cpass-statement-sheet")

        # Inject alignment fix
        await page.add_style_tag(content=ALIGNMENT_FIX_CSS)
        await page.wait_for_timeout(500)

        # 1. SCREEN CHECK
        screen_check = await page.evaluate("""() => {
            const sheet = document.querySelector('.cpass-statement-sheet');
            const logo = document.querySelector('.cpass-header-logo');
            const title = document.querySelector('.cpass-header-title');
            const h2 = document.querySelector('.cpass-header-title h2');
            const meta = document.querySelector('.cpass-header-meta');

            const sR = sheet.getBoundingClientRect();
            const lR = logo.getBoundingClientRect();
            const tR = title.getBoundingClientRect();
            const h2R = h2.getBoundingClientRect();
            const mR = meta.getBoundingClientRect();

            const pageMid = sR.left + (sR.width / 2);
            const titleMid = tR.left + (tR.width / 2);
            const h2Mid = h2R.left + (h2R.width / 2);

            return {
                pageMid: pageMid.toFixed(2),
                titleMid: titleMid.toFixed(2),
                h2Mid: h2Mid.toFixed(2),
                offset: (titleMid - pageMid).toFixed(2),
                h2Offset: (h2Mid - pageMid).toFixed(2),
                logoLeft: lR.left.toFixed(2),
                metaRight: mR.right.toFixed(2),
                sheetRight: sR.right.toFixed(2),
            };
        }""")
        print("SCREEN ALIGNMENT:", screen_check)

        # Screenshot Screen Header
        header_el = page.locator(".cpass-statement-header")
        await header_el.screenshot(path=os.path.join(ARTIFACT_DIR, "header_screen_aligned.png"))

        # 2. PRINT CHECK
        await page.emulate_media(media="print")
        await page.wait_for_timeout(500)

        print_check = await page.evaluate("""() => {
            const sheet = document.querySelector('.cpass-statement-sheet');
            const logo = document.querySelector('.cpass-header-logo');
            const title = document.querySelector('.cpass-header-title');
            const h2 = document.querySelector('.cpass-header-title h2');
            const meta = document.querySelector('.cpass-header-meta');

            const sR = sheet.getBoundingClientRect();
            const lR = logo.getBoundingClientRect();
            const tR = title.getBoundingClientRect();
            const h2R = h2.getBoundingClientRect();
            const mR = meta.getBoundingClientRect();

            const pageMid = sR.left + (sR.width / 2);
            const titleMid = tR.left + (tR.width / 2);
            const h2Mid = h2R.left + (h2R.width / 2);

            return {
                pageMid: pageMid.toFixed(2),
                titleMid: titleMid.toFixed(2),
                h2Mid: h2Mid.toFixed(2),
                offset: (titleMid - pageMid).toFixed(2),
                h2Offset: (h2Mid - pageMid).toFixed(2),
                logoLeft: lR.left.toFixed(2),
                metaRight: mR.right.toFixed(2),
                sheetRight: sR.right.toFixed(2),
            };
        }""")
        print("PRINT ALIGNMENT:", print_check)

        # Screenshot Print Header
        await header_el.screenshot(path=os.path.join(ARTIFACT_DIR, "header_print_aligned.png"))

        # 3. PDF GENERATION & COORDINATE INSPECTION
        pdf_path = os.path.join(ARTIFACT_DIR, "statement_aligned_test.pdf")
        await page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
        )
        print("PDF GENERATED:", pdf_path)

        reader = pypdf.PdfReader(pdf_path)
        first_page = reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_mid = page_width / 2.0
        print(f"PDF Page Width: {page_width} pt | Page Mid: {page_mid:.2f} pt")

        items = []
        def visitor(text, cm, tm, font_dict, font_size):
            t = text.strip()
            if tm[5] < 120 and t: # Header region near top
                items.append((t, tm[4], tm[5], font_size))

        first_page.extract_text(visitor_text=visitor)
        print("\n--- PDF HEADER TEXT POSITIONS ---")
        for t, x, y, size in items:
            print(f"  X: {x:6.2f} | Y: {y:5.2f} | Font: {size:4.1f} | '{t}'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_alignment())

