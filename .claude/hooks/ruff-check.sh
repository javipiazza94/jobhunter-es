#!/usr/bin/env bash
# PostToolUse (Write|Edit): ruff sobre el .py editado. No bloquea; devuelve los avisos a Claude (exit 2).
f=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
case "$f" in *.py) ;; *) exit 0 ;; esac
[ -f "$f" ] || exit 0
command -v ruff >/dev/null 2>&1 || exit 0
out=$(ruff check --output-format concise "$f" 2>&1) && exit 0
echo "$out" >&2
exit 2
