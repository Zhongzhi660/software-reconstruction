#!/bin/sh
set -u
mkdir -p /logs/verifier
set +e
python3 /tests/private/judge.py   --workspace "${WORKSPACE_ROOT:-/app/workspace}"   --private "${PRIVATE_ROOT:-/tests/private}"   > /logs/verifier/judge.log 2>&1
rc=$?
set -e
cat /logs/verifier/judge.log || true
if [ "$rc" -eq 0 ]; then printf '1\n' > /logs/verifier/reward.txt
else printf '0\n' > /logs/verifier/reward.txt; fi
exit "$rc"
