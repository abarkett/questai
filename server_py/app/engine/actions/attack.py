from __future__ import annotations

import time
from ...types import Player, ActionResponse
from ...db import upsert_player, log_reputation_event
from ...world import get_location
from ...factions import get_npc_faction, get_location_factions, get_reputation_event_value
from ..entities import (
    find_entity,
    find_player_by_name_at,
    get_entities_at,
    serialize_entity,
    remove_entity,
    get_adjacent_scenes,
    get_world_entities_at,
    filter_current_player,
)
from ..state_view import build_action_state
from ...progression import total_attack_damage, defense_bonus, apply_xp
from ...combat import roll_damage
from ...abilities import get_ability
from ...status_effects import tick_effects, damage_modifier, apply_effect
from ...content import monster_inflicts


# Simple shared combat constants
PLAYER_DAMAGE = 3
RESPAWN_LOCATION = "town_square"

# Protection and cooldown constants (in seconds)
RESPAWN_PROTECTION_SECONDS = 300  # 5 minutes protection after defeat
ATTACK_COOLDOWN_SECONDS = 30  # 30 seconds before attacking same target again


def update_quest_progress(player: Player, target_name: str) -> list[str]:
    """
    Update quest progress for kill objectives.
    Also updates progress for party members at the same location.
    Returns list of quest completion messages.
    """
    from ...db import get_player_party, get_player, upsert_player

    messages = []
    completed_quest_ids = []

    # Get all party members (regardless of location)
    party_members_to_update = []
    party = get_player_party(player.player_id)
    print(f"[PARTY QUEST] Player {player.name} has party: {party is not None}")
    if party:
        print(f"[PARTY QUEST] Party members: {party['members']}")
        for member_id in party["members"]:
            if member_id == player.player_id:
                continue  # Skip self, we'll update them directly
            member = get_player(member_id)
            if member:
                print(f"[PARTY QUEST] Adding {member.name} to quest update list (location: {member.location})")
                party_members_to_update.append(member)

    # Update quest progress for player and party members
    all_players = [player] + party_members_to_update

    for p in all_players:
        player_messages = []
        player_completed = []

        from ...engine.quest_progress import current_objectives, completion_message, stage_message

        for quest_id, quest in p.active_quests.items():
            if quest.status != "accepted":
                continue

            objs = current_objectives(quest)
            for objective in objs:
                if objective.type == "kill" and objective.target.lower() == target_name.lower():
                    if objective.progress < objective.required:
                        objective.progress += 1
                        player_messages.append(f"Quest progress: {quest.name} ({objective.progress}/{objective.required})")

                        # Stage / completion check on the current stage's objectives.
                        if all(obj.progress >= obj.required for obj in objs):
                            if quest.stages and quest.current_stage < len(quest.stages) - 1:
                                quest.current_stage += 1
                                player_messages.append(stage_message(quest))
                            else:
                                quest.status = "completed"
                                quest.completed_at = int(time.time() * 1000)
                                player_completed.append(quest_id)
                                player_messages.append(completion_message(quest))
                        break

        # Move completed quests after iteration
        for quest_id in player_completed:
            p.completed_quests[quest_id] = p.active_quests[quest_id]
            del p.active_quests[quest_id]

        # Save party member updates
        if p.player_id != player.player_id:
            upsert_player(p)
            # Add party member messages to main messages with prefix
            for msg in player_messages:
                messages.append(f"[Party] {p.name}: {msg}")
        else:
            # Add player's own messages
            messages.extend(player_messages)
            completed_quest_ids.extend(player_completed)

    return messages


def is_player_attackable(target: Player, attacker: Player, current_time_ms: int) -> tuple[bool, str | None]:
    """
    Check if a player can be attacked.
    Returns (is_attackable, error_message)
    """
    # Check if target just respawned (defeated recently)
    if target.last_defeated_at:
        time_since_defeat = (current_time_ms - target.last_defeated_at) / 1000
        if time_since_defeat < RESPAWN_PROTECTION_SECONDS:
            remaining = int(RESPAWN_PROTECTION_SECONDS - time_since_defeat)
            return False, f"That player has just respawned. Protected for {remaining} more seconds."
    
    # Check if attacker is on cooldown for attacking this specific target
    if (attacker.last_attacked_target == target.name and 
        attacker.last_attacked_at):
        time_since_attack = (current_time_ms - attacker.last_attacked_at) / 1000
        if time_since_attack < ATTACK_COOLDOWN_SECONDS:
            remaining = int(ATTACK_COOLDOWN_SECONDS - time_since_attack)
            return False, f"You must wait {remaining} more seconds before attacking {target.name} again."
    
    return True, None


