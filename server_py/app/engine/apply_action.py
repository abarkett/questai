from __future__ import annotations

from typing import Optional, Any

from pydantic import TypeAdapter

from ..types import ActionRequest, ActionResponse
from ..db import get_player, log_action, increment_world_turn, get_world_turn

from .actions.create_player import create_player
from .actions.look import look
from .actions.move import move
from .actions.attack import attack
from .actions.stats import stats
from .actions.inventory import inventory
from .actions.use import use 
from .actions.talk import talk
from .actions.buy import buy
from .actions.accept_quest import accept_quest
from .actions.turn_in_quest import turn_in_quest
from .actions.offer_trade import offer_trade
from .actions.accept_trade import accept_trade
from .actions.list_trades import list_trades
from .actions.cancel_trade import cancel_trade
from .actions.party_invite import party_invite
from .actions.accept_party_invite import accept_party_invite
from .actions.leave_party import leave_party
from .actions.party_status import party_status
from .actions.reputation import reputation
from .actions.equip import equip, unequip
from .actions.sell import sell
from .actions.craft import craft
from .actions.gather import gather
from .actions.use_ability import use_ability
from .actions.heal import heal
from .actions.world_map import world_map
from .actions.bestiary import bestiary
from .actions.journal import journal
from .actions.story import story_status, begin_arc, choose


_action_adapter = TypeAdapter(ActionRequest)

# Actions that neither advance the world clock nor cost action points:
# pure reads of your own state or the world.
PASSIVE_ACTIONS = {
    "look", "stats", "inventory", "party_status", "reputation",
    "list_trades", "story", "map", "bestiary", "journal",
    "bounties", "goals", "companion", "raid_status",
    # Stronghold actions are personal bookkeeping: no AI, no shared-world
    # effect, so they don't draw on action points.
    "stronghold", "build_stronghold", "stash", "unstash", "collect_tribute",
    "guide", "choose_path", "learn",
}


