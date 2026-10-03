#!/usr/bin/env bash
# Bring the cluster's demo-persona passwords home, from one run of
# .github/workflows/demo-personas.yml.
#
#   scripts/demo_personas_fetch.sh <run-id>
#
# Downloads that run's artifact, decrypts each <db>.personas.enc with the
# private key that exists only here (docs/api/.personas.key.pem, gitignored),
# and merges the lines into docs/api/.personas.cluster.<db> — mode 600,
# gitignored, a persona's line replaced by its newer password. `cluster.` in
# the name because the cluster's tenants share names with this machine's
# replicas (gtb, jaizbankplc, lasg) and have different passwords.
set -euo pipefail

run="${1:?usage: $0 <run-id>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
key="$root/docs/api/.personas.key.pem"
[ -f "$key" ] || { echo "no private key at $key — the passwords can only be read where it lives" >&2; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
gh run download "$run" --dir "$work" >/dev/null
found=0
while IFS= read -r -d '' enc; do
  found=$((found + 1))
  db="$(basename "$enc" .personas.enc)"
  keyiv="$(sed -n 1p "$enc" | openssl base64 -d -A \
    | openssl pkeyutl -decrypt -inkey "$key" -pkeyopt rsa_padding_mode:oaep \
    | od -An -tx1 -v | tr -d ' \n')"
  sed -n 2p "$enc" | openssl base64 -d -A \
    | openssl enc -d -aes-256-cbc -K "${keyiv:0:64}" -iv "${keyiv:64:32}" > "$work/$db.txt"
  python3 - "$work/$db.txt" "$root/docs/api/.personas.cluster.$db" <<'PY'
import os, sys
new, creds = sys.argv[1], sys.argv[2]
lines = [l.rstrip("\n") for l in open(new) if l.strip()]
known = {}
if os.path.exists(creds):
    for l in open(creds):
        if l.strip() and not l.startswith("#"):
            known[l.split()[0]] = l.rstrip("\n")
for l in lines:
    known[l.split()[0]] = l
fd = os.open(creds, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("# Demo personas on the CLUSTER tenant (handoff 46): key login password.\n"
            "# Fetched by scripts/demo_personas_fetch.sh. Gitignored; never copy.\n")
    for k in sorted(known):
        f.write(known[k] + "\n")
os.chmod(creds, 0o600)
print("%-12s %d password(s) → %s" % (os.path.basename(creds).split(".")[-1],
                                     len(lines), os.path.relpath(creds)))
PY
done < <(find "$work" -name '*.personas.enc' -print0)
[ "$found" -gt 0 ] || echo "run $run carried no encrypted passwords (nothing new was created)"
