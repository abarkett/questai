"""
Offline tests for presence-aware parties: online/offline status, auto-pruning
of long-gone members, party disband, and party-invite expiry.

Run from server_py/:  python3 test_presence.py
"""

import os
import tempfile
import uuid

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.types import Player  # noqa: E402
from app.db import (  # noqa: E402
    upsert_player, create_party, add_party_member, get_player_party,
    create_party_invite, get_player_party_invites, touch_last_seen,
    get_last_seen_map, PARTY_INVITE_TTL_MS,
)
from app.presence import is_online, is_stale, now_ms, ONLINE_WINDOW_MS, STALE_PARTY_MS
from app.engine.actions.party_status import party_status
from app.engine.actions.accept_party_invite import accept_party_invite


def mkp(pid, name):
    p = Player(player_id=pid, name=name, location="town_square", level=1, xp=0, hp=10, max_hp=10)
    upsert_player(p)
    return p


def main() -> None:
    now = now_ms()

    # Presence helpers.
    assert is_online(now - 1000, now) and not is_online(now - ONLINE_WINDOW_MS - 1000, now)
    assert is_stale(now - STALE_PARTY_MS - 1000, now) and not is_stale(now - 1000, now)
    assert not is_stale(0, now)  # never-seen players are not pruned
    print("PASS  presence helpers: online / stale thresholds")

    # last_seen round-trips.
    mkp("a", "Active")
    touch_last_seen("a", now)
    assert get_last_seen_map(["a"])["a"] == now
    print("PASS  last_seen recorded and queried")

    # A party with a long-gone member: status greys them and prunes the stale one.
    leader = mkp("L", "Leader")
    active = mkp("A2", "Buddy")
    gone = mkp("G", "GhostAlt")
    pid = str(uuid.uuid4())
    create_party(pid, "L", "Test Party")
    add_party_member(pid, "A2")
    add_party_member(pid, "G")
    touch_last_seen("L", now)
    touch_last_seen("A2", now)
    touch_last_seen("G", now - STALE_PARTY_MS - 5000)  # months-old alt

    r = party_status(leader)
    text = " ".join(r.messages)
    assert "online" in text, text
    assert "GhostAlt" not in " ".join(m for m in r.messages if "online" in m or "offline" in m)
    assert "GhostAlt" in text  # mentioned as dropped
    assert "G" not in get_player_party("L")["members"], "stale member pruned"
    assert set(get_player_party("L")["members"]) == {"L", "A2"}
    print("PASS  party_status greys offline + prunes stale members")

    # Party collapses to one -> disband.
    solo = mkp("S", "Solo")
    leftover = mkp("X", "OldFriend")
    pid2 = str(uuid.uuid4())
    create_party(pid2, "S", "Duo")
    add_party_member(pid2, "X")
    touch_last_seen("S", now)
    touch_last_seen("X", now - STALE_PARTY_MS - 5000)
    r = party_status(solo)
    assert "disbanded" in " ".join(r.messages).lower(), r.messages
    assert get_player_party("S") is None
    print("PASS  party disbands when only one active member remains")

    # Invite expiry: stale invites are filtered/rejected, fresh ones kept.
    inviter = mkp("I", "Inviter")
    invitee = mkp("J", "Invitee")
    pid3 = str(uuid.uuid4())
    create_party(pid3, "I", "Guild")
    old_id, new_id = str(uuid.uuid4()), str(uuid.uuid4())
    create_party_invite(old_id, pid3, "I", "J")
    create_party_invite(new_id, pid3, "I", "J")
    # Backdate the old invite beyond the TTL.
    conn = db.get_conn()
    conn.execute("UPDATE party_invites SET created_at = ? WHERE invite_id = ?",
                 (now - PARTY_INVITE_TTL_MS - 5000, old_id))
    conn.commit(); conn.close()

    fresh = get_player_party_invites("J")
    assert [i["invite_id"] for i in fresh] == [new_id], fresh
    assert accept_party_invite(invitee, old_id).ok is False  # expired
    print("PASS  party invites expire (stale rejected, fresh kept)")

    print("\nALL PRESENCE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
