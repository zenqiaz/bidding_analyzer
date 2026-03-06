# Bridge Deal Analysis — Usage Guide

This agent analyzes bridge hands using **deal319** (hand dealer) and **DDS 2.9.0** (Double Dummy Solver).
The primary entry point is the `/bridge-deal` skill.

---

## Quick Start

```
/bridge-deal 1NT – 3NT
/bridge-deal 1NT – 2C – 2H | contracts: N:4H,N:3NT | deals: 500
/bridge-deal 1S – 3S north :AKQJ2.KT4.AJ3.87
```

---

## Syntax Reference

```
/bridge-deal <bidding> [SEAT :S.H.D.C ...] [| contracts: ...] [| deals: N]
```

All parts are optional and can appear in any order.

### Bidding sequence

A dash- or arrow-separated auction in SAYC (5-card majors):

```
1NT – 3NT
1NT – 2C – 2H – 4H
1♠ – 2♠
1H – 4H
2NT – 3NT
```

The agent translates each bid into HCP and shape constraints for the relevant seat and infers the contract to evaluate.

### Fixed hand(s)

Pin one or more seats to a specific hand:

```
SEAT :S.H.D.C
```

- `SEAT` — `north`, `south`, `east`, or `west`
- `S.H.D.C` — card ranks per suit (spades · hearts · diamonds · clubs), **void = empty**

| Input | Meaning |
|-------|---------|
| `north :AQ73..AT9842.KQJ` | North: ♠AQ73 ♥void ♦AT9842 ♣KQJ |
| `south :K742.873.AQ6.KT2` | South: ♠K742 ♥873 ♦AQ6 ♣KT2 |
| `east :AKQJ.T98.-.7654`   | East: ♠AKQJ ♥T98 ♦void ♣7654 |

A fixed hand replaces bidding-derived constraints for that seat.

### Contracts override

```
| contracts: N:3NT,S:4H,N:6D
```

Format: `HAND:LEVELSTRAIN`, comma-separated.
`HAND` = N/E/S/W (declarer seat); `STRAIN` = NT/S/H/D/C.

If omitted, the agent infers the contract from the auction.

### Deals count

```
| deals: 1000
```

Default is **1000**. More deals = more accurate probabilities but slower.

---

## Examples

### Simple auction
```
/bridge-deal 1NT – 3NT
```
Generates 1000 random hands satisfying 1NT opener (15–17 HCP, balanced) and 3NT responder (10–15 HCP), evaluates `N:3NT`.

### With fixed declarer hand
```
/bridge-deal 1NT – 3NT north :AQ73.KJ5.AJ4.KQ8
```
North is fixed; south is constrained to 10–15 HCP. Evaluates `N:3NT`.

### Multiple contracts
```
/bridge-deal 1NT – 2C – 2D north :AQ73..AT9842.KQJ | contracts: N:6D,N:7D,S:6NT,S:7NT
```
Evaluates four contracts simultaneously on the same deal set.

### Custom deal count
```
/bridge-deal 1S – 3S | deals: 2000
```

### Natural language (no auction)
```
/bridge-deal North is 5-5 in the majors, 11-15 HCP | contracts: N:4S,N:4H
```

---

## Output

The agent reports:
1. **Constraints applied** — how the bidding was interpreted
2. **Make-probability table:**

| Contract | Makes | Total | Probability |
|----------|-------|-------|-------------|
| N 3NT    | 310   | 1000  | 31.0%       |
| N 6NT    | 42    | 1000  | 4.2%        |

---

## How It Works (Pipeline)

```
/bridge-deal arguments
    ↓
custom.tcl (Tcl constraint script written to D:\_\deal319\)
    ↓
deal.exe -i pbn._nob.tcl -i custom.tcl <N>   (runs from D:\_\deal319\)
    ↓ fix void notation (.. → -)
solver_batch.exe --contracts_named="..."      (SolveAllBoards, 200 boards/DDS call)
    ↓
JSON → make-probability table
```

Key tools:
| Tool | Path |
|------|------|
| Hand dealer | `D:\_\deal319\deal.exe` |
| Pipeline script | `D:\_\deal319\run_pipeline.py` |
| DDS solver | `D:\_\dds\dds\examples\solver_batch.exe` |
| Constraint script | `D:\_\deal319\custom.tcl` (overwritten each run) |

---

## Bidding System

SAYC (Standard American Yellow Card), 5-card majors:

| Opening | HCP | Shape |
|---------|-----|-------|
| 1NT | 15–17 | Balanced (no void/singleton, no 5-card major) |
| 2NT | 20–21 | Balanced |
| 1♠/1♥ | 12–21 | 5+ cards in bid major |
| 1♦/1♣ | 12–21 | 3+/4+ cards |
| 2♦/2♥/2♠ | 5–11 | 6+ cards (weak two) |

Conventions handled: Stayman (2♣), Jacoby transfers (2♦/2♥ over 1NT), Bergen raises, limit raises.

---

## Notes

- `custom.tcl` is **overwritten** on every run. To save a constraint script, copy it elsewhere.
- Do not use `dds_wrapper.exe` — it has a swapped index bug that returns wrong trick counts.
- deal319 is non-deterministic by default; results vary between runs. Use more deals for stability.
