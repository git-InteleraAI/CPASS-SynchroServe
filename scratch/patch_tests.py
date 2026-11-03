with open("backend/tests/test_multilevel_reviews.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace('role="L4_LEADER",', 'role="L4_LEADER",\n    assigned_states=["ODISHA"],')
with open("backend/tests/test_multilevel_reviews.py", "w", encoding="utf-8") as f:
    f.write(text)
print("Updated L4_USER successfully")

