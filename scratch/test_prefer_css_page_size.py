import asyncio
import os
import sys
import pypdf
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d"

ALIGNMENT_FIX_CSS = """
/* Scope responsive styles so they NEVER match during print */
@media screen and (max-width: 768px) {
}

@media print {
  @page {
    size: A4 portrait;
    margin: 10mm;
  }

  .cpass-statement-header {
    display: grid !important;
    grid-template-columns: 180px 1fr 200px !important;
    align-items: center !important;
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

/* On screen: balanced grid */
.cpass-statement-sheet .cpass-statement-header,
.cpass-statement-header {
  display: grid !important;
  grid-template-columns: 200px 1fr 200px !important;
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

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='msedge', headless=True)
        ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await page.goto('http://localhost:5173')
        await page.fill('input#em', 'appe@synchroserve.com')
        await page.fill('input#pw', 'appe@cpass')
        await page.locator('form#lf button.btn').first.click()
        await page.wait_for_timeout(2000)
        await page.locator('#sel-state').select_option(label='ANDHRA PRADESH')
        await page.wait_for_timeout(800)
        await page.locator('#sel-tc').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-order').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-batch').select_option(index=1)
        await page.wait_for_timeout(800)
        await page.locator('#sel-cand').select_option(index=1)
        await page.wait_for_timeout(1500)
        await page.locator(".l1-btn-secondary:has-text('Statement'), .l1-btn-primary-action:has-text('Statement')").first.click()
        await page.wait_for_timeout(1500)

        await page.add_style_tag(content=ALIGNMENT_FIX_CSS)
        await page.wait_for_timeout(500)

        pdf_path = os.path.join(ARTIFACT_DIR, "statement_prefer_css.pdf")
        await page.pdf(
            path=pdf_path,
            prefer_css_page_size=True,
            print_background=True,
        )
        print("PDF generated:", pdf_path)

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

        await b.close()

if __name__ == '__main__':
    asyncio.run(test())

