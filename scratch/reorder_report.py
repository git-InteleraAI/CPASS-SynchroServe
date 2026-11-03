import sys

sys.stdout.reconfigure(encoding='utf-8')

report_path = r"C:\Users\Manu Mansoor\.gemini\antigravity\brain\be024e12-79ef-49d3-85b4-648e5272182d\CPASS_Final_Independent_Verification_Report.md"

with open(report_path, "r", encoding="utf-8") as f:
    text = f.read()

# Extract Section 8 block
s8_marker = "## 8. Final Recommendation"
s5_marker = "## 5. Placement Audit Statement Header Alignment Verification"

if s8_marker in text and s5_marker in text:
    parts = text.split(s8_marker)
    pre_s8 = parts[0]
    rest = parts[1]

    subparts = rest.split(s5_marker)
    s8_content = subparts[0]
    s5_content = s5_marker + subparts[1]

    new_text = pre_s8 + s5_content + "\n---\n\n" + s8_marker + s8_content
    # Replace numbering to be sequential:
    new_text = new_text.replace("## 5. Placement Audit Statement Header Alignment Verification", "## 7. Placement Audit Statement Header Alignment Verification (Print & Downloaded PDF)")
    new_text = new_text.replace("### 5.1", "### 7.1")
    new_text = new_text.replace("### 5.2", "### 7.2")
    new_text = new_text.replace("### 5.3", "### 7.3")
    new_text = new_text.replace("### 5.4", "### 7.4")
    new_text = new_text.replace("### 5.5", "### 7.5")
    new_text = new_text.replace("## 7. Edge Cases Tested", "## 8. Edge Cases Tested")
    new_text = new_text.replace("## 8. Final Recommendation", "## 9. Final Recommendation")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print("✓ Successfully cleaned up and sequenced report sections.")

