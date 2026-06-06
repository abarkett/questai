from __future__ import annotations

import json
from typing import Optional

from ...types import Player, ActionResponse
from ...story_content import get_arc, all_arc_ids, StoryArcDef, ArcReward
from ...items import get_item
from ...progression import apply_xp
from ...db import (
    get_player_arc,
    get_player_arcs,
    start_player_arc,
    update_player_arc,
    upsert_player,
)
from ..state_view import build_action_state


def _choices(row: dict) -> list[dict]:
    try:
        return json.loads(row.get("choices_json") or "[]")
    except Exception:
        return []


def _chapter_prompt(arc: StoryArcDef, chapter_num: int) -> list[str]:
    """Narration + choice prompt for a chapter."""
    ch = arc.chapter(chapter_num)
    if not ch:
        return []
    lines = [f"[{arc.title} — Ch. {ch.chapter}: {ch.title}]", ch.narration]
    if ch.choices:
        lines.append("Choose:")
        for c in ch.choices:
            lines.append(f"  - {c.key}: {c.label}")
        lines.append(f"Use `choose {arc.arc_id} <key>`.")
    return lines


def _reward_for(arc: StoryArcDef, choices: list[dict]) -> ArcReward:
    """Branch-aware reward: first recorded choice that has an override wins."""
    for entry in choices:
        key = entry.get("choice")
        if key in arc.branch_rewards:
            return arc.branch_rewards[key]
    return arc.default_reward


def _grant_reward(player: Player, reward: ArcReward) -> list[str]:
    messages: list[str] = []
    for item_id, qty in reward.items.items():
        player.inventory[item_id] = player.inventory.get(item_id, 0) + qty
        item = get_item(item_id)
        messages.append(f"Reward: {qty}x {item.name if item else item_id}")
    if reward.xp:
        messages.extend(apply_xp(player, reward.xp))
    return messages


def arc_talk_lines(player: Player) -> list[str]:
    """What the recurring arc-giver NPC says, based on the player's arc state."""
    arcs = {a["arc_id"]: a for a in get_player_arcs(player.player_id)}

    # Any active arc currently awaiting a choice?
    for arc_id, row in arcs.items():
        if row.get("status") != "active":
            continue
        arc = get_arc(arc_id)
        if not arc:
            continue
        ch = arc.chapter(row.get("current_chapter", 1))
        if ch and ch.choices:
            return [f'"Our tale is unfinished. {ch.title} awaits your choice."'] + _chapter_prompt(arc, ch.chapter)

    # Otherwise, offer any arc not yet begun.
    unstarted = [aid for aid in all_arc_ids() if aid not in arcs]
    if unstarted:
        lines = ['"I carry stories that need a hero. Will you hear one?"']
        for aid in unstarted:
            arc = get_arc(aid)
            if arc:
                lines.append(f"  - {arc.arc_id}: {arc.title} — {arc.description}")
        lines.append("Use `begin <arc_id>`.")
        return lines

    return ['"You have walked every road I know. Go well, friend."']


def story_status(player: Player) -> ActionResponse:
    arcs = {a["arc_id"]: a for a in get_player_arcs(player.player_id)}
    messages = ["Story Arcs:"]

    active = [(aid, r) for aid, r in arcs.items() if r.get("status") == "active"]
    completed = [aid for aid, r in arcs.items() if r.get("status") == "completed"]
    unstarted = [aid for aid in all_arc_ids() if aid not in arcs]

    if active:
        messages.append("In progress:")
        for aid, row in active:
            arc = get_arc(aid)
            if not arc:
                continue
            cur = row.get("current_chapter", 1)
            messages.append(f"  - {arc.title} (Ch. {cur}/{arc.total_chapters})")
            ch = arc.chapter(cur)
            if ch and ch.choices:
                keys = ", ".join(c.key for c in ch.choices)
                messages.append(f"      awaiting choice: {keys} (use `choose {aid} <key>`)")

    if unstarted:
        messages.append("Available (talk to the Wanderer or `begin <arc_id>`):")
        for aid in unstarted:
            arc = get_arc(aid)
            if arc:
                messages.append(f"  - {aid}: {arc.title}")

    if completed:
        messages.append("Completed:")
        for aid in completed:
            arc = get_arc(aid)
            if arc:
                messages.append(f"  - {arc.title}")

    if not active and not unstarted and not completed:
        messages.append("  (none)")

    return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=False))


def begin_arc(player: Player, arc_id: str) -> ActionResponse:
    arc_id = arc_id.strip().lower()
    arc = get_arc(arc_id)
    if not arc:
        return ActionResponse(ok=False, error="There is no such tale.")

    if get_player_arc(player.player_id, arc_id):
        return ActionResponse(ok=False, error="You have already begun that tale.")

    start_player_arc(player.player_id, arc_id)
    messages = ["You begin a new story arc."] + _chapter_prompt(arc, 1)
    return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=False))


def choose(player: Player, choice_key: str, arc_id: Optional[str] = None) -> ActionResponse:
    choice_key = choice_key.strip().lower()
    arcs = {a["arc_id"]: a for a in get_player_arcs(player.player_id)}

    # Active arcs whose current chapter is awaiting a choice.
    awaiting = []
    for aid, row in arcs.items():
        if row.get("status") != "active":
            continue
        arc = get_arc(aid)
        if not arc:
            continue
        ch = arc.chapter(row.get("current_chapter", 1))
        if ch and ch.choices:
            awaiting.append(aid)

    if arc_id:
        arc_id = arc_id.strip().lower()
        if arc_id not in awaiting:
            return ActionResponse(ok=False, error="You have no pending choice in that tale.")
        target = arc_id
    elif len(awaiting) == 1:
        target = awaiting[0]
    elif not awaiting:
        return ActionResponse(ok=False, error="You have no story choice to make right now.")
    else:
        return ActionResponse(
            ok=False,
            error="Specify which tale: " + ", ".join(f"choose {a} <key>" for a in awaiting),
        )

    arc = get_arc(target)
    row = arcs[target]
    cur = row.get("current_chapter", 1)
    chapter = arc.chapter(cur)
    selected = next((c for c in chapter.choices if c.key == choice_key), None)
    if not selected:
        valid = ", ".join(c.key for c in chapter.choices)
        return ActionResponse(ok=False, error=f"Not a valid choice. Options: {valid}.")

    choices = _choices(row)
    choices.append({"chapter": cur, "choice": choice_key})

    messages = [selected.result]
    next_num = cur + 1
    next_chapter = arc.chapter(next_num)

    if next_chapter and not next_chapter.choices:
        # Advancing into the epilogue completes the arc.
        update_player_arc(player.player_id, target, current_chapter=next_num, status="completed", choices=choices)
        messages += _chapter_prompt(arc, next_num)
        reward = _reward_for(arc, choices)
        messages += _grant_reward(player, reward)
        messages.append(f"You have completed '{arc.title}'.")
        upsert_player(player)
    else:
        update_player_arc(player.player_id, target, current_chapter=next_num, status="active", choices=choices)
        messages += _chapter_prompt(arc, next_num)

    return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=False))
