#!/usr/bin/env bash
#
# Install Ollama, pull an open-source model, verify it answers, and point this project's .env at it.
# Safe to re-run: every step checks whether it is already done. Works on macOS and Linux.
#
#   scripts/setup_ollama.sh --dry-run        # show exactly what would happen, change nothing
#   scripts/setup_ollama.sh                  # do it (asks before downloading)
#   scripts/setup_ollama.sh --model qwen2.5:7b-instruct --yes --disable-web-search
#
# Options:
#   --model NAME           model to pull (default: qwen2.5:14b-instruct, ~9 GB; 7b-instruct is ~5 GB)
#   --dry-run              print every action without running it
#   --yes                  do not ask for confirmation before downloading
#   --no-pull              install/start Ollama but do not pull a model
#   --disable-web-search   set DISABLED_TOOLS=web_search in .env (use when no search provider is configured)
#   -h, --help             show this help
#
# Sources used (official only):
#   macOS app:   https://ollama.com/download/Ollama-darwin.zip   (code signature verified before install)
#   Linux:       https://ollama.com/install.sh                    (downloaded to a file, hash shown, run only after confirmation)
#   Models:      the Ollama library via `ollama pull`

set -euo pipefail

MODEL="${MODEL:-qwen2.5:14b-instruct}"
DRY_RUN=0
ASSUME_YES=0
NO_PULL=0
DISABLE_SEARCH=0
HOST="http://localhost:11434"
MAC_ZIP_URL="https://ollama.com/download/Ollama-darwin.zip"
LINUX_SCRIPT_URL="https://ollama.com/install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
TMP_DIR=""

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

cleanup() { [ -n "$TMP_DIR" ] && rm -rf "$TMP_DIR"; return 0; }
trap cleanup EXIT

usage() { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; }

# Run a command, or only print it in dry-run mode.
run() {
  if [ "$DRY_RUN" = 1 ]; then
    printf '   [dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --model)              [ $# -ge 2 ] || die "--model needs a value"; MODEL="$2"; shift 2 ;;
    --dry-run)            DRY_RUN=1; shift ;;
    --yes|-y)             ASSUME_YES=1; shift ;;
    --no-pull)            NO_PULL=1; shift ;;
    --disable-web-search) DISABLE_SEARCH=1; shift ;;
    -h|--help)            usage; exit 0 ;;
    *)                    die "unknown option: $1 (try --help)" ;;
  esac
done

case "$MODEL" in *[!A-Za-z0-9._:/-]*|"") die "model name contains unexpected characters: '$MODEL'" ;; esac

OS="$(uname -s)"
case "$OS" in Darwin|Linux) ;; *) die "unsupported OS '$OS'. Install Ollama manually from https://ollama.com/download" ;; esac
command -v curl >/dev/null 2>&1 || die "curl is required"

confirm() {  # confirm "question"
  [ "$ASSUME_YES" = 1 ] && return 0
  [ "$DRY_RUN" = 1 ] && return 0
  printf '%s [y/N] ' "$1"
  read -r answer || answer=""
  case "$answer" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# --- 1. disk space ----------------------------------------------------------------------------------------
needed_gb() {
  case "$MODEL" in
    *:32b*|*:34b*|*:70b*) echo 45 ;;
    *:14b*)               echo 15 ;;
    *:7b*|*:8b*)          echo 10 ;;
    *:3b*|*:4b*)          echo 6 ;;
    *)                    echo 20 ;;
  esac
}
free_gb() { df -Pk "$HOME" | awk 'NR==2 {printf "%d", $4/1024/1024}'; }

log "Checking disk space for $MODEL"
NEED="$(needed_gb)"; FREE="$(free_gb)"
[ "$FREE" -ge "$NEED" ] || die "only ${FREE} GB free in \$HOME, need about ${NEED} GB for $MODEL (pick a smaller one with --model)"
echo "   ${FREE} GB free, ~${NEED} GB needed: ok"

# --- 2. install Ollama ------------------------------------------------------------------------------------
OLLAMA_BIN=""
find_ollama() {
  if command -v ollama >/dev/null 2>&1; then OLLAMA_BIN="$(command -v ollama)"; return 0; fi
  for p in /Applications/Ollama.app/Contents/Resources/ollama "$HOME/Applications/Ollama.app/Contents/Resources/ollama" /usr/local/bin/ollama; do
    if [ -x "$p" ]; then OLLAMA_BIN="$p"; return 0; fi
  done
  return 1
}

install_mac() {
  if command -v brew >/dev/null 2>&1; then
    log "Installing Ollama with Homebrew"
    run brew install ollama
    return
  fi
  confirm "Download Ollama for macOS from $MAC_ZIP_URL (a few hundred MB) and install it to /Applications?" || die "aborted by user"
  TMP_DIR="$(mktemp -d)"
  log "Downloading Ollama app"
  run curl -fL --retry 3 --progress-bar -o "$TMP_DIR/Ollama.zip" "$MAC_ZIP_URL"
  log "Unpacking"
  run ditto -x -k "$TMP_DIR/Ollama.zip" "$TMP_DIR/unpacked"
  APP="$TMP_DIR/unpacked/Ollama.app"
  if [ "$DRY_RUN" != 1 ]; then
    [ -d "$APP" ] || die "download did not contain Ollama.app; nothing was installed"
    log "Verifying code signature and Gatekeeper approval"
    codesign --verify --deep --strict "$APP" || die "code signature check failed; not installing"
    spctl --assess --type execute "$APP" || die "Gatekeeper rejected the app; not installing"
  else
    printf '   [dry-run] codesign --verify --deep --strict Ollama.app && spctl --assess --type execute Ollama.app\n'
  fi
  DEST="/Applications"
  [ -w "$DEST" ] || { DEST="$HOME/Applications"; run mkdir -p "$DEST"; }
  if [ -d "$DEST/Ollama.app" ]; then die "$DEST/Ollama.app already exists; refusing to overwrite (delete it and re-run if you want a fresh copy)"; fi
  log "Installing to $DEST"
  run mv "$APP" "$DEST/Ollama.app"
}

