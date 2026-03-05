# Deployment Guide — Bridge Bot on Linux VM

## Architecture

```
Discord user
    │  /bridge 1NT – 3NT
    ▼
Discord Bot (deploy/bot.py)  — runs on VM at 188.166.232.163
    │
    ├─ Claude API (generates custom.tcl from query)
    │
    ├─ deal (from apt) + custom.tcl  → PBN lines
    │
    └─ solver_batch (built from src) → JSON results
           ↑
       libdds.so (built from src)
```

## First-time setup

### 1. Create a Discord bot

1. Go to https://discord.com/developers/applications → **New Application**
2. **Bot** tab → **Add Bot** → copy the **Token**
3. **OAuth2 → URL Generator**: scope `bot` + `applications.commands`, permission `Send Messages`
4. Open the generated URL to invite the bot to your server
5. (Optional) Under **Bot**: copy your server ID from Discord → `Settings → Advanced → Developer Mode → right-click server → Copy ID`

### 2. Push the repo to the VM

```bash
# On your local machine — push to GitHub first, then on the VM:
ssh root@188.166.232.163
git clone https://github.com/YOUR/ddsnew.git /opt/bridge/src
```

Or rsync directly:
```bash
rsync -avz --exclude '.git' D:/_/ddsnew/ root@188.166.232.163:/opt/bridge/src/
```

### 3. Run setup

```bash
ssh root@188.166.232.163
bash /opt/bridge/src/deploy/setup.sh
```

This installs dependencies, builds `libdds.so` and `solver_batch`, sets up the Python venv, and installs the systemd service.

### 4. Configure tokens

```bash
nano /opt/bridge/.env
```

```env
DISCORD_TOKEN=your_discord_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DISCORD_GUILD_ID=123456789012345678   # your server ID (for instant registration)
BRIDGE_DIR=/opt/bridge
```

### 5. Start the bot

```bash
systemctl start bridge-bot
journalctl -u bridge-bot -f          # watch logs
```

The `/bridge` slash command appears instantly in your guild (or within ~1 hour for global sync).

---

## Usage

```
/bridge 1NT – 3NT
/bridge 1S – 3S north :AKQJ2.KT4.AJ3.87
/bridge 1NT – 2C – 2D | contracts: N:3NT,N:4H | deals: 500
/bridge North is 5-5 majors 11-15 HCP | contracts: N:4S,N:4H
```

---

## File layout on VM

```
/opt/bridge/
  .env                  — secrets (DISCORD_TOKEN, ANTHROPIC_API_KEY)
  libdds.so             — DDS shared library (built from src/src/)
  solver_batch          — DDS solver binary (built from src/examples/)
  venv/                 — Python virtualenv (discord.py, anthropic)
  deal/
    pbn._nob.tcl        — PBN output format for deal319
    custom.tcl          — written at runtime by the bot
  bot/
    bot.py              — Discord bot
    run_pipeline.py     — deal → DDS pipeline
    SKILL.md            — bridge-deal skill (Claude system prompt)
    bidding.md          — SAYC bidding reference
  src/                  — git clone of this repo
```

---

## Updating

```bash
ssh root@188.166.232.163
cd /opt/bridge/src && git pull
bash /opt/bridge/src/deploy/setup.sh   # re-runs safely (idempotent)
systemctl restart bridge-bot
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `libdds.so: cannot open shared object` | `export LD_LIBRARY_PATH=/opt/bridge` or re-run setup.sh |
| `deal: command not found` | `apt-get install deal` or setup.sh builds from source |
| Slash command not showing | Use `DISCORD_GUILD_ID` for instant sync; global sync takes ~1 hour |
| Bot silent after `/bridge` | `journalctl -u bridge-bot -f` — check for missing token or API error |
| `custom.tcl` permissions | `chown bridge:bridge /opt/bridge/deal/custom.tcl` |
