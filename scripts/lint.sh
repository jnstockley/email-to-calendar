#!/usr/bin/env bash

# Run Python linter
ruff check
ruff format --check

# Run Shell linter
find . -type f \( -name '*.sh' -o -name '*.bash' -o -name '*.ksh' -o -name '*.bashrc' -o -name '*.bash_profile' -o -name '*.bash_login' -o -name '*.bash_logout' \) -print0 | xargs -0 shellcheck -x -S style
shfmt --diff -i 4 -ci .

# Run YAML linter
yamllint -s .
npx dclint -r --fix --max-warnings 0 ./