install_linux() {
  confirm "Download the official Ollama installer from $LINUX_SCRIPT_URL and run it (needs sudo)?" || die "aborted by user"
  TMP_DIR="$(mktemp -d)"
  run curl -fsSL --retry 3 -o "$TMP_DIR/install.sh" "$LINUX_SCRIPT_URL"
  if [ "$DRY_RUN" != 1 ]; then
    [ -s "$TMP_DIR/install.sh" ] || die "installer download was empty"
    echo "   installer sha256: $(sha256sum "$TMP_DIR/install.sh" | cut -d' ' -f1)  ($(wc -c < "$TMP_DIR/install.sh") bytes)"
    echo "   read it first if you like: $TMP_DIR/install.sh"
    confirm "Run the installer now?" || die "aborted by user"
  fi
  run sh "$TMP_DIR/install.sh"
}

if find_ollama; then
  log "Ollama already installed at $OLLAMA_BIN"
else
  log "Ollama not found; installing"
  if [ "$OS" = Darwin ]; then install_mac; else install_linux; fi
  if [ "$DRY_RUN" = 1 ]; then
    OLLAMA_BIN="ollama"
  else
    find_ollama || die "install finished but the ollama binary was not found; open the Ollama app once, or install manually from https://ollama.com/download"
    log "Installed: $OLLAMA_BIN"
  fi
fi

# --- 3. start the server ----------------------------------------------------------------------------------
api_up() { curl -fsS -m 3 "$HOST/api/version" >/dev/null 2>&1; }

if api_up; then
  log "Ollama server already running at $HOST"
elif [ "$DRY_RUN" = 1 ]; then
  log "Would start the Ollama server and wait for $HOST"
else
  log "Starting Ollama server"
  if [ "$OS" = Darwin ] && [ -d /Applications/Ollama.app -o -d "$HOME/Applications/Ollama.app" ]; then
    open -a Ollama || warn "could not open the Ollama app, falling back to 'ollama serve'"
  fi
  if ! api_up; then
    sleep 2
    if ! api_up && ! pgrep -x ollama >/dev/null 2>&1; then
      nohup "$OLLAMA_BIN" serve >"$PROJECT_DIR/.ollama-serve.log" 2>&1 &
    fi
  fi
  for _ in $(seq 1 60); do api_up && break; sleep 1; done
  api_up || die "server did not come up within 60s (see $PROJECT_DIR/.ollama-serve.log if it exists)"
  log "Server is up"
fi

# --- 4. pull the model ------------------------------------------------------------------------------------
if [ "$NO_PULL" = 1 ]; then
  log "Skipping model pull (--no-pull)"
elif [ "$DRY_RUN" != 1 ] && "$OLLAMA_BIN" list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq "$MODEL"; then
  log "Model $MODEL already pulled"
else
  confirm "Pull $MODEL from the Ollama library (~${NEED} GB of disk)?" || die "aborted by user"
  log "Pulling $MODEL (resumes automatically if interrupted; just re-run this script)"
  run "$OLLAMA_BIN" pull "$MODEL"
fi

# --- 5. verify the model answers --------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  log "Would send a test chat request to $HOST/v1/chat/completions and check for a reply"
elif [ "$NO_PULL" = 1 ]; then
  log "Skipping verification (no model pulled)"
else
  log "Verifying $MODEL answers through the OpenAI-compatible endpoint"
  REPLY="$(curl -fsS -m 300 "$HOST/v1/chat/completions" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$MODEL\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the single word: ready\"}]}")" \
    || die "test request failed; check the server and that '$MODEL' was pulled (ollama list)"
  printf '%s' "$REPLY" | grep -q '"choices"' || die "unexpected response from the server: $REPLY"
  echo "   model responded: ok"
fi

# --- 6. configure the project -----------------------------------------------------------------------------
set_env() {  # set_env KEY VALUE  (replace if present, append otherwise)
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  if grep -Eq "^${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"; printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

log "Configuring $ENV_FILE"
if [ "$DRY_RUN" = 1 ]; then
  printf '   [dry-run] create .env from .env.example if missing (existing .env backed up to .env.bak)\n'
  printf '   [dry-run] set LLM_BACKEND=openai LLM_BASE_URL=%s/v1 LLM_MODEL=%s\n' "$HOST" "$MODEL"
  [ "$DISABLE_SEARCH" = 1 ] && printf '   [dry-run] set DISABLED_TOOLS=web_search\n'
else
  [ -f "$PROJECT_DIR/.env.example" ] || die "missing $PROJECT_DIR/.env.example"
  if [ -f "$ENV_FILE" ]; then [ -f "$ENV_FILE.bak" ] || cp "$ENV_FILE" "$ENV_FILE.bak"; else cp "$PROJECT_DIR/.env.example" "$ENV_FILE"; fi
  set_env LLM_BACKEND openai
  set_env LLM_BASE_URL "$HOST/v1"
  set_env LLM_MODEL "$MODEL"
  [ "$DISABLE_SEARCH" = 1 ] && set_env DISABLED_TOOLS web_search
  true
fi

log "Done."
cat <<EOF

Next steps:
  cd "$PROJECT_DIR" && source .venv/bin/activate
  python -m startup_cofounder "your business idea"
  python eval/demo_cases.py --only uber        # one evaluation case, then drop --only for all four
EOF
