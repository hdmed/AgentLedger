PYTHON := python

.PHONY: extract report watch full all clean open open-app test check-js exe exe-debug

# Incremental extraction (delta since the last sync)
extract:
	$(PYTHON) extract.py

# Full re-extraction (use after editing config/pricing.json)
full:
	$(PYTHON) extract.py --full

# Build dist/report.html (offline)
report:
	$(PYTHON) extract.py
	$(PYTHON) build_report.py

# Full re-extraction + report
all: full report

# Watch opencode.db and regenerate automatically (extract + build)
watch:
	$(PYTHON) extract.py --watch --build

# Open the report
open:
	$(PYTHON) -c "import os,webbrowser; webbrowser.open('file:///'+os.path.abspath('dist/report.html'))"

# Validate the template inline JS (dataset placeholder substituted)
check-js:
	$(PYTHON) -c "import re; h=open('templates/report_template.html',encoding='utf-8').read().replace('/*__DATASET__*/','{}'); open('__tpl_check.js','w',encoding='utf-8').write('\n'.join(re.findall(r'<script>(.*?)</script>',h,re.S)))"
	node --check __tpl_check.js
	$(PYTHON) -c "import os; os.remove('__tpl_check.js')"

test:
	$(PYTHON) -m py_compile extract.py extract_kilo.py extract_autoclaw.py extract_workbuddy.py build_report.py resources.py launcher.py build_exe.py notification.py
	$(PYTHON) -m unittest discover -s tests -v

exe:
	$(PYTHON) build_exe.py --confirm

exe-debug:
	$(PYTHON) build_exe.py --onedir --confirm

open-app:
	$(PYTHON) launcher.py

# Reset extraction cache (dataset + all sync states + report)
clean:
	$(PYTHON) -c "import os; [os.remove(f) for f in ['data/dataset.json','data/sync_state.json','data/kilo_sync_state.json','data/autoclaw_sync_state.json','data/workbuddy_sync_state.json','dist/report.html'] if os.path.exists(f)]"
