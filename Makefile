PYTHON ?= .venv/bin/python
PORT_VIEWER ?= 8080
PORT_TOOLS ?= 8765
RENDERER ?= browser

.PHONY: help install install-pil viewer tools demo demo-stop judge-demo duet learn-from-targets test clean-servers

help:
	@echo "hermes-painter — make targets"
	@echo ""
	@echo "  make install          pip install -e . + playwright install chromium"
	@echo "  make install-pil      pip install -e . only (no Chromium; RENDERER=pil)"
	@echo "  make judge-demo       self-check + start stack + paint one canonical demo (for judges)"
	@echo "  make demo             start viewer :$(PORT_VIEWER) + tool server :$(PORT_TOOLS) in background"
	@echo "  make demo-stop        stop both servers"
	@echo "  make viewer           start only the viewer (foreground)"
	@echo "  make tools            start only the tool server (foreground)"
	@echo "  make duet TARGET=... [A=van_gogh_voice] [B=tenebrist_voice] [TURNS=6]"
	@echo "                        run a two-persona duet via scripts/duet.py"
	@echo "  make learn-from-targets [LIMIT=N]"
	@echo "                        batch-paint real targets to seed the skills library"
	@echo "  make test             run pytest"
	@echo "  make clean-servers    kill any viewer/tools processes on known ports"
	@echo ""
	@echo "After 'make demo': open http://127.0.0.1:$(PORT_VIEWER) to watch."
	@echo "Then try Hermes against the running servers:"
	@echo '  hermes "paint targets/masterworks/the_bedroom.jpg in van_gogh style"'
	@echo ""
	@echo "Tip: RENDERER=pil make viewer for headless PIL rendering (no Chromium)."

install:
	$(PYTHON) -m pip install -e .
	$(PYTHON) -m playwright install chromium

install-pil:
	$(PYTHON) -m pip install -e .

viewer:
	$(PYTHON) scripts/viewer.py --port $(PORT_VIEWER) --renderer $(RENDERER)

tools:
	$(PYTHON) scripts/hermes_tools.py --port $(PORT_TOOLS)