def resolve_monster_kill(player: Player, entity_id: str, result: dict) -> list[str]:
    """Everything that happens when a monster dies: cleanup, loot, XP, quests."""
    from ...bosses import clear_boss_state
    from ..entities import record_monster_death
    from ...dots import clear_bleed

    messages: list[str] = []
    clear_boss_state(entity_id, result["name"])
    clear_bleed(entity_id)
    record_monster_death(entity_id)  # schedule its respawn
    messages.append(f"The {result['name']} is defeated.")

    # Loot drops go straight into the inventory.
    for item, qty in (result.get("loot") or {}).items():
        player.inventory[item] = player.inventory.get(item, 0) + qty
        messages.append(f"You found: {qty}x {item}")

    # XP and any level-ups from the kill.
    messages.extend(apply_xp(player, result.get("xp_reward") or 0))

    # Rare bonus drops: trinkets, and relics that enter world history.
    from ...loot import roll_bonus_loot
    messages.extend(roll_bonus_loot(player, result["name"]))

    # Update quest progress
    messages.extend(update_quest_progress(player, result["name"]))

    # Track monster deaths for world evolution
    from ...world_rules import track_monster_survival
    track_monster_survival(player.location)

    # Leave an echo for other players who pass through here.
    from ...echoes import record_deed
    record_deed(player, player.location, f"{player.name} slew a {result['name']} here")

    # Anyone's open bounty on this monster pays out to the killer.
    from ...db import claim_bounty_for_kill
    bounty = claim_bounty_for_kill(result["name"], player.player_id, player.name)
    if bounty:
        player.inventory["coin"] = player.inventory.get("coin", 0) + bounty["reward_coins"]
        messages.append(
            f"Bounty claimed! {bounty['poster_name']}'s contract pays you "
            f"{bounty['reward_coins']} coins for the {result['name']}."
        )
        record_deed(
            player, player.location,
            f"{player.name} claimed {bounty['poster_name']}'s bounty on a {result['name']}",
            kind="bounty",
        )

    # Community goals advance with every kill (see app/world_goals.py).
    from ...world_goals import record_kill_progress
    messages.extend(record_kill_progress(player, result["name"]))
    return messages


def monster_retaliation(
    player: Player,
    entity_id: str,
    result: dict,
    *,
    taken_mult: float = 1.0,
) -> list[str]:
    """A surviving monster strikes back (with boss mechanics and afflictions)."""
    messages: list[str] = []
    raw = result.get("attack") or 2
    retaliation = max(1, int(round(raw * taken_mult)) - defense_bonus(player))
    player.hp -= retaliation
    messages.append(f"The {result['name']} hits you for {retaliation} damage.")

    # Some monsters afflict a status effect when they land a blow.
    inflict = monster_inflicts(result["name"])
    if inflict and player.hp > 0:
        msg = apply_effect(
            player,
            inflict["effect"],
            inflict.get("magnitude", 1),
            inflict.get("turns", 1),
        )
        if msg:
            messages.append(msg)

    # Boss mechanics: enrage / summon adds once below the HP threshold.
    from ...bosses import trigger_boss_on_hit
    messages.extend(trigger_boss_on_hit(entity_id, result))

    if player.hp <= 0:
        player.hp = player.max_hp
        player.location = RESPAWN_LOCATION
        player.last_defeated_at = int(time.time() * 1000)
        player.status_effects.clear()
        messages.append(
            f"You were defeated by the {result['name']} and wake up back in the Town Square."
        )
    return messages


