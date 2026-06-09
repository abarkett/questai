"""
Collapsed-encounter combat: one action resolves a whole fight.

Where `attack` is a single exchange of blows, `fight` presses the engagement
until the monster falls, you're forced to disengage, or you're defeated —
with a stance choosing the risk/reward trade. One action, one meaningful
encounter: the right shape for short sessions and SMS play.
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player, damage_monster
from ...combat import roll_damage
from ...progression import total_attack_damage, defense_bonus
from ...status_effects import tick_effects, damage_modifier
from ..entities import find_entity
from ..state_view import build_action_state
from .attack import RESPAWN_LOCATION, resolve_monster_kill, monster_retaliation

MAX_ROUNDS = 10

# stance -> (damage dealt multiplier, damage taken multiplier,
#            disengage when HP falls below this fraction of max)
STANCES = {
    "bold": (1.25, 1.25, 0.15),
    "standard": (1.0, 1.0, 0.35),
    "cautious": (0.8, 0.6, 0.5),
}


def fight(player: Player, target_name: str, stance: str = "standard") -> ActionResponse:
    import time

    if stance not in STANCES:
        return ActionResponse(ok=False, error="Stance must be bold, standard, or cautious.")
    dealt_mult, taken_mult, disengage_at = STANCES[stance]

    entity = find_entity(player.location, target_name)
    if not entity:
        return ActionResponse(ok=False, error="There is nothing here by that name.")
    if entity["type"] == "player":
        return ActionResponse(ok=False, error="Duels are blow-by-blow: use attack for players.")
    if entity["type"] != "monster":
        return ActionResponse(ok=False, error="You can't fight that.")

    messages: list[str] = []
    if stance != "standard":
        messages.append(f"You take a {stance} stance.")

    # Lingering effects tick once as the fight begins.
    messages.extend(tick_effects(player))
    if player.hp <= 0:
        player.hp = player.max_hp
        player.location = RESPAWN_LOCATION
        player.last_defeated_at = int(time.time() * 1000)
        player.status_effects.clear()
        messages.append("Your wounds overcome you. You wake back in the Town Square.")
        upsert_player(player)
        return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=True))

    from ...bestiary import discover
    discover(player, entity["name"])

    from ...dots import tick_bleeds
    messages.extend(tick_bleeds(player.location))

    outcome = "stalemate"
    for _ in range(MAX_ROUNDS):
        base = int((total_attack_damage(player) + damage_modifier(player)) * dealt_mult)
        dmg, is_crit = roll_damage(base)
        result = damage_monster(entity["id"], dmg)
        if result is None:
            messages.append(f"The {entity['name']} is already gone.")
            outcome = "gone"
            break

        crit_suffix = " (CRITICAL HIT!)" if is_crit else ""
        messages.append(f"You strike the {result['name']} for {dmg} damage.{crit_suffix}")

        if result["killed"]:
            messages.extend(resolve_monster_kill(player, entity["id"], result))
            outcome = "victory"
            break

        prev_defeated_at = player.last_defeated_at
        messages.extend(monster_retaliation(player, entity["id"], result, taken_mult=taken_mult))
        if player.last_defeated_at != prev_defeated_at:
            # monster_retaliation respawned us: the fight is lost.
            outcome = "defeat"
            break

        if player.hp <= int(player.max_hp * disengage_at):
            messages.append(
                f"Bloodied, you break off the fight. The {result['name']} still prowls here."
            )
            outcome = "disengage"
            break

    if outcome == "stalemate":
        messages.append(f"You trade blows but neither side gives. The {entity['name']} endures.")

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=True),
    )
