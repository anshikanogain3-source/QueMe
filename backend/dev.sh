#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
flask_bin="$backend_dir/.venv/bin/flask"
children=()

if [[ ! -x "$flask_bin" ]]; then
  printf 'Backend virtualenv not found. Create it and install backend/requirements.txt first.\n' >&2
  exit 1
fi
if ! command -v setsid >/dev/null 2>&1; then
  printf 'The dev launcher requires setsid to shut down both process groups cleanly.\n' >&2
  exit 1
fi

stop_children() {
  trap - EXIT INT TERM
  for pid in "${children[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  for pid in "${children[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}
remove_child() {
  local target="$1"
  local remaining=()
  for pid in "${children[@]}"; do
    [[ "$pid" == "$target" ]] || remaining+=("$pid")
  done
  children=("${remaining[@]}")
}
trap stop_children EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$backend_dir"
setsid "$flask_bin" --app run.py process-answer-jobs &
worker_pid=$!
children+=("$worker_pid")
worker_ready=false
heartbeat_path="$backend_dir/instance/answer-processing-worker.json"
for _ in {1..50}; do
  if ! kill -0 "$worker_pid" 2>/dev/null; then
    set +e
    wait "$worker_pid"
    exit_code=$?
    set -e
    remove_child "$worker_pid"
    exit "$exit_code"
  fi
  heartbeat_pid="$("$backend_dir/.venv/bin/python" -c 'import json, sys; print(json.load(open(sys.argv[1])).get("pid", ""))' "$heartbeat_path" 2>/dev/null || true)"
  if [[ "$heartbeat_pid" == "$worker_pid" ]]; then
    worker_ready=true
    break
  fi
  sleep 0.1
done
if [[ "$worker_ready" != true ]]; then
  printf 'Answer worker did not become healthy; check its startup output and /api/health.\n' >&2
  exit 1
fi

setsid "$flask_bin" --app run.py --debug run &
api_pid=$!
children+=("$api_pid")

printf 'QueMe API and answer worker are running. Press Ctrl+C to stop both.\n'
set +e
wait -n "$api_pid" "$worker_pid"
exit_code=$?
set -e
exit "$exit_code"
