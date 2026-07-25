.PHONY: test demo manifest clean

test:
	python3 -m pytest tests/ -v

demo:
	python3 -m src.server --manifest
	python3 -m src.server list --group quick
	python3 -m src.server health || true

manifest:
	python3 -m src.server --manifest

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
