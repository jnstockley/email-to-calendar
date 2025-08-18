#!/usr/bin/env bash

export PYTHONPATH=src/:$PYTHONPATH

# Run Tests
uv run pytest --cov src --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy
