#!/usr/bin/env bash
# Serve the web UI over HTTPS (port 8443) with a locally trusted certificate.
#
# Browsers only grant the microphone (composer dictation) to HTTPS pages, and
# a self-hosted Tailscale control server (Headscale) can't issue ts.net
# certificates. mkcert makes a local certificate authority; this script
# issues a certificate for every address this Mac is reached by and drops it
# where Codi picks it up (<state dir>/tls/cert.pem + key.pem).
#
# Afterwards:
#   - trust the CA on this Mac:   mkcert -install      (asks for your password)
#   - trust it on an iPhone/iPad: AirDrop <state dir>/tls/rootCA.pem, install
#     the profile, then Settings > General > About > Certificate Trust
#     Settings > enable full trust for "mkcert ..."
#   - restart Codi: ./scripts/install_macos_launchd.sh
#
# Re-run it when the Mac's addresses change.
set -euo pipefail

STATE_DIR="${CODEXBOT_DIR:-$HOME/.codexbot}"
TLS_DIR="$STATE_DIR/tls"

if ! command -v mkcert >/dev/null 2>&1; then
    echo "Installing mkcert with Homebrew…"
    brew install mkcert
fi

names=(localhost 127.0.0.1 ::1)
host="$(scutil --get LocalHostName 2>/dev/null || hostname -s)"
names+=("$host" "$host.local")
if command -v tailscale >/dev/null 2>&1; then
    ts_name="$(tailscale status --json 2>/dev/null \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' \
        2>/dev/null || true)"
    [ -n "$ts_name" ] && names+=("$ts_name")
    for ip in $(tailscale ip 2>/dev/null); do names+=("$ip"); done
fi
for iface in en0 en1; do
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    [ -n "$ip" ] && names+=("$ip")
done
# De-duplicate, keeping order.
names=($(printf '%s\n' "${names[@]}" | awk '!seen[$0]++'))

mkdir -p "$TLS_DIR"
chmod 700 "$TLS_DIR"
mkcert -cert-file "$TLS_DIR/cert.pem" -key-file "$TLS_DIR/key.pem" "${names[@]}"
chmod 600 "$TLS_DIR/key.pem"
cp "$(mkcert -CAROOT)/rootCA.pem" "$TLS_DIR/rootCA.pem"

echo
echo "Certificate for: ${names[*]}"
echo "Files in $TLS_DIR (cert.pem, key.pem, rootCA.pem for other devices)."
echo "Next: mkcert -install  (trust on this Mac), then ./scripts/install_macos_launchd.sh"
