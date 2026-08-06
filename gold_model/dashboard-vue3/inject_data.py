#!/usr/bin/env python3
"""把 dashboard_data.json + execution_data.json + drift_history.json + manifest.json + sw.js 注入/复制到 dist
让file://协议下也能加载数据（绕过CORS），PWA资源完整
用法：
  npm run build 后：PYTHONPATH=src python3 dashboard-vue3/inject_data.py
  只刷新单文件成品的内联数据（无需重新构建）：
  PYTHONPATH=src python3 dashboard-vue3/inject_data.py --refresh
"""
import json, sys, pathlib, shutil, re

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))
from gold_model.paths import DASHBOARD_JSON, EXECUTION_JSON, DRIFT_HISTORY, WEB_DIR

ROOT = pathlib.Path(__file__).resolve().parent
DIST = ROOT / 'dist'
HTML = DIST / 'index.html'
DD = DASHBOARD_JSON
ED = EXECUTION_JSON
DRIFT = DRIFT_HISTORY

REFRESH_ONLY = '--refresh' in sys.argv
SINGLE_FILE = WEB_DIR / 'dashboard-vue3.html'

with open(DD, 'r', encoding='utf-8') as f:
    dash_data = json.load(f)
with open(ED, 'r', encoding='utf-8') as f:
    exec_data = json.load(f)
drift_data = []
if DRIFT.exists():
    with open(DRIFT, 'r', encoding='utf-8') as f:
        drift_data = json.load(f)

# 序列化时禁用 NaN/Infinity（JSON标准不支持）
def safe(obj):
    if isinstance(obj, dict):
        return {k: safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [safe(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj in (float('inf'), float('-inf')):
            return None
    return obj

inline_script = f"""<script>
window.__DASHBOARD_DATA__ = {json.dumps(safe(dash_data), ensure_ascii=False, allow_nan=False)};
window.__EXECUTION_DATA__ = {json.dumps(safe(exec_data), ensure_ascii=False, allow_nan=False)};
window.__DRIFT_DATA__ = {json.dumps(safe(drift_data), ensure_ascii=False, allow_nan=False)};
</script>"""

if REFRESH_ONLY:
    # 原地替换单文件成品里 <body> 后的第一个数据 script 块
    with open(SINGLE_FILE, 'r', encoding='utf-8') as f:
        single = f.read()
    pattern = re.compile(r'<script>\s*window\.__DASHBOARD_DATA__.*?</script>', re.DOTALL)
    new_single, n = pattern.subn(inline_script, single, count=1)
    if n == 0:
        # 首次注入：插到 <body> 后
        pos = single.find('<body>')
        assert pos >= 0, '未找到 <body>'
        new_single = single[:pos + len('<body>')] + '\n' + inline_script + '\n' + single[pos + len('<body>'):]
    with open(SINGLE_FILE, 'w', encoding='utf-8') as f:
        f.write(new_single)
    print(f'✅ single-file data refreshed: {SINGLE_FILE}')
    print(f'   size: {len(new_single)/1024:.1f} KB, drift records: {len(drift_data)}')
    sys.exit(0)

assert HTML.exists(), '缺少 dist/index.html，请先 npm run build'

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# 在<body>后插入数据
needle = '<body>'
pos = html.find(needle)
assert pos >= 0
new_html = html[:pos + len(needle)] + '\n' + inline_script + '\n' + html[pos + len(needle):]

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(new_html)

# 复制 PWA 资源到 dist
for name in ['manifest.json', 'sw.js']:
    src = ROOT / 'public' / name
    if src.exists():
        shutil.copy2(src, DIST / name)
        print(f'✅ copied {name}')

print(f'✅ inline data injected, size: {len(new_html)/1024:.1f} KB')
print(f'   drift_history records: {len(drift_data)}')
