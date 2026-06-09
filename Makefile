.PHONY: setup demo serve api ui eval test

setup:
	uv sync

demo:
	python scripts/run_demo.py --topic "小区门口夜市是否应该保留？"

api:
	python api/main.py

ui:
	streamlit run frontend/streamlit_app.py

serve:
	@echo "Open two terminals: make api and open frontend/live_deliberation.html, or run make ui for Streamlit Cloud preview."

eval:
	python evals/run_eval.py

test:
	pytest -q
