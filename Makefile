PYTHON ?= python3
YOSYS ?= yosys

.PHONY: test

test:
	PYTHONPATH=src YOSYS=$(YOSYS) $(PYTHON) -m unittest discover -s tests -v

