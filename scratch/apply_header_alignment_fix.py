import sys

sys.stdout.reconfigure(encoding='utf-8')

# 1. Update PlacementAuditStatement.css
statement_css_path = 'frontend/src/components/PlacementAuditStatement.css'
with open(statement_css_path, 'r', encoding='utf-8') as f:
    statement_css = f.read()

# Replace base header styles
old_base_header = """/* -----------------------------------------------------------------------------
   1. Compact, Professional Document Header
   ----------------------------------------------------------------------------- */
.cpass-statement-sheet .cpass-statement-header,
.cpass-statement-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 2px solid #0b4fb8;
  padding-bottom: 12px;
  gap: 16px;
  width: 100%;
}

.cpass-statement-sheet .cpass-header-logo,
.cpass-header-logo {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.cpass-statement-sheet .cpass-header-logo img,
.cpass-header-logo img {
  height: 44px;
  width: auto;
  object-fit: contain;
  display: block;
}

.cpass-statement-sheet .cpass-header-title,
.cpass-header-title {
  text-align: center;
  flex: 1;
  min-width: 0;
  padding: 0 8px;
}"""

new_base_header = """/* -----------------------------------------------------------------------------
   1. Compact, Professional Document Header
   ----------------------------------------------------------------------------- */
.cpass-statement-sheet .cpass-statement-header,
.cpass-statement-header {
  display: grid !important;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr) !important;
  align-items: center !important;
  justify-content: space-between !important;
  border-bottom: 2px solid #0b4fb8;
  padding-bottom: 12px;
  gap: 16px;
  width: 100%;
}

.cpass-statement-sheet .cpass-header-logo,
.cpass-header-logo {
  order: 1;
  justify-self: start;
  display: flex;
  align-items: center;
}

.cpass-statement-sheet .cpass-header-logo img,
.cpass-header-logo img {
  height: 44px;
  width: auto;
  object-fit: contain;
  display: block;
}

.cpass-statement-sheet .cpass-header-title,
.cpass-header-title {
  order: 2;
  justify-self: center;
  text-align: center;
  width: 100%;
  padding: 0 8px;
}"""

assert old_base_header in statement_css, "old_base_header not found in PlacementAuditStatement.css"
statement_css = statement_css.replace(old_base_header, new_base_header)

# Replace meta styles in base header
old_meta = """.cpass-statement-sheet .cpass-header-meta,
.cpass-header-meta {
  flex-shrink: 0;
  text-align: right;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: #475569;
  min-width: 175px;
}"""

new_meta = """.cpass-statement-sheet .cpass-header-meta,
.cpass-header-meta {
  order: 3;
  justify-self: end;
  text-align: right;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: #475569;
  min-width: 175px;
}"""

assert old_meta in statement_css, "old_meta not found in PlacementAuditStatement.css"
statement_css = statement_css.replace(old_meta, new_meta)

# Scope responsive queries to screen only
old_resp_768 = "@media (max-width: 768px) {"
new_resp_768 = "@media screen and (max-width: 768px) {"
assert old_resp_768 in statement_css, "old_resp_768 not found"
statement_css = statement_css.replace(old_resp_768, new_resp_768)

old_resp_480 = "@media (max-width: 480px) {"
new_resp_480 = "@media screen and (max-width: 480px) {"
assert old_resp_480 in statement_css, "old_resp_480 not found"
statement_css = statement_css.replace(old_resp_480, new_resp_480)

# Replace print header styles
old_print_header = """  .cpass-statement-header {
    border-bottom: 2px solid #0a2a7a !important;
    padding-bottom: 8px !important;
    margin-bottom: 10px !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }

  .cpass-header-logo img {
    height: 38px !important;
  }

  .cpass-header-title h2 {
    font-size: 11pt !important;
    color: #0a2a7a !important;
  }

  .cpass-header-title h4 {
    font-size: 9.5pt !important;
    color: #0b4fb8 !important;
  }"""

