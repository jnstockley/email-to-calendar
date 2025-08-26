#!/usr/bin/env bash

# Run Python linter
uvx ruff check
uvx ruff format --check

# Run Shell linter, ignoring files in .gitignore
git ls-files --cached --others --exclude-standard |
    grep -E '\.sh$|\.bash$|\.ksh$|\.bashrc$|\.bash_profile$|\.bash_login$|\.bash_logout$' |
    xargs -r shellcheck -x -S style

git ls-files --cached --others --exclude-standard |
    grep -E '\.sh$|\.bash$|\.ksh$|\.bashrc$|\.bash_profile$|\.bash_login$|\.bash_logout$' |
    xargs -r shfmt --diff -i 4 -ci

# Run YAML linter
yamllint -s .
npx dclint -r --fix --max-warnings 0 ./