def attack(player: Player, target_name: str, ability: str | None = None) -> ActionResponse:
    messages: list[str] = []
    current_time_ms = int(time.time() * 1000)

    # Status effects tick as time passes in combat; a lingering DoT can be fatal.
    messages.extend(tick_effects(player))
    if player.hp <= 0:
        player.hp = player.max_hp
        player.location = RESPAWN_LOCATION
        player.last_defeated_at = current_time_ms
        player.status_effects.clear()
        messages.append("Your wounds overcome you. You wake back in the Town Square.")
        upsert_player(player)
        return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=True))

    # Bleed (monster DoT) ticks on your strikes.
    from ...dots import tick_bleeds
    messages.extend(tick_bleeds(player.location))

    # An offensive ability scales the hit and triggers its cooldown on use.
    ability_obj = get_ability(ability) if ability else None
    mult = ability_obj.multiplier if (ability_obj and ability_obj.multiplier) else 1.0
    label = f"{ability_obj.name}! " if ability_obj else ""

    base = int((total_attack_damage(player) + damage_modifier(player)) * mult)
    dmg, is_crit = roll_damage(base)
    crit_suffix = " (CRITICAL HIT!)" if is_crit else ""

    def _start_cooldown() -> None:
        if ability_obj:
            player.ability_cooldowns[ability_obj.ability_id] = (
                current_time_ms + ability_obj.cooldown_s * 1000
            )

    # -------------------------------------------------
    # Try PvE first (monsters)
    # -------------------------------------------------
    entity = find_entity(player.location, target_name)
    if entity and entity["type"] == "monster":
        from ...bestiary import discover
        discover(player, entity["name"])
        # Atomic, persistent monster combat (safe under concurrent attackers).
        from ...db import damage_monster
        result = damage_monster(entity["id"], dmg)

        if result is None:
            # Another player already finished it off between our look and our hit.
            return ActionResponse(
                ok=True,
                messages=[f"The {entity['name']} is already gone."],
                state=build_action_state(player, scene_dirty=True),
            )

        _start_cooldown()
        messages.append(f"{label}You attack the {result['name']} for {dmg} damage.{crit_suffix}")

        if result["killed"]:
            messages.extend(resolve_monster_kill(player, entity["id"], result))
        else:
            messages.extend(monster_retaliation(player, entity["id"], result))

        # A second hostile in the area may join the fray.
        if player.hp > 0:
            from ...ambush import maybe_ambush
            joiner = maybe_ambush(player, exclude_id=entity["id"], chance=0.35)
            if joiner:
                messages.append("Another enemy joins the fight!")
                messages.extend(joiner)

        upsert_player(player)

        return ActionResponse(
            ok=True,
            messages=messages,
            state=build_action_state(player, scene_dirty=True),
        )

    # -------------------------------------------------
    # PvP combat
    # -------------------------------------------------
    target_player = find_player_by_name_at(player.location, target_name)

    if not target_player:
        return ActionResponse(ok=False, error="There is no one here by that name.")

    if target_player.player_id == player.player_id:
        return ActionResponse(ok=False, error="You can't attack yourself.")

    # Check if target is attackable
    attackable, error_msg = is_player_attackable(target_player, player, current_time_ms)
    if not attackable:
        return ActionResponse(
            ok=True,
            messages=[error_msg],
            state=build_action_state(player, scene_dirty=False),
        )

    _start_cooldown()
    pvp_dmg = max(1, dmg - defense_bonus(target_player))
    messages.append(f"{label}You attack {target_player.name} for {pvp_dmg} damage.{crit_suffix}")

    target_player.hp -= pvp_dmg

    if target_player.hp <= 0:
        messages.append(f"{target_player.name} is defeated!")
        target_player.hp = target_player.max_hp
        target_player.location = RESPAWN_LOCATION
        target_player.last_defeated_at = current_time_ms
        messages.append(f"{target_player.name} is sent back to the Town Square.")

    # Update attacker's last attack info
    player.last_attacked_target = target_player.name
    player.last_attacked_at = current_time_ms

    # Phase 9: Log reputation events for PvP in faction territory
    location_factions = get_location_factions(player.location)
    if location_factions:
        # Attacking in faction territory damages reputation
        for faction in location_factions:
            value = get_reputation_event_value("attacked_in_territory")
            log_reputation_event(
                player_id=player.player_id,
                faction_id=faction.faction_id,
                event_type="attacked_in_territory",
                value=value,
                description=f"Attacked {target_player.name} in {faction.name} territory",
                location_id=player.location
            )

    upsert_player(target_player)
    upsert_player(player)

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )