SW = python skills/snapwright/scripts/sw.py

.PHONY: setup test example preview package clean bench ldraw-check
setup:
	pip install -r requirements.txt
test:
	pytest -q -n auto tests
preview:
	$(SW) preview examples/lighthouse/design.py --out examples/lighthouse/out/preview
example:
	$(SW) build examples/lighthouse/design.py --out examples/lighthouse/out --seeds 6
package:
	rm -f dist/snapwright.skill dist/snapwright.zip
	mkdir -p dist && cd skills && zip -rq ../dist/snapwright.zip snapwright -x '*/__pycache__/*' '*.DS_Store' '*/.rebrickable/*' '*.tmp'
	cp dist/snapwright.zip dist/snapwright.skill
clean:
	rm -rf examples/*/out creations/*/out dist .pytest_cache
bench:
	$(SW) build examples/keep/design.py --out examples/keep/out --seeds 6 --profile
ldraw-check:
	python tools/ldraw_check.py examples/lighthouse/out/model.json examples/lighthouse/out/harbour-lighthouse.ldr --lib $(LDRAW_LIB) --png examples/lighthouse/out/ldraw-check.png
