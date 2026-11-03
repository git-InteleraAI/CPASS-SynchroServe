with open("backend/app/routers/documents.py", "r", encoding="utf-8") as f:
    text = f.read()

target = """            if matched_bank.get("is_consolidated"):
                b_row["coverage_start_month"] = matched_bank.get("coverage_start_month")
                b_row["coverage_end_month"] = matched_bank.get("coverage_end_month")
                b_row["coverage_start_year"] = matched_bank.get("coverage_start_year")
                b_row["coverage_end_year"] = matched_bank.get("coverage_end_year")
                b_row["covered_months"] = matched_bank.get("covered_months")"""

rep = """            if matched_bank.get("is_consolidated"):
                b_row["coverage_start_month"] = matched_bank.get("coverage_start_month")
                b_row["coverage_end_month"] = matched_bank.get("coverage_end_month")
                b_row["coverage_start_year"] = matched_bank.get("coverage_start_year")
                b_row["coverage_end_year"] = matched_bank.get("coverage_end_year")
                b_row["covered_months"] = matched_bank.get("covered_months")
                if not b_row.get("remarks"):
                    b_row["remarks"] = f"Covered by consolidated statement ({matched_bank.get('file_name', '')})" """

assert target in text, "Target not found in documents.py"
text = text.replace(target, rep, 1)

with open("backend/app/routers/documents.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Updated consolidated remark in documents.py")