new_print_header = """  .cpass-statement-sheet .cpass-statement-header,
  .cpass-statement-header {
    display: grid !important;
    grid-template-columns: minmax(170px, 1fr) auto minmax(170px, 1fr) !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 10px !important;
    width: 100% !important;
    border-bottom: 2px solid #0a2a7a !important;
    padding-bottom: 8px !important;
    margin-bottom: 10px !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    flex-wrap: nowrap !important;
  }

  .cpass-statement-sheet .cpass-header-logo,
  .cpass-header-logo {
    order: 1 !important;
    justify-self: start !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
  }

  .cpass-header-logo img,
  .cpass-statement-sheet .cpass-header-logo img {
    height: 38px !important;
    width: auto !important;
    object-fit: contain !important;
    display: block !important;
  }

  .cpass-statement-sheet .cpass-header-title,
  .cpass-header-title {
    order: 2 !important;
    justify-self: center !important;
    text-align: center !important;
    width: 100% !important;
    padding: 0 4px !important;
  }

  .cpass-statement-sheet .cpass-header-title h2,
  .cpass-header-title h2 {
    font-size: 11pt !important;
    font-weight: 800 !important;
    color: #0a2a7a !important;
    line-height: 1.2 !important;
    margin: 0 !important;
    text-align: center !important;
  }

  .cpass-statement-sheet .cpass-header-title h4,
  .cpass-header-title h4 {
    font-size: 9.5pt !important;
    font-weight: 800 !important;
    color: #0b4fb8 !important;
    margin: 2px 0 0 !important;
    letter-spacing: 0.05em !important;
    text-align: center !important;
  }

  .cpass-statement-sheet .cpass-header-title p,
  .cpass-header-title p {
    font-size: 7.5pt !important;
    color: #475569 !important;
    line-height: 1.25 !important;
    margin: 2px 0 0 !important;
    text-align: center !important;
  }

  .cpass-statement-sheet .cpass-header-meta,
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

  .cpass-statement-sheet .cpass-header-meta div,
  .cpass-header-meta div {
    white-space: nowrap !important;
    text-align: right !important;
  }"""

assert old_print_header in statement_css, "old_print_header not found"
statement_css = statement_css.replace(old_print_header, new_print_header)

with open(statement_css_path, 'w', encoding='utf-8') as f:
    f.write(statement_css)
print("✓ Updated PlacementAuditStatement.css")

# 2. Update L1Home.css
l1_css_path = 'frontend/src/pages/L1Home.css'
with open(l1_css_path, 'r', encoding='utf-8') as f:
    l1_css = f.read()

old_l1_header = """.cpass-statement-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 2px solid #0B4FB8;
  padding-bottom: 14px;
  gap: 16px;
}"""

new_l1_header = """.cpass-statement-header {
  border-bottom: 2px solid #0B4FB8;
  padding-bottom: 14px;
  gap: 16px;
}"""

assert old_l1_header in l1_css, "old_l1_header not found in L1Home.css"
l1_css = l1_css.replace(old_l1_header, new_l1_header)

# Scope mobile query in L1Home.css
old_l1_resp = "/* 4. Placement Audit Statement Modal on Mobile */\n@media (max-width: 640px) {"
new_l1_resp = "/* 4. Placement Audit Statement Modal on Mobile */\n@media screen and (max-width: 640px) {"
assert old_l1_resp in l1_css, "old_l1_resp not found in L1Home.css"
l1_css = l1_css.replace(old_l1_resp, new_l1_resp)

with open(l1_css_path, 'w', encoding='utf-8') as f:
    f.write(l1_css)
print("✓ Updated L1Home.css")

# 3. Update L2Home.css
l2_css_path = 'frontend/src/pages/L2Home.css'
with open(l2_css_path, 'r', encoding='utf-8') as f:
    l2_css = f.read()

old_l2_header = """.l2-statement-panel .cpass-statement-header {
  flex-wrap: wrap;
  gap: 12px;
}"""

new_l2_header = """@media screen and (max-width: 768px) {
  .l2-statement-panel .cpass-statement-header {
    flex-wrap: wrap;
    gap: 12px;
  }
}"""

assert old_l2_header in l2_css, "old_l2_header not found in L2Home.css"
l2_css = l2_css.replace(old_l2_header, new_l2_header)

with open(l2_css_path, 'w', encoding='utf-8') as f:
    f.write(l2_css)
print("✓ Updated L2Home.css")

