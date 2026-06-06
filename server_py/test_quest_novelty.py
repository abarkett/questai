"""
Offline tests for quest novelty/dynamism mechanics (no live Miriel needed).

Covers:
  - valid-target snapshot (generated quests stay completable)
  - dynamic quest id: stable within an offer->accept cycle, rotates as the
    player finishes quests
  - cache key: stable per (player, quest_id_hint) so an offer survives to
    accept, but distinct across players (no collisions)
  - prompt: injects anti-repeat names, a variation seed, valid kill targets,
    and the pinned quest_id
  - get_or_generate_quest: template hit; dynamic gracefully None when Miriel off

Run from server_py/:  python3 test_quest_novelty.py
"""

import os
import tempfile

import app.db as db

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp.close()
db.DB_PATH = _tmp.name
db.init_db()

# Force Miriel disabled so generation degrades to None deterministically.
os.environ.pop("MIRIEL_API_KEY", None)

from app.types import Player  # noqa: E402
from app.types_quests import Quest, QuestObjective  # noqa: E402
from app.world_quests import get_valid_quest_targets  # noqa: E402
from app.miriel_quests import (  # noqa: E402
    _generate_cache_key,
    _build_quest_context,
    get_or_generate_quest,
)
from app.services.miriel_prompts import build_quest_generation_prompt  # noqa: E402
from app.engine.actions.talk import _dynamic_quest_id  # noqa: E402


def _quest(i: int) -> Quest:
    return Quest(
        quest_id=f"old_{i}",
        name=f"Old Quest {i}",
        description="an old task",
        objectives=[QuestObjective(type="kill", target="Rat", required=1)],
        rewards={"coin": 1},
    )


def mkplayer(pid="11111111-2222-3333-4444-555555555555", completed=0, archived=0) -> Player:
    return Player(
        player_id=pid,
        name="Hero",
        location="town_square",
        level=1,
        xp=0,
        hp=10,
        max_hp=10,
        completed_quests={f"c{i}": _quest(i) for i in range(completed)},
        archived_quests={f"a{i}": _quest(100 + i) for i in range(archived)},
    )


def main() -> None:
    # 1) Valid targets snapshot
    vt = get_valid_quest_targets()
    assert "Rat" in vt["monsters"], vt
    assert "healing_herb" in vt["items"] and "torch" in vt["items"], vt
    print("PASS  valid targets:", vt)

    # 2) Dynamic id: stable, then rotates after finishing a quest
    p = mkplayer()
    id1, id1b = _dynamic_quest_id(p, "warden"), _dynamic_quest_id(p, "warden")
    assert id1 == id1b, (id1, id1b)
    id2 = _dynamic_quest_id(mkplayer(archived=1), "warden")
    assert id2 != id1, (id1, id2)
    print(f"PASS  dynamic id stable + rotates: {id1} -> {id2}")

    # 3) Cache key: stable per (player, hint); distinct across players
    cA = _build_quest_context(mkplayer(pid="player-aaaa"))
    cB = _build_quest_context(mkplayer(pid="player-bbbb"))
    kA = _generate_cache_key("quest", cA, "dyn_warden_aaaa_0")
    kA2 = _generate_cache_key("quest", cA, "dyn_warden_aaaa_0")
    kB = _generate_cache_key("quest", cB, "dyn_warden_aaaa_0")
    assert kA == kA2, "same player+hint must be stable (offer == accept)"
    assert kA != kB, "different players must not collide"
    print("PASS  cache key stable per player, distinct across players")

    # 4) Prompt: anti-repeat + seed + valid target + pinned id
    p3 = mkplayer(completed=2, archived=1)  # novelty_seed should be 3
    ctx = _build_quest_context(p3)
    prompt = build_quest_generation_prompt(p3, ctx, quest_id_hint="dyn_warden_x_3", npc_id="warden")
    assert "Rat" in prompt
    assert "AVOID REPETITION" in prompt
    assert "Old Quest" in prompt, "seen quest names must be injected"
    assert "Variation token: 3" in prompt, "novelty seed must be 2 completed + 1 archived"
    assert "dyn_warden_x_3" in prompt, "quest_id hint must be pinned in schema"
    assert '"type": "kill"' in prompt
    print("PASS  prompt has anti-repeat, valid target, variation seed, pinned id")

    # 5) get_or_generate_quest: template hit; dynamic None when Miriel disabled
    tq, gen = get_or_generate_quest("rat_problem", mkplayer())
    assert tq is not None and gen is False, (tq, gen)
    dq, gen2 = get_or_generate_quest("dyn_warden_aaaa_0", mkplayer())
    assert dq is None and gen2 is False, (dq, gen2)
    print("PASS  template returns; dynamic gracefully None when Miriel disabled")

    print("\nALL QUEST NOVELTY TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_tmp.name)
