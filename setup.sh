#!/usr/bin/env bash
# setup.sh — Deploy bridge deal bot to Ubuntu/Debian VM
# Run as root: bash setup.sh
#
# Expects:
#   - This repo cloned locally (recommended /opt/bridge/src)
#   - /opt/bridge/.env written with DISCORD_TOKEN, OPENAI_API_KEY, etc.

set -euo pipefail

BRIDGE_DIR=/opt/bridge
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Support either repository layout:
#   /opt/bridge/src/<repo files>
# or legacy:
#   /opt/bridge/src/deploy/setup.sh with sources in /opt/bridge/src
if [[ -f "$SCRIPT_DIR/run_pipeline.py" && -d "$SCRIPT_DIR/deal_tcl" ]]; then
    SRC_DIR="$SCRIPT_DIR"
elif [[ -f "$SCRIPT_DIR/../run_pipeline.py" && -d "$SCRIPT_DIR/../deal_tcl" ]]; then
    SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    SRC_DIR="$BRIDGE_DIR/src"
fi

BOT_DIR=$BRIDGE_DIR/bot
DEAL_DIR=$BRIDGE_DIR/deal

echo "=== 1. System packages ==="
apt-get update -qq
apt-get install -y \
    g++ \
    libomp-dev \
    tcl \
    deal \
    python3 \
    python3-pip \
    python3-venv \
    git

# If 'deal' is not available in apt, build from source:
if ! command -v deal &>/dev/null; then
    echo "deal not found in apt — building from source..."
    apt-get install -y tcl-dev
    TMP=$(mktemp -d)
    curl -fsSL http://bridge.thomasoandrews.com/deal/deal319.tar.gz -o "$TMP/deal.tar.gz"
    tar -xzf "$TMP/deal.tar.gz" -C "$TMP"
    make -C "$TMP"/deal* install PREFIX=/usr/local
    rm -rf "$TMP"
fi

echo "=== 2. Directory layout ==="
mkdir -p "$BRIDGE_DIR" "$BOT_DIR" "$DEAL_DIR"

echo "Using source directory: $SRC_DIR"
for d in "$SRC_DIR" "$SRC_DIR/src" "$SRC_DIR/examples" "$SRC_DIR/deal_tcl"; do
    if [[ ! -d "$d" ]]; then
        echo "ERROR: required directory not found: $d"
        echo "Hint: run setup.sh from this repo root, or clone repo to /opt/bridge/src"
        exit 1
    fi
done
for f in "$SRC_DIR/bot.py" "$SRC_DIR/run_pipeline.py" "$SRC_DIR/bot.service" "$SRC_DIR/deal_tcl/pbn._nob.tcl"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: required file not found: $f"
        exit 1
    fi
done

# Create a system user if it doesn't exist
id bridge &>/dev/null || useradd -r -s /bin/false -d "$BRIDGE_DIR" bridge

echo "=== 3. Build libdds.so ==="
cd "$SRC_DIR/src"
cp Makefiles/Makefile_linux_shared Makefile_linux_shared_tmp
# Remove Boost dependency (use OpenMP + STL only)
sed 's/THREADING.*=.*/THREADING = $(THR_OPENMP) $(THR_STL)/' Makefile_linux_shared_tmp \
  | sed 's/THREAD_LINK.*=.*/THREAD_LINK = -fopenmp/' \
  > Makefile_linux_build
make -f Makefile_linux_build linux -j"$(nproc)"
cp libdds.so "$BRIDGE_DIR/"
make -f Makefile_linux_build clean
rm Makefile_linux_shared_tmp Makefile_linux_build

echo "=== 4. Build solver_batch ==="
cd "$SRC_DIR/examples"
g++ -O2 -std=c++17 -o "$BRIDGE_DIR/solver_batch" solver_batch.cpp \
    -I"$SRC_DIR/include" \
    -L"$BRIDGE_DIR" -ldds \
    -Wl,-rpath,"$BRIDGE_DIR" \
    -fopenmp

echo "=== 5. Copy deal Tcl files ==="
cp "$SRC_DIR/deal_tcl/pbn._nob.tcl" "$DEAL_DIR/"
# custom.tcl is written at runtime — create a placeholder
touch "$DEAL_DIR/custom.tcl"

echo "=== 6. Python environment ==="
python3 -m venv "$BRIDGE_DIR/venv"
"$BRIDGE_DIR/venv/bin/pip" install --quiet --upgrade pip
"$BRIDGE_DIR/venv/bin/pip" install --quiet discord.py openai

echo "=== 7. Install bot files ==="
cp "$SRC_DIR/bot.py"          "$BOT_DIR/"
cp "$SRC_DIR/run_pipeline.py" "$BOT_DIR/"

if [[ -f "$SRC_DIR/SKILL.md" && -f "$SRC_DIR/bidding.md" ]]; then
    cp "$SRC_DIR/SKILL.md"   "$BOT_DIR/"
    cp "$SRC_DIR/bidding.md" "$BOT_DIR/"
elif [[ -f "$SRC_DIR/.claude/skills/bridge-deal/SKILL.md" && -f "$SRC_DIR/.claude/skills/bridge-deal/bidding.md" ]]; then
    cp "$SRC_DIR/.claude/skills/bridge-deal/SKILL.md"   "$BOT_DIR/"
    cp "$SRC_DIR/.claude/skills/bridge-deal/bidding.md" "$BOT_DIR/"
else
    echo "WARNING: SKILL.md/bidding.md not found; writing placeholders to keep bot startup stable"
    cat > "$BOT_DIR/SKILL.md" <<'EOF'
Bridge skill reference unavailable in this checkout.
EOF
    cat > "$BOT_DIR/bidding.md" <<'EOF'
Bidding reference unavailable in this checkout.
EOF
fi

echo "=== 8. .env file ==="
if [[ ! -f "$BRIDGE_DIR/.env" ]]; then
    cat > "$BRIDGE_DIR/.env" <<'EOF'
DISCORD_TOKEN=your_discord_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
# Optional: fill in for instant slash-command registration in one guild
# OPENAI_MODEL=gpt-4.1
# DISCORD_GUILD_ID=123456789012345678
BRIDGE_DIR=/opt/bridge
EOF
    echo "Created $BRIDGE_DIR/.env — EDIT THIS FILE with your tokens before starting the bot."
else
    echo "$BRIDGE_DIR/.env already exists, skipping."
fi

echo "=== 9. systemd service ==="
cp "$SRC_DIR/bot.service" /etc/systemd/system/bridge-bot.service
systemctl daemon-reload
systemctl enable bridge-bot

echo "=== 10. Permissions ==="
chown -R bridge:bridge "$BRIDGE_DIR"
chmod 640 "$BRIDGE_DIR/.env"

echo ""
echo "============================================================"
echo " Setup complete."
echo ""
echo " Next steps:"
echo "   1. Edit /opt/bridge/.env with your Discord token and"
echo "      OpenAI API key."
echo "   2. Start the bot:  systemctl start bridge-bot"
echo "   3. Check logs:     journalctl -u bridge-bot -f"
echo ""
echo " Slash command:  /bridge <query>"
echo " Example:  /bridge 1NT - 3NT"
echo " Example:  /bridge 1S - 3S north :AKQJ2.KT4.AJ3.87 | deals: 500"
echo "============================================================"
