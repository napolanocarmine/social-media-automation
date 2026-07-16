#!/usr/bin/env bash
# Genera certificati TLS locali per META_REDIRECT_URI=https://127.0.0.1:8765/...
# Richiede mkcert: https://github.com/FiloSottile/mkcert
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/output/meta-oauth-certs"
mkdir -p "${OUT}"
cd "${OUT}"

if ! command -v mkcert >/dev/null 2>&1; then
  echo "mkcert non trovato. Su macOS con Homebrew:"
  echo "  brew install mkcert nss"
  echo "  mkcert -install"
  echo "Poi rilancia questo script."
  exit 1
fi

mkcert -cert-file meta-oauth.pem -key-file meta-oauth-key.pem 127.0.0.1 localhost
chmod 600 meta-oauth.pem meta-oauth-key.pem
echo "Creati:"
echo "  ${OUT}/meta-oauth.pem"
echo "  ${OUT}/meta-oauth-key.pem"
echo ""
echo "Aggiungi al .env:"
echo "  META_OAUTH_TLS_CERTFILE=${OUT}/meta-oauth.pem"
echo "  META_OAUTH_TLS_KEYFILE=${OUT}/meta-oauth-key.pem"
echo "  META_REDIRECT_URI=https://127.0.0.1:8765/oauth/facebook/callback"
echo ""
echo "Registra lo stesso META_REDIRECT_URI in Meta → Facebook Login → URI OAuth validi."
echo "Esegui una tantum: mkcert -install (installa la CA locale nel keychain)."
