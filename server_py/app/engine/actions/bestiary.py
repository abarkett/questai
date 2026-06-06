from __future__ import annotations

from ...types import Player, ActionResponse
from ...bestiary import catalog_entry, known_monster, all_monster_names
from ..state_view import build_action_state


def bestiary(player: Player) -> ActionResponse:
    discovered = [
        catalog_entry(n) for n in player.discovered_monsters if known_monster(n)
    ]
    discovered.sort(key=lambda e: e["name"])
    total = len(all_monster_names())

    messages = [f"Bestiary — {len(discovered)}/{total} discovered:"]
    if not discovered:
        messages.append("  (nothing yet — explore and fight to fill these pages)")
    for e in discovered:
        eff = f", inflicts {e['inflicts']}" if e.get("inflicts") else ""
        where = ", ".join(e["locations"])
        messages.append(
            f"  {e['name']} — HP {e['max_hp']}, ATK {e['attack']}, {e['xp_reward']} XP{eff}"
            f" (found in: {where})"
        )

    state = build_action_state(player, scene_dirty=False)
    state["bestiary"] = {"total": total, "discovered": discovered}

    return ActionResponse(ok=True, messages=messages, state=state)
