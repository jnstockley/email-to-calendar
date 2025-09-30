#!/usr/bin/env bash

# Set these variables
PYTHON_STARTER_URL="https://github.com/jnstockley/python-starter.git"
PYTHON_STARTER_BRANCH="main" # or the branch you want to merge

# Pull changes from python starter repo into current git repo
git remote add pythonStarter "$PYTHON_STARTER_URL"
git fetch pythonStarter
git merge --allow-unrelated-histories --no-edit pythonStarter/"$PYTHON_STARTER_BRANCH"
git remote remove pythonStarter
