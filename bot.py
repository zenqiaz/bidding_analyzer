"""bridge-bot.py — Discord slash-command interface to the bridge deal pipeline.

Environment variables required:
    DISCORD_TOKEN       — Discord bot token
    OPENAI_API_KEY      — OpenAI API key
    OPENAI_MODEL        — (optional) OpenAI model, default gpt-4.1
    DISCORD_GUILD_ID    — (optional) Guild ID for instant slash-command registration
    BRIDGE_DIR          — (optional) Install root, default /opt/bridge
"""

import os
import json
import asyncio
import subprocess
import textwrap

import discord
from discord import app_commands
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
GUILD_ID      = int(os.environ["DISCORD_GUILD_ID"]) if os.environ.get("DISCORD_GUILD_ID") else None

BRIDGE_DIR  = os.environ.get("BRIDGE_DIR", "/opt/bridge")
DEAL_DIR    = os.path.join(BRIDGE_DIR, "deal")
PIPELINE    = os.path.join(BRIDGE_DIR, "bot", "run_pipeline.py")
CUSTOM_TCL  = os.path.join(DEAL_DIR, "custom.tcl")

# Load skill knowledge for the LLM system prompt
_HERE = os.path.dirname(__file__)

def _read_optional(path: str, fallback: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return fallback

SKILL_MD = _read_optional(
    os.path.join(_HERE, "SKILL.md"),
    "Skill parsing rules unavailable in this deployment.",
)
BIDDING_MD = _read_optional(
    os.path.join(_HERE, "bidding.md"),
    "Bidding reference unavailable in this deployment.",
)

SYSTEM_PROMPT = f"""
You are an assistant for bridge hand analysis. Your job is to interpret a user's
bridge query (bidding sequence, fixed hands, contract specifications) and output
ONLY a JSON object with the following fields:

{{
  "tcl": "<full contents of custom.tcl to write>",
  "contracts": "<comma-separated contracts e.g. N:3NT,S:4H>",
  "n_deals": <integer number of deals, default 1000>
}}

Rules for generating the Tcl:
- Place `SEAT is "..."` lines BEFORE main {{}}
- Use `shapeclass balanced {{...}}` inside main {{}} as needed
- Apply HCP/shape accept constraints only for non-fixed seats
- Use deal319 helpers: hcp, spades, hearts, diamonds, clubs (all take a seat name)
- Void suits use `-` in the is-string (e.g. `north is "AQ73 - AT9842 KQJ"`)

Bidding system reference:
{BIDDING_MD}

Skill reference (parsing rules):
{SKILL_MD}

Output ONLY the JSON object. No explanation, no markdown fences.
""".strip()

# ── OpenAI helper ─────────────────────────────────────────────────────────────
_client = OpenAI(api_key=OPENAI_KEY)


def ask_openai(query: str) -> dict:
    """Call OpenAI to translate a bridge query into tcl + contracts + n_deals."""
    msg = _client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=1024,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    )
    text = (msg.choices[0].message.content or "").strip()
    # Strip markdown fences if the model ignores the instruction
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


# ── Pipeline runner ───────────────────────────────────────────────────────────
def run_pipeline(n_deals: int, contracts: str) -> dict:
    """Synchronous: run the deal→DDS pipeline and return parsed JSON."""
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = BRIDGE_DIR + ":" + env.get("LD_LIBRARY_PATH", "")
    proc = subprocess.run(
        ["python3", PIPELINE, str(n_deals), contracts],
        capture_output=True, text=True, env=env, timeout=300
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


# ── Result formatter ──────────────────────────────────────────────────────────
def format_results(data: dict, query: str) -> discord.Embed:
    embed = discord.Embed(
        title="Bridge Analysis",
        description=f"`{query}`",
        colour=discord.Colour.dark_green(),
    )
    rows = []
    for item in data["summary"]:
        pct = item["prob"] * 100
        rows.append(f"`{item['label']:8s}` {item['makes']:>5}/{item['total']}  **{pct:.1f}%**")
    embed.add_field(name="Results", value="\n".join(rows), inline=False)
    embed.set_footer(text=f"{data['total_deals']} deals")
    return embed


# ── Discord bot ───────────────────────────────────────────────────────────────
intents = discord.Intents.default()
bot     = discord.Client(intents=intents)
tree    = app_commands.CommandTree(bot)

guild_obj = discord.Object(id=GUILD_ID) if GUILD_ID else None


@tree.command(name="bridge", description="Analyze bridge hand make-probabilities")
@app_commands.describe(query="Bidding sequence, fixed hands, contracts, deals count")
async def bridge_cmd(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)

    loop = asyncio.get_running_loop()
    try:
        # 1. Ask OpenAI to generate Tcl + contract info
        plan = await loop.run_in_executor(None, ask_openai, query)

        tcl       = plan["tcl"]
        contracts = plan.get("contracts", "N:3NT")
        n_deals   = int(plan.get("n_deals", 1000))

        # 2. Write custom.tcl
        os.makedirs(DEAL_DIR, exist_ok=True)
        with open(CUSTOM_TCL, "w", encoding="utf-8") as f:
            f.write(tcl)

        # 3. Run pipeline
        data = await loop.run_in_executor(
            None, run_pipeline, n_deals, contracts
        )

        # 4. Reply
        embed = format_results(data, query)
        embed.add_field(
            name="Tcl constraints",
            value=f"```tcl\n{textwrap.shorten(tcl, 500, placeholder=' …')}\n```",
            inline=False,
        )
        await interaction.followup.send(embed=embed)

    except json.JSONDecodeError as e:
        await interaction.followup.send(f"OpenAI returned invalid JSON: {e}")
    except RuntimeError as e:
        await interaction.followup.send(f"Pipeline error:\n```\n{str(e)[:800]}\n```")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@tree.command(name="bridge-tcl", description="Analyze bridge hands with a raw deal319 Tcl script")
@app_commands.describe(
    tcl="Full custom.tcl contents",
    contracts="Contracts to evaluate e.g. N:3NT,S:4H",
    deals="Number of deals (default 100)",
)
async def bridge_tcl_cmd(
    interaction: discord.Interaction,
    tcl: str,
    contracts: str = "N:3NT",
    deals: int = 100,
):
    await interaction.response.defer(thinking=True)
    try:
        os.makedirs(DEAL_DIR, exist_ok=True)
        with open(CUSTOM_TCL, "w", encoding="utf-8") as f:
            f.write(tcl)

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, run_pipeline, deals, contracts)

        embed = format_results(data, f"{contracts} | deals: {deals}")
        embed.add_field(
            name="Tcl",
            value=f"```tcl\n{textwrap.shorten(tcl, 500, placeholder=' …')}\n```",
            inline=False,
        )
        await interaction.followup.send(embed=embed)
    except RuntimeError as e:
        await interaction.followup.send(f"Pipeline error:\n```\n{str(e)[:800]}\n```")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@bot.event
async def on_ready():
    print(f"on_ready fired: {bot.user}  |  guild_id={GUILD_ID}", flush=True)
    try:
        await tree.sync(guild=guild_obj)
        print("Slash commands synced successfully.", flush=True)
    except Exception as e:
        print(f"ERROR syncing commands: {e}", flush=True)


bot.run(DISCORD_TOKEN)
