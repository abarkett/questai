"""
Defeat and its stakes.

Being beaten finally costs something — but for a casual, shared world the price
is a sting, not a spiral. When you fall you:

  * scatter a fraction of the coin you were carrying where you fell,
  * carry a *wound* out of it that dulls your blows for a few combat actions,
  * shake your companion's loyalty (and they can lose heart entirely and leave
    if you keep falling), and
  * leave a "fallen here" echo for whoever passes through next.

Then you wake, recovered, back in town. Every defeat in the game — monster
combat, lingering poison, travel ambushes, the raid Warfront — routes through
`apply_defeat`, so the stakes are consistent everywhere and live in one place.
"""

from __future__ import annotations

import time
from typing import List

from .types import Player

RESPAWN_LOCATION = "town_square"
RESPAWN_LOCATION_NAME = "the Town Square"

# Stakes, kept deliberately gentle — a casual game punishes lightly.
COIN_LOSS_FRAC = 0.20          # share of carried coin scattered on defeat
COMPANION_LOYALTY_LOSS = 10    # loyalty an ally loses when you fall
WOUND_MAGNITUDE = 2            # damage your blows lose while wounded
WOUND_TURNS = 3               # combat actions the wound lingers


def now_ms() -> int:
    return int(time.time() * 1000)


def apply_defeat(player: Player, cause: str) -> List[str]:
    """
    Resolve a defeat: take the stakes, then respawn the player in town.

    `cause` is a short noun phrase ("the Wolf", "an ambush", "The Ashen
    Dragon") used in the wake-up line and the echo left behind. Returns the
    player-facing messages; the caller persists the player.
    """
    messages: List[str] = []
    fell_at = player.location

    # 1. Scatter some coin where you fell.
    coins = int(player.inventory.get("coin", 0))
    lost = min(coins, int(coins * COIN_LOSS_FRAC))
    if lost > 0:
        player.inventory["coin"] = coins - lost
        messages.append(f"You scatter {lost} coins as you fall.")

    # 2. Your companion takes it hard — and can lose heart entirely.
    if player.companion:
        c = player.companion
        c.loyalty -= COMPANION_LOYALTY_LOSS
        if c.loyalty < 0:
            messages.append(f"{c.name}, seeing you fall, loses heart and slips away.")
            player.companion = None
        else:
            messages.append(f"{c.name} hauls you clear of the worst of it.")

    # 3. Respawn, then carry a wound out of it (applied AFTER clearing effects,
    #    so the wound is the one thing that follows you home).
    player.hp = player.max_hp
    player.location = RESPAWN_LOCATION
    player.last_defeated_at = now_ms()
    player.status_effects.clear()
    from .status_effects import apply_effect
    apply_effect(player, "wounded", WOUND_MAGNITUDE, WOUND_TURNS)

    # 4. Leave a trace for others, and tell the player where they woke.
    from .echoes import record_deed
    try:
        record_deed(player, fell_at, f"{player.name} fell to {cause} here", kind="defeat")
    except Exception:
        pass
    messages.append(
        f"You are overcome by {cause} and wake, wounded, back in {RESPAWN_LOCATION_NAME}."
    )
    return messages
