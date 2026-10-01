#!/usr/bin/env bash
# Print every authority (`host:port`) a browser on this tailnet can reach this
# machine's $1 by, one per line — the MagicDNS name, its short form, and each
# Tailscale IP literal, bracketed when it is IPv6.
#
# This exists because two independent fences need the same answer and must not
# drift: SSSF_TRUSTED_HOSTS for the visualizer's operator guard, and
# `dsh --trusted-host` for the DeepSeek Harness web UI. Both compare the
# request's Host header against a literal list, so a name missing here is a 403
# with nothing useful in it.
#
# Prints nothing and exits 0 when Tailscale is down: a caller then starts
# loopback-only rather than failing to start at all.
set -euo pipefail

port="${1:?usage: tailnet-authorities.sh <port>}"

command -v tailscale >/dev/null || exit 0
state=$(tailscale status --json 2>/dev/null) || exit 0
[ "$(jq -r .BackendState <<<"$state")" = "Running" ] || exit 0

name=$(jq -r '.Self.DNSName // ""' <<<"$state" | sed 's/\.$//')
if [ -n "$name" ]; then
  printf '%s:%s\n' "$name" "$port"
  # MagicDNS resolves the short form too, and that is what gets typed.
  [ "${name%%.*}" = "$name" ] || printf '%s:%s\n' "${name%%.*}" "$port"
fi
for ip in $(tailscale ip 2>/dev/null || true); do
  # An IP literal is the authority that still works with MagicDNS off. IPv6
  # appears in a URL bracketed, which is how a Host header carries it.
  case "$ip" in
    *:*) printf '[%s]:%s\n' "$ip" "$port" ;;
    *) printf '%s:%s\n' "$ip" "$port" ;;
  esac
done
