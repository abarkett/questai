"""
Tests for the SMS gateway and plain-text renderer: the whole game must be
playable as short plain text from a bare phone number.

Run from server_py/:  python3 test_sms.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from fastapi.testclient import TestClient  # noqa: E402

# Miriel is required (no fallback): stub it for the offline suite.
from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402

get_miriel_client().enabled = True
install_test_responder(lambda q: "Lantern light spills over the cobbles.")

from app.main import app  # noqa: E402
from app.render_text import render_plain, MAX_SMS_CHARS  # noqa: E402
from app.types import ActionResponse, Player  # noqa: E402

client = TestClient(app)
PHONE = "+15555550100"


def send(text: str, phone: str = PHONE) -> str:
    r = client.post("/sms", json={"from": phone, "text": text})
    assert r.status_code == 200, r.text
    return r.text


def main() -> None:
    with client:
        # Unknown senders are onboarded.
        reply = send("look")
        assert "create <name>" in reply, reply
        print("PASS  unknown senders are told how to start")

        # Creating binds the phone to the new hero.
        reply = send("create Mara")
        assert "Welcome, Mara" in reply, reply
        reply = send("create Again")
        assert "already have a hero" in reply, reply
        print("PASS  create binds the phone to one hero")

        # The full command grammar works over SMS, and replies stay short.
        reply = send("look")
        assert "Town Square" in reply, reply
        assert len(reply) <= MAX_SMS_CHARS, len(reply)
        assert "HP " in reply, "status suffix present"

        reply = send("go north")
        assert "North Road" in reply, reply

        reply = send("stats")
        assert "Mara" in reply and "AP" in reply, reply
        print("PASS  play over SMS: look, move, stats all under the length cap")

        # Parse errors come back as friendly one-liners.
        reply = send("dance wildly")
        assert "Unknown command" in reply, reply
        print("PASS  unknown commands answer gently")

    # Renderer truncates long content but keeps the status readable.
    p = Player(player_id="x", name="X", location="town_square",
               level=1, xp=0, hp=9, max_hp=10)
    long_result = ActionResponse(ok=True, messages=["word " * 300])
    text = render_plain(long_result, player=p)
    assert len(text) <= MAX_SMS_CHARS
    assert text.endswith("]") and "HP 9/10" in text
    err = render_plain(ActionResponse(ok=False, error="Nope."), player=p)
    assert err == "Nope."
    print("PASS  renderer truncates to budget and keeps the status line")

    print("\nALL SMS TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
