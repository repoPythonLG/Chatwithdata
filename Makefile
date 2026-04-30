.PHONY: backend frontend test sample

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest

sample:
	python scripts/create_sample_data.py
