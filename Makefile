SW = python skill/snapwright/scripts/sw.py

.PHONY: setup test example preview package clean bench
setup:
	pip install -r requirements.txt
test:
	pytest -q tests
preview:
	$(SW) preview examples/lighthouse/design.py --out examples/lighthouse/out/preview
example:
	$(SW) build examples/lighthouse/design.py --out examples/lighthouse/out --seeds 6
package:
	mkdir -p dist && cd skill && zip -rq ../dist/snapwright.skill snapwright -x '*/__pycache__/*'
clean:
	rm -rf examples/*/out creations/*/out dist .pytest_cache
bench:
	$(SW) build examples/keep/design.py --out examples/keep/out --seeds 6 --profile
