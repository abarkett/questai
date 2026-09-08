"""
Test the background cache warmer: it populates Miriel description caches for the
current room and neighbors, and never raises (best-effort), even when Miriel is
down.

Run from server_py/:  python3 test_prefetch.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402
seed_world_monsters()

from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_world_turn  # noqa: E402
from app.world import get_location  # noqa: E402
from app.engine.entities import get_entities_at  # noqa: E402
from app.engine.state_view import effective_description  # noqa: E402
from app.engine.prefetch import warm_location_caches  # noqa: E402


def desc_cache_key(loc_id, turn):
    # Use the ONE shared key derivation (descriptions.cache_key_for) rather
    # than mirroring the formula here — a mirror drifts (and did, when the
    # base text became part of the key). The warmer describes each room with
    # effective_description() as the base, so match that exactly.
    from app.descriptions import cache_key_for
    loc = get_location(loc_id)
    return cache_key_for(loc, get_entities_at(loc_id), turn, effective_description(loc))


def main() -> None:
    p = Player(player_id="p", name="P", location="town_square", level=3, xp=0, hp=20, max_hp=20)
    upsert_player(p)

    # Miriel up (stubbed): warming caches the current room + neighbors.
    install_test_responder(lambda q: "An AI-authored vista.")
    res = warm_location_caches("p")
    assert res["ok"] and res["warmed"] >= 1, res
    # town_square has several exits -> current + neighbors (+ NPC dialogue) warmed.
    assert res["warmed"] >= 1 + len(get_location("town_square").exits), res

    turn = get_world_turn()
    cached = db.get_cached_miriel_content(desc_cache_key("town_square", turn))
    assert cached == "An AI-authored vista.", cached
    # a neighbor too
    nbr = get_location("town_square").exits[0].to
    assert db.get_cached_miriel_content(desc_cache_key(nbr, turn)) is not None
    print(f"PASS  warmer populated {res['warmed']} description caches")

    # Warming a quest-giver room pre-generates and caches its quest-offer dialogue.
    import hashlib
    from app.engine.entities import get_entities_at as _ents
    from app.engine.npc_offers import next_offer
    warden = next(e for e in _ents("town_square") if e.get("role") == "quest_giver")
    offer = next_offer(p, warden)
    assert offer is not None and offer[0].quest_id in warden["quests"], offer
    qkey = "qoffer_" + hashlib.sha256(f"p|{warden['id']}|{offer[0].name}".encode()).hexdigest()[:16]
    assert db.get_cached_miriel_content(qkey) is not None, "quest-offer dialogue should be warmed"
    print(f"PASS  quest-giver dialogue pre-generated ({offer[0].name})")

    # Warming a monster room pre-generates the 'cleared' description too.
    pf = Player(player_id="f", name="F", location="forest", level=3, xp=0, hp=20, max_hp=20)
    upsert_player(pf)
    warm_location_caches("f")
    # forest currently HAS rats, so the warmed key is the 'cleared' (no-monster)
    # one: the warmer describes the room with its non-monster entities and the
    # cleared_description as the base. Derive that key the same shared way.
    from app.descriptions import cache_key_for
    floc = get_location("forest")
    cleared_ents = [e for e in get_entities_at("forest") if e.get("type") != "monster"]
    cleared_key = cache_key_for(floc, cleared_ents, get_world_turn(),
                                floc.cleared_description or floc.description)
    assert db.get_cached_miriel_content(cleared_key) is not None, "cleared-room description should be warmed"
    print("PASS  cleared-room description pre-generated")

    # Best-effort: with Miriel down it must NOT raise (warmer swallows errors).
    install_test_responder(None)
    get_miriel_client().enabled = False
    res2 = warm_location_caches("p")
    assert res2["ok"] and res2["warmed"] == 0, res2
    print("PASS  warmer is best-effort (no crash when Miriel is down)")

    # Unknown player -> graceful.
    assert warm_location_caches("nope")["ok"] is False
    install_test_responder(None)
    print("PASS  unknown player handled")

    print("\nALL PREFETCH TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
