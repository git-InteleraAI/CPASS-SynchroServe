import re
from pathlib import Path

html_path = Path("SyncroServe CPASS.html")
text = html_path.read_text(encoding="utf-8")

login_start = text.find('<main id="login"')
dash_start = text.find('<main id="dash"')

login_html = text[login_start:dash_start]
login_html_clean = re.sub(r'src="data:image/png;base64,[^"]+"', 'src="[LOGO_PLACEHOLDER]"', login_html)
print("=" * 60)
print("LOGIN HTML:")
print("=" * 60)
print(login_html_clean)

script_start = text.find("<script>")
script_end = text.find("</script>")
script_content = text[script_start:script_end+9]
print("=" * 60)
print("SCRIPT CONTENT:")
print("=" * 60)
print(script_content)
