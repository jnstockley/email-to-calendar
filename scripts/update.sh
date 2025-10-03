#!/usr/bin/env bash

# Set these variables
PYTHON_STARTER_URL="https://github.com/jnstockley/python-starter.git"
PYTHON_STARTER_BRANCH="main"

git remote add -f python-starter "$PYTHON_STARTER_URL"
git fetch python-starter
git merge python-starter/"$PYTHON_STARTER_BRANCH" --allow-unrelated-histories
git remote remove python-starter
