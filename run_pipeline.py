"""run_pipeline.py — generate deals and run DDS analysis (Linux paths)."""
import subprocess, sys, os, json

BRIDGE_DIR  = os.environ.get("BRIDGE_DIR", "/opt/bridge")
DEAL_DIR    = os.path.join(BRIDGE_DIR, "deal")
DEAL_EXE    = "deal"                                      # installed via apt
SOLVER      = os.path.join(BRIDGE_DIR, "solver_batch")
LIB_PATH    = BRIDGE_DIR                                  # where libdds.so lives

N_DEALS     = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
CONTRACTS   = sys.argv[2] if len(sys.argv) > 2 else "N:3NT"


def fix_hand(hand: str) -> str:
    return '.'.join(s if s else '-' for s in hand.split('.'))


def fix_voids(line: str) -> str:
    inner = line.strip().strip('"')
    if not inner.startswith('N:'):
        return line
    parts = inner.split(' ')
    north = 'N:' + fix_hand(parts[0][2:])
    rest = [fix_hand(h) for h in parts[1:]]
    return '"' + north + ' ' + ' '.join(rest) + '"'


# ── Step 1: generate deals ────────────────────────────────────────────────
print(f"Generating {N_DEALS} deals...", file=sys.stderr)
result = subprocess.run(
    [DEAL_EXE, "-i", "pbn._nob.tcl", "-i", "custom.tcl", str(N_DEALS)],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    cwd=DEAL_DIR
)
if result.returncode != 0:
    sys.exit(f"deal error:\n{result.stderr[:500]}")

lines = [fix_voids(l) for l in result.stdout.splitlines() if l.strip()]
print(f"Generated {len(lines)} deals.", file=sys.stderr)

# ── Step 2: DDS analysis ──────────────────────────────────────────────────
print(f"Running DDS analysis ({CONTRACTS})...", file=sys.stderr)
env = os.environ.copy()
env["LD_LIBRARY_PATH"] = LIB_PATH + ":" + env.get("LD_LIBRARY_PATH", "")

proc = subprocess.run(
    [SOLVER, "--contracts_named=" + CONTRACTS],
    input="\n".join(lines) + "\n",
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    env=env
)
if proc.returncode != 0:
    sys.exit(f"solver_batch error:\n{(proc.stderr or proc.stdout)[:500]}")

try:
    res = json.loads(proc.stdout)
except json.JSONDecodeError as e:
    sys.exit(f"JSON parse error: {e}\n{proc.stdout[:400]}")

# ── Step 3: output ────────────────────────────────────────────────────────
print(json.dumps({"summary": res["summary"], "total_deals": len(lines)}, indent=2))