def apply_action(*, player_id: Optional[str], req_json: Any) -> ActionResponse:
    try:
        req = _action_adapter.validate_python(req_json)
    except Exception:
        return ActionResponse(ok=False, error="Invalid action payload.")

    # create_player does not require x-player-id
    if req.action == "create_player":
        result = create_player(req.args.name, getattr(req.args, "archetype", None))
        pid = (
            result.state["player"]["player_id"]
            if result.state and "player" in result.state
            else "unknown"
        )
        if pid != "unknown":
            log_action(
                player_id=pid,
                action=req.action,
                args=req.model_dump().get("args"),
                result=result.model_dump(),
            )
        return result

    if not player_id:
        return ActionResponse(ok=False, error="Missing player_id (x-player-id header).")

    player = get_player(player_id)
    if not player:
        return ActionResponse(ok=False, error="Unknown player_id.")

    # Presence: record that this player is active right now — but first note
    # when they were last here, so a returning player gets a recap.
    from ..db import touch_last_seen, get_world_state, set_world_state, get_last_seen_map
    from ..presence import now_ms
    now = now_ms()
    prev_seen = get_last_seen_map([player.player_id]).get(player.player_id, 0)
    touch_last_seen(player.player_id, now)

    recap_msgs: list[str] = []
    if prev_seen and (player.last_recap_at or 0) < prev_seen:
        from ..recap import recap_messages
        try:
            recap_msgs = recap_messages(player, prev_seen, now)
        except Exception as e:
            print(f"[RECAP] failed: {e}")
        if recap_msgs:
            player.last_recap_at = now
            from ..db import upsert_player as _persist_recap
            _persist_recap(player)

    # Track the world's threat level (highest player level) so respawns scale.
    try:
        if player.level > int(get_world_state("world_level") or 1):
            set_world_state("world_level", str(player.level))
    except (TypeError, ValueError):
        set_world_state("world_level", str(player.level))

    # Bring back any monsters whose respawn timer has elapsed.
    from .entities import respawn_due_monsters
    respawn_due_monsters()

    # Action points: passive reads are free; anything that changes the world
    # costs 1 AP (regenerating in real time — see app/action_points.py).
    from ..action_points import refill, spend, seconds_to_next_ap, ap_enabled, ap_max
    refill(player)
    if req.action not in PASSIVE_ACTIONS:
        if not spend(player, 1):
            wait = seconds_to_next_ap(player)
            return ActionResponse(
                ok=False,
                error=(
                    f"You're out of action points — your next one arrives in {wait}s. "
                    "The world keeps turning while you rest."
                ),
            )

    if req.action == "look":
        result = look(player)
    elif req.action == "move":
        result = move(player, req.args.to)
    elif req.action == "attack":
        result = attack(player, req.args.target)
    elif req.action == "fight":
        from .actions.fight import fight
        result = fight(player, req.args.target, req.args.stance)
    elif req.action == "stats":
        result = stats(player)
    elif req.action == "inventory":
        result = inventory(player)
    elif req.action == "use":
        result = use(player, req.args.item)
    elif req.action == "talk":
        result = talk(player, req.args.target)
    elif req.action == "buy":
        result = buy(player, req.args.item)
    elif req.action == "accept_quest":
        result = accept_quest(player, req.args.quest_id)
    elif req.action == "turn_in_quest":
        result = turn_in_quest(player, req.args.quest_id)
    elif req.action == "offer_trade":
        result = offer_trade(
            player,
            req.args.to_player,
            req.args.offer_items,
            req.args.request_items,
        )
    elif req.action == "accept_trade":
        result = accept_trade(player, req.args.trade_id)
    elif req.action == "list_trades":
        result = list_trades(player)
    elif req.action == "cancel_trade":
        result = cancel_trade(player, req.args.trade_id)
    elif req.action == "party_invite":
        result = party_invite(player, req.args.target_player)
    elif req.action == "accept_party_invite":
        result = accept_party_invite(player, req.args.invite_id)
    elif req.action == "leave_party":
        result = leave_party(player)
    elif req.action == "party_status":
        result = party_status(player)
    elif req.action == "reputation":
        result = reputation(player)
    elif req.action == "equip":
        result = equip(player, req.args.item)
    elif req.action == "unequip":
        result = unequip(player, req.args.slot)
    elif req.action == "sell":
        result = sell(player, req.args.item)
    elif req.action == "craft":
        result = craft(player, req.args.item)
    elif req.action == "gather":
        result = gather(player)
    elif req.action == "use_ability":
        result = use_ability(player, req.args.ability, req.args.target)
    elif req.action == "heal":
        result = heal(player)
    elif req.action == "map":
        result = world_map(player)
    elif req.action == "bestiary":
        result = bestiary(player)
    elif req.action == "journal":
        result = journal(player)
    elif req.action == "story":
        result = story_status(player)
    elif req.action == "begin_arc":
        result = begin_arc(player, req.args.arc_id)
    elif req.action == "choose":
        result = choose(player, req.args.choice, req.args.arc_id)
    elif req.action == "explore":
        from .actions.explore import explore
        result = explore(player)
    elif req.action == "dig":
        from .actions.dig import dig
        result = dig(player)
    elif req.action == "rest":
        from .actions.rest import rest
        result = rest(player)
    elif req.action == "recruit":
        from .actions.recruit import recruit
        result = recruit(player, req.args.target)
    elif req.action == "dismiss":
        from .actions.dismiss import dismiss
        result = dismiss(player)
    elif req.action == "companion":
        from .actions.companion_status import companion_status
        result = companion_status(player)
    elif req.action == "raid_status":
        from ..raids import raid_status
        result = raid_status(player)
    elif req.action == "raid_strike":
        from ..raids import strike_raid
        result = strike_raid(player)
    elif req.action == "stronghold":
        from ..stronghold import status as stronghold_status
        result = stronghold_status(player)
    elif req.action == "build_stronghold":
        from ..stronghold import build as stronghold_build
        result = stronghold_build(player)
    elif req.action == "stash":
        from ..stronghold import deposit
        result = deposit(player, req.args.item, req.args.qty)
    elif req.action == "unstash":
        from ..stronghold import withdraw
        result = withdraw(player, req.args.item, req.args.qty)
    elif req.action == "collect_tribute":
        from ..stronghold import collect
        result = collect(player)
    elif req.action == "guide":
        from ..guidance import guide
        result = guide(player)
    elif req.action == "choose_path":
        from .actions.choose_path import choose_path
        result = choose_path(player, req.args.archetype)
    elif req.action == "learn":
        from .actions.learn import learn
        result = learn(player, req.args.ability)
    elif req.action == "post_note":
        from .actions.post_note import post_note
        result = post_note(player, req.args.text)
    elif req.action == "post_bounty":
        from .actions.bounty import post_bounty
        result = post_bounty(player, req.args.target, req.args.coins)
    elif req.action == "bounties":
        from .actions.bounty import list_bounties
        result = list_bounties(player)
    elif req.action == "goals":
        from ..world_goals import goals_overview
        from .state_view import build_action_state
        result = ActionResponse(
            ok=True,
            messages=goals_overview(player),
            state=build_action_state(player, scene_dirty=False),
        )
    else:
        result = ActionResponse(ok=False, error="Unhandled action.")

    # Refresh collect/visit quest objectives from current state (kills are
    # progressed at the moment of the kill). Persist progress (even partial,
    # e.g. counting items you already had) and reflect it in the response.
    if result.ok and req.action not in PASSIVE_ACTIONS:
        from .quest_progress import refresh_quests
        from ..db import upsert_player as _upsert
        quest_msgs = refresh_quests(player)
        _upsert(player)
        if quest_msgs:
            result.messages.extend(quest_msgs)
        # Running low on AP is worth a heads-up (but not on every action).
        if ap_enabled() and player.action_points <= 5:
            result.messages.append(
                f"AP: {player.action_points}/{ap_max()} — they regenerate over time."
            )
        # Rebuild the state so the UI shows the refreshed quest progress now.
        if result.state is not None:
            from .state_view import build_action_state
            result.state = build_action_state(player, scene_dirty=bool(result.state.get("scene_dirty")))

    # Phase 8: Increment world turn on successful actions (except passive ones like look, stats, inventory)
    if result.ok and req.action not in PASSIVE_ACTIONS:
        new_turn = increment_world_turn()
        print(f"[TURN] New turn: {new_turn}, Action: {req.action}")

        # Evaluate world evolution rules periodically (every 5 turns)
        if new_turn % 5 == 0:
            print(f"[TURN] Turn {new_turn} is divisible by 5, evaluating world rules")
            from ..world_rules import evaluate_world_rules
            try:
                triggered_rules = evaluate_world_rules()
            except Exception as e:
                from ..db import log_world_event
                print(f"[TURN] World rules error: {e}")
                log_world_event(
                    event_type="world_rule_error",
                    location_id=None,
                    data={"error": str(e)}
                )
                triggered_rules = []
            # (World-change notices were debug-only and are intentionally not
            # surfaced to the player.)

    # A returning player's recap leads their first action's output.
    if recap_msgs and result.ok:
        result.messages = recap_msgs + result.messages

    log_action(
        player_id=player.player_id,
        action=req.action,
        args=req.model_dump().get("args"),
        result=result.model_dump(),
    )

    # Learn player action in Miriel (Phase 2: Learning System)
    if result.ok:
        from ..miriel_learning import learn_player_action
        try:
            learn_player_action(
                player=player,
                action=req.action,
                args=req.model_dump().get("args", {}),
                result=result.model_dump(),
                turn=get_world_turn()
            )
        except Exception as e:
            print(f"[MIRIEL] Learning failed: {e}")

    return result