#!/usr/bin/env bash

set -e

IFS=$'\n\t'

# Run Python linter
uv run ruff check --exit-non-zero-on-fix
uv run ruff format --check --exit-non-zero-on-format

# Run Shell linter, ignoring files in .gitignore
git ls-files --cached --others --exclude-standard |
    grep -E '\.sh$|\.bash$|\.ksh$|\.bashrc$|\.bash_profile$|\.bash_login$|\.bash_logout$' |
    xargs -r shellcheck -x -S style

git ls-files --cached --others --exclude-standard |
    grep -E '\.sh$|\.bash$|\.ksh$|\.bashrc$|\.bash_profile$|\.bash_login$|\.bash_logout$' |
    xargs -r shfmt --diff -i 4 -ci

# Run YAML linter only on YAML files not ignored by .gitignore
git ls-files --cached --others --exclude-standard |
    grep -E '\.ya?ml$' |
    xargs -r yamllint -s
