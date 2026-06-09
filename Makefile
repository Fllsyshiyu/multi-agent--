.PHONY: setup demo serve api ui eval test

setup:
	uv sync

demo:
	python scripts/run_demo.py --topic "小区门口夜市是否应该保留？"

api:
	uvicorn api.main:app --reload --port 8000

ui:
	streamlit run frontend/streamlit_app.py

serve:
	@echo "Open two terminals: make api and make ui"

eval:
	python evals/run_eval.py

test:
	pytest -q
