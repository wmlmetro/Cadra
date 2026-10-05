#!/usr/bin/env bash
# Refuse a commit message that carries an AI-attribution trailer.
#
# The repository's standing rule (CLAUDE.md, "Git & attribution policy") is
# that no commit, tag or PR carries any Claude/AI reference. Twice — reports
# 37 and 49 — the Step-0 commit went out with the tool's default trailer
# before the rule was consulted, both caught after the push. Handoff 50
# ruling 3: a rule that depends on remembering will be broken again, so this
# is the mechanical form. It runs two ways:
#
#   check_commit_messages.sh --message-file <path>   # the commit-msg hook
#   check_commit_messages.sh --range <A>..<B>        # CI, over new commits
#
# Past commits stay as the owner ruled (206 of the 209 commits reachable from
# dev carry a trailer from before the rule was mechanical) — which is why the
# CI mode takes a RANGE and never scans full history.
set -euo pipefail

# Case-insensitive, one per line. Anything matching any of these fails.
PATTERNS=(
  'co-authored-by:.*claude'
  'generated with.*claude'
  'noreply@anthropic\.com'
  'anthropic\.com/claude'
)

fail=0

check_text() {
  # $1 = label to print, $2 = the message text
  local label="$1" text="$2" pat
  for pat in "${PATTERNS[@]}"; do
    if printf '%s\n' "$text" | grep -Eiq "$pat"; then
      echo "REFUSED: $label carries an AI-attribution line (matched /$pat/)." >&2
      printf '%s\n' "$text" | grep -Ein "$pat" | sed 's/^/    /' >&2
      echo "    The repository forbids any Claude/AI reference in commits" >&2
      echo "    (CLAUDE.md, 'Git & attribution policy'; handoff 50 ruling 3)." >&2
      echo "    Remove the line and commit again." >&2
      fail=1
    fi
  done
}

case "${1:-}" in
  --message-file)
    [ -n "${2:-}" ] && [ -f "$2" ] || { echo "usage: $0 --message-file <path>" >&2; exit 2; }
    # Comment lines never reach the recorded message.
    check_text "this commit message" "$(grep -v '^#' "$2" || true)"
    ;;
  --range)
    [ -n "${2:-}" ] || { echo "usage: $0 --range <A>..<B>" >&2; exit 2; }
    shas=$(git log --format=%H "$2")
    n=0
    for sha in $shas; do
      n=$((n + 1))
      check_text "commit ${sha:0:9}" "$(git log -1 --format=%B "$sha")"
    done
    echo "checked $n commit message(s) in $2" >&2
    ;;
  *)
    echo "usage: $0 --message-file <path> | --range <A>..<B>" >&2
    exit 2
    ;;
esac

exit $fail
