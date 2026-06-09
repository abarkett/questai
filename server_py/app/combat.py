"""
Damage rolling: per-hit variance and critical hits.

Pure and RNG-injectable so combat has texture in play but stays deterministic
under test.
"""

from __future__ import annotations

import random
from typing import Optional, Tuple

CRIT_CHANCE = 0.15   # 15% chance to crit
CRIT_MULT = 2.0      # crits deal double
VARIANCE = 0.25      # damage rolls within +/-25% of base


def roll_damage(base: int, *, rng: Optional[random.Random] = None) -> Tuple[int, bool]:
    """
    Roll a single hit. Returns (damage, is_crit). Damage is at least 1.
    `base` is the pre-variance damage (level + gear + ability multiplier).
    """
    r = rng or random
    lo = max(1, int(base * (1 - VARIANCE)))
    hi = max(lo, int(base * (1 + VARIANCE)))
    dmg = r.randint(lo, hi)

    is_crit = r.random() < CRIT_CHANCE
    if is_crit:
        dmg = int(dmg * CRIT_MULT)

    return max(1, dmg), is_crit
