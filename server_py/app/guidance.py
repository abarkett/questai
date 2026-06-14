"""
Onboarding & discovery: a contextual "what now?" that surfaces the right next
thing at the right moment.

The game has grown a lot of systems — quests, companions, raids, a stronghold,
crafting, frontiers, community goals. A new player shouldn't have to already
know they exist. So this reads the player's current state and the world around
them and offers a few pointed nudges toward what they can do *next*.

Every suggestion is **stateless and self-resolving**: it derives purely from
the present state, so it appears only while it's relevant and quietly vanishes
once the player has done the thing. No scripted tutorial sequence, no progress
flags to track — a guide that reads the world instead of remembering it.

Lower `priority` numbers surface first; `suggestions()` returns the top few.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import Player, ActionResponse

# Raid trophies that hint at the forge (kept in step with app/items.py).
_TROPHIES = ("dragon_heart", "coral_crown", "colossus_core")


def guide(player: Player) -> ActionResponse:
    """The `next` command: a short, friendly 'what now?' for this player."""
    from .engine.state_view import build_action_state
    tips = suggestions(player)
    messages = ["What now?"]
    messages.extend(f"• {t['text']}" for t in tips)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )


def guidance_summary(player: Player, limit: int = 4) -> List[Dict[str, Any]]:
    """Suggestions for the web client: just the text and the clickable command."""
    return [{"text": t["text"], "command": t["command"]}
            for t in suggestions(player, limit=limit)]


def _tip(priority: int, text: str, command: Optional[str] = None) -> Dict[str, Any]:
    return {"priority": priority, "text": text, "command": command}


def suggestions(player: Player, limit: int = 4) -> List[Dict[str, Any]]:
    """The top few contextual next-steps for this player, most useful first."""
    tips: List[Dict[str, Any]] = []
    inv = player.inventory or {}
    coin = int(inv.get("coin", 0))

    # Look around once and reuse it (cheap, and avoids re-querying per rule).
    try:
        from .engine.entities import get_entities_at
        entities = get_entities_at(player.location)
    except Exception:
        entities = []
    npcs = [e for e in entities if e.get("type") == "npc"]
    monsters = [e for e in entities if e.get("type") == "monster"]

    # --- survival first ---
    if "wounded" in player.status_effects:
        tips.append(_tip(5, "You're carrying a wound from a defeat — `rest` somewhere safe to shake it off.", "rest"))
    elif player.hp <= max(1, player.max_hp * 0.35):
        tips.append(_tip(6, "You're badly hurt — `rest` to recover before pressing on.", "rest"))

    # --- equip a weapon you're carrying but not wielding ---
    if "weapon" not in (player.equipment or {}):
        from .items import get_item
        weap = next((iid for iid in inv if iid != "coin" and (get_item(iid) and get_item(iid).type == "weapon")), None)
        if weap:
            tips.append(_tip(8, f"You have a weapon in your pack — `equip {weap}` to wield it.", f"equip {weap}"))

    # --- quests: pick one up, or push the one you have ---
    quest_giver = next((n for n in npcs if n.get("role") == "quest_giver"), None)
    if not player.active_quests:
        if quest_giver:
            tips.append(_tip(10, f"{quest_giver['name']} has work for you — `talk {quest_giver['id']}`.", f"talk {quest_giver['id']}"))
        else:
            tips.append(_tip(18, "You have no quests. Seek a quest giver (the Warden, Huntmaster, or Scholar) and `talk` to them.", None))
    else:
        prog = _quest_progress_line(player)
        if prog:
            tips.append(_tip(12, prog, "journal"))

    # --- a recruitable ally is standing right here ---
    if not player.companion:
        from .companions import is_recruitable
        ally = next((n for n in npcs if is_recruitable(n)), None)
        if ally:
            tips.append(_tip(14, f"{ally['name']} could fight at your side — `recruit {ally['id']}`.", f"recruit {ally['id']}"))

    # --- foes to fight, if you're hale enough ---
    if monsters and player.hp > player.max_hp * 0.4 and "wounded" not in player.status_effects:
        m = monsters[0]
        tips.append(_tip(16, f"A {m['name']} prowls here — `fight {m['id']}` to take it on.", f"fight {m['id']}"))

    # --- the stronghold: found it, collect from it ---
    tips.extend(_stronghold_tips(player, coin))

    # --- the raid: a great threat to join ---
    tips.extend(_raid_tips(player))

    # --- an uncharted frontier underfoot ---
    tips.extend(_frontier_tip(player))

    # --- a torn map you're holding ---
    if player.treasure_target:
        if player.treasure_target == player.location:
            tips.append(_tip(15, "Your torn map marks *this* spot — `dig` to claim what's buried.", "dig"))
        else:
            tips.append(_tip(34, "You hold a torn map pointing elsewhere in the world — find the spot and `dig`.", None))

    # --- forge a raid trophy into a relic ---
    if any(inv.get(t, 0) > 0 for t in _TROPHIES):
        tips.append(_tip(30, "You hold a raid trophy — forged with deep-tier ore it becomes a relic (`craft`).", None))

    # --- something you can craft right now ---
    craftable = _first_craftable(inv)
    if craftable:
        tips.append(_tip(32, f"You have the makings of a {craftable[1]} — `craft {craftable[0]}`.", f"craft {craftable[0]}"))

    # --- a season worth joining ---
    tips.extend(_goal_tip(player))

    # --- overflowing pack with somewhere to put it ---
    if player.stronghold_level > 0 and len([k for k in inv if k != "coin"]) >= 8:
        tips.append(_tip(40, "Your pack is heavy — `stash <item>` to store spares at your stronghold.", None))

    tips.sort(key=lambda t: t["priority"])
    chosen = tips[:limit]

    if not chosen:
        chosen = [_tip(99, "The world is wide open. Try `look`, `map`, `goals`, or `explore` — or check your `stronghold`.", None)]
    return chosen


def _quest_progress_line(player: Player) -> Optional[str]:
    try:
        from .engine.quest_progress import current_objectives
    except Exception:
        return None
    for q in player.active_quests.values():
        objs = current_objectives(q)
        for o in objs:
            if o.progress < o.required:
                return f"Quest '{q.name}': {o.target} {o.progress}/{o.required}. Hunt it down to finish."
    return f"You have an active quest — return to its giver to turn it in (`journal`)."


def _stronghold_tips(player: Player, coin: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    from .stronghold import UPGRADE_COST, accrued_tribute
    if player.stronghold_level <= 0:
        if coin >= UPGRADE_COST[1]:
            out.append(_tip(20, f"You can afford a stronghold of your own — `build` a Campsite ({UPGRADE_COST[1]} coins).", "build"))
    else:
        if accrued_tribute(player) > 0:
            out.append(_tip(22, "Tribute has gathered at your stronghold — `collect` it.", "collect"))
    return out


def _raid_tips(player: Player) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if player.level < 3:
        return out
    try:
        from .raids import WARFRONT_LOC
        from .db import get_active_raid_boss
        boss = get_active_raid_boss()
    except Exception:
        return out
    if not boss:
        return out
    if player.location == WARFRONT_LOC:
        out.append(_tip(11, f"{boss['name']} holds the Warfront — `raid strike` to land a blow with the realm.", "raid strike"))
    else:
        out.append(_tip(24, f"A great threat, {boss['name']}, looms at the Warfront — `go warfront` to join the fight.", "go warfront"))
    return out


def _frontier_tip(player: Player) -> List[Dict[str, Any]]:
    try:
        from .regiongen import frontier_at
        from .db import get_region_by_origin
        if frontier_at(player.location) and not get_region_by_origin(player.location):
            return [_tip(26, "Something here remains uncharted — `explore` to open a whole new region.", "explore")]
    except Exception:
        pass
    return []


def _goal_tip(player: Player) -> List[Dict[str, Any]]:
    try:
        from .db import get_active_world_goals
        goals = get_active_world_goals()
    except Exception:
        return []
    if goals:
        g = goals[0]
        return [_tip(36, f"A season is underway — {g['name']}. Every kill counts toward it (`goals`).", "goals")]
    return []


def _first_craftable(inv: Dict[str, int]) -> Optional[tuple]:
    """The first recipe the player has all the materials for (id, display name)."""
    try:
        from .items import RECIPES, get_item
    except Exception:
        return None
    for out_id, recipe in RECIPES.items():
        if inv.get(out_id, 0) > 0:
            continue  # already have one — don't nag
        inputs = recipe.get("inputs", {})
        if inputs and all(inv.get(mat, 0) >= need for mat, need in inputs.items()):
            it = get_item(out_id)
            return (out_id, it.name if it else out_id)
    return None