judge-demo: clean-servers
	@echo ""
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║              Hermes Painter — Judge Demo                     ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "[1/5] Environment self-check..."
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "  ✗ Python not found at $(PYTHON)"; \
		echo "    Run:  make install"; \
		exit 1; \
	fi
	@py_ver=$$($(PYTHON) -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"); \
		py_major=$$(echo $$py_ver | cut -d. -f1); \
		py_minor=$$(echo $$py_ver | cut -d. -f2); \
		if [ $$py_major -lt 3 ] || [ $$py_major -eq 3 -a $$py_minor -lt 11 ]; then \
			echo "  ✗ Python $$py_ver is too old (need >= 3.11)"; exit 1; \
		else \
			echo "  ✓ Python $$py_ver"; \
		fi
	@$(PYTHON) -c "import painter" 2>/dev/null && echo "  ✓ painter package installed" || \
		(echo "  ✗ painter package not installed"; echo "    Run:  make install"; exit 1)
	@if [ ! -f targets/masterworks/great_wave.jpg ]; then \
		echo "  ✗ targets/masterworks/great_wave.jpg missing"; exit 1; \
	else \
		echo "  ✓ demo target present (targets/masterworks/great_wave.jpg)"; \
	fi
	@mkdir -p /tmp/painter-demo
	@echo ""
	@echo "[2/5] Starting viewer on :$(PORT_VIEWER) (renderer=$(RENDERER))..."
	@PYTHONPATH=src $(PYTHON) scripts/viewer.py --port $(PORT_VIEWER) --renderer $(RENDERER) \
		> /tmp/painter-demo/viewer.log 2>&1 & echo $$! > /tmp/painter-demo/viewer.pid
	@sleep 2
	@echo "[3/5] Starting tool server on :$(PORT_TOOLS)..."
	@PYTHONPATH=src $(PYTHON) scripts/hermes_tools.py --port $(PORT_TOOLS) \
		> /tmp/painter-demo/tools.log 2>&1 & echo $$! > /tmp/painter-demo/tools.pid
	@sleep 1
	@echo ""
	@echo "[4/5] Health-check (up to 10 seconds)..."
	@ok=0; for i in 1 2 3 4 5 6 7 8 9 10; do \
		viewer=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$(PORT_VIEWER)/api/state 2>/dev/null); \
		tools=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$(PORT_TOOLS)/tool/manifest 2>/dev/null); \
		if [ "$$viewer" = "200" ] && [ "$$tools" = "200" ]; then ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ok" = "1" ]; then \
		echo "  ✓ viewer :$(PORT_VIEWER) → 200"; \
		echo "  ✓ tools  :$(PORT_TOOLS) → 200"; \
	else \
		echo "  ✗ servers did not come up in 10s"; \
		echo "    viewer log: /tmp/painter-demo/viewer.log"; \
		echo "    tools  log: /tmp/painter-demo/tools.log"; \
		exit 1; \
	fi
	@echo ""
	@echo "[5/5] Running one canonical demo paint (targets/masterworks/great_wave.jpg, default style)..."
	@curl -s -X POST -H "Content-Type: application/json" \
		-d '{"path":"targets/masterworks/great_wave.jpg"}' \
		http://127.0.0.1:$(PORT_TOOLS)/tool/load_target > /dev/null
	@curl -s -X POST http://127.0.0.1:$(PORT_VIEWER)/api/paint -d '{}' > /dev/null
	@done_ok=0; for i in 1 2 3 4 5 6 7 8 9 10 11 12; do \
		sleep 2; \
		busy=$$(curl -s http://127.0.0.1:$(PORT_VIEWER)/api/state | $(PYTHON) -c "import sys,json; print(json.load(sys.stdin).get('busy'))" 2>/dev/null); \
		if [ "$$busy" = "False" ]; then done_ok=1; break; fi; \
	done; \
	@mkdir -p gallery/judge-demo
	if [ "$$done_ok" = "1" ]; then \
		echo "  ✓ paint completed"; \
		curl -s http://127.0.0.1:$(PORT_VIEWER)/api/state | $(PYTHON) -c "\
import sys,json,base64,pathlib; \
s=json.load(sys.stdin); \
sc=s.get('score') or {}; \
ssim=round(sc.get('ssim',0),4); \
strokes=s.get('strokes_applied',0); \
iter_=s.get('iteration',0); \
job=s.get('job_status','unknown'); \
out=pathlib.Path('gallery/judge-demo'); \
out.mkdir(parents=True, exist_ok=True); \
canvas_b64=s.get('canvas_png') or ''; \
result=out/'result.png'; \
result.write_bytes(base64.b64decode(canvas_b64)) if canvas_b64 else None; \
meta=out/'result.json'; \
meta.write_text(json.dumps({'target':'targets/masterworks/great_wave.jpg','iterations':iter_,'strokes':strokes,'ssim':ssim,'job_status':job}, indent=2)); \
print(f'    iterations: {iter_}'); \
print(f'    strokes:    {strokes}'); \
print(f'    SSIM:       {ssim}'); \
print(f'    job_status: {job}'); \
print(f'    artifact:   {result} ({result.stat().st_size//1024} KB)' if result.exists() else '    artifact:   (none — canvas empty)')"; \
	else \
		echo "  ⚠ paint did not finish in 24s — check /tmp/painter-demo/*.log"; \
	fi
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "  ✓ READY — Hermes Painter is running."
	@echo ""
	@echo "  👁  Watch in your browser:"
	@echo "     http://127.0.0.1:$(PORT_VIEWER)"
	@echo ""
	@echo "  🤖 Drive it with Hermes (AGENTS.md is auto-discovered):"
	@echo '     hermes "paint targets/masterworks/the_bedroom.jpg in van_gogh style"'
	@echo '     hermes "run paint_duet on targets/masterworks/mona_lisa.jpg with van_gogh_voice and tenebrist_voice"'
	@echo ""
	@echo "  🖼  Standalone artifact: gallery/judge-demo/result.png (+ result.json)"
	@echo "  📜 More demo prompts:   AGENTS.md"
	@echo "  📋 Full agent playbook: HERMES.md"
	@echo "  📂 Logs:                /tmp/painter-demo/{viewer,tools}.log"
	@echo "  🛑 Stop everything:     make demo-stop"
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"

demo: clean-servers
	@mkdir -p /tmp/painter-demo
	@echo "[demo] starting viewer on :$(PORT_VIEWER) (renderer=$(RENDERER))..."
	@PYTHONPATH=src $(PYTHON) scripts/viewer.py --port $(PORT_VIEWER) --renderer $(RENDERER) \
		> /tmp/painter-demo/viewer.log 2>&1 & echo $$! > /tmp/painter-demo/viewer.pid
	@sleep 2
	@echo "[demo] starting tool server on :$(PORT_TOOLS)..."
	@PYTHONPATH=src $(PYTHON) scripts/hermes_tools.py --port $(PORT_TOOLS) \
		> /tmp/painter-demo/tools.log 2>&1 & echo $$! > /tmp/painter-demo/tools.pid
	@sleep 1
	@ok=0; for i in 1 2 3 4 5 6 7 8 9 10; do \
		viewer=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$(PORT_VIEWER)/api/state 2>/dev/null); \
		tools=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$(PORT_TOOLS)/tool/manifest 2>/dev/null); \
		if [ "$$viewer" = "200" ] && [ "$$tools" = "200" ]; then ok=1; break; fi; \
		sleep 0.5; \
	done; \
	if [ "$$ok" = "1" ]; then \
		echo "[demo] ✓ viewer ready at http://127.0.0.1:$(PORT_VIEWER)"; \
		echo "[demo] ✓ tools  ready at http://127.0.0.1:$(PORT_TOOLS)/tool/manifest"; \
	else \
		echo "[demo] ⚠ servers slow to start — check /tmp/painter-demo/viewer.log and tools.log"; \
	fi
	@echo ""
	@echo "[demo] logs: tail -f /tmp/painter-demo/viewer.log /tmp/painter-demo/tools.log"
	@echo "[demo] stop: make demo-stop"
	@echo ""
	@echo "Try Hermes:"
	@echo '  hermes "paint targets/masterworks/the_bedroom.jpg in van_gogh style"'
	@echo '  hermes "run paint_duet on targets/masterworks/mona_lisa.jpg with van_gogh_voice and tenebrist_voice"'
	@echo ""
	@echo "Or open http://127.0.0.1:$(PORT_VIEWER) and click a preset tile."

demo-stop: clean-servers

duet:
	@test -n "$(TARGET)" || (echo "usage: make duet TARGET=targets/masterworks/mona_lisa.jpg [A=van_gogh_voice] [B=tenebrist_voice] [TURNS=6]"; exit 1)
	$(PYTHON) scripts/duet.py "$(TARGET)" \
		--personas $(if $(A),$(A),van_gogh_voice),$(if $(B),$(B),tenebrist_voice) \
		--max-turns $(if $(TURNS),$(TURNS),6)

learn-from-targets:
	$(PYTHON) scripts/learn_from_targets.py --style-cycle $(if $(LIMIT),--limit $(LIMIT))

test:
	$(PYTHON) -m pytest tests/ -x

clean-servers:
	@for pidf in /tmp/painter-demo/viewer.pid /tmp/painter-demo/tools.pid; do \
		if [ -f "$$pidf" ]; then \
			pid=$$(cat "$$pidf"); \
			if kill -0 "$$pid" 2>/dev/null; then kill "$$pid"; fi; \
			rm -f "$$pidf"; \
		fi; \
	done
	@pkill -f "scripts/viewer.py" 2>/dev/null || true
	@pkill -f "scripts/hermes_tools.py\|painter.tools.server" 2>/dev/null || true
	@sleep 1
	@# Port-based fallback — catch any stragglers not killed by pkill/PID-file
	@for port in $(PORT_VIEWER) $(PORT_TOOLS); do \
		pid=$$(lsof -ti :$$port 2>/dev/null); \
		if [ -n "$$pid" ]; then kill -9 $$pid 2>/dev/null; fi; \
	done
	@sleep 1
	@echo "[clean] ✓ servers stopped"
