#!/usr/bin/env bash
# The passwords' half of .github/workflows/demo-personas.yml, kept out of the
# YAML so it can be run, and tested, on a laptop.
#
#   scripts/demo_personas_ci.sh <raw-output> <db> <out-dir> <recipient.pem>
#
# <raw-output> is what `seed_demo_personas.py` printed. Everything in it but
# the lines between CADRA_PERSONAS_BEGIN and CADRA_PERSONAS_END is printed;
# those lines are NEVER printed. Each password is first registered with the
# runner as a mask (`::add-mask::`), so a stray echo anywhere later in the job
# shows *** instead — the second wall, not the first. The block is then
# encrypted to <recipient.pem>, whose private half exists only on the owner's
# machine (docs/api/.personas.key.pem, gitignored), and written to
# <out-dir>/<db>.personas.enc for the workflow to upload as an artifact.
# `scripts/demo_personas_fetch.sh <run-id>` decrypts it there.
#
# Why encrypted rather than masked alone: a GitHub log is readable by anybody
# with read access to the repository, and an artifact is downloadable by the
# same people. A mask hides a value from the log; it does nothing for a file.
#
# File format, three lines, all base64: the AES key and IV (48 bytes)
# RSA-OAEP-encrypted to the recipient; the AES-256-CBC ciphertext; nothing else.
set -euo pipefail

raw="${1:?raw output}"; db="${2:?db}"; out="${3:?out dir}"; recipient="${4:?recipient pem}"

block="$(mktemp)"; keyiv="$(mktemp)"
trap 'rm -f "$block" "$keyiv"' EXIT
awk '/^CADRA_PERSONAS_BEGIN$/{inside=1; next} /^CADRA_PERSONAS_END$/{inside=0; next} inside && NF' \
  "$raw" > "$block"

# Masks first, before anything else is printed.
while read -r _key _login password; do
  [ -n "${password:-}" ] && echo "::add-mask::${password}"
done < "$block"

sed '/^CADRA_PERSONAS_BEGIN$/,/^CADRA_PERSONAS_END$/d' "$raw"

count="$(grep -c . "$block" || true)"
if [ "$count" -eq 0 ]; then
  echo "passwords  : none new for ${db} — nothing to fetch"
  exit 0
fi
mkdir -p "$out"
openssl rand 48 > "$keyiv"
hex="$(od -An -tx1 -v "$keyiv" | tr -d ' \n')"
{
  openssl pkeyutl -encrypt -pubin -inkey "$recipient" \
    -pkeyopt rsa_padding_mode:oaep -in "$keyiv" | openssl base64 -A; echo
  openssl enc -aes-256-cbc -K "${hex:0:64}" -iv "${hex:64:32}" -in "$block" \
    | openssl base64 -A; echo
} > "${out}/${db}.personas.enc"
echo "passwords  : ${count} encrypted to ${db}.personas.enc — fetch with scripts/demo_personas_fetch.sh <run-id>"
