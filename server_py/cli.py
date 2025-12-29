import requests

SERVER = "http://localhost:8787"
PLAYER_ID = None

while True:
    text = input("> ").strip()
    if not text:
        continue

    resp = requests.post(
        f"{SERVER}/command",
        json={"text": text},
        headers=({"x-player-id": PLAYER_ID} if PLAYER_ID else {}),
    ).json()

    if resp.get("state", {}).get("player", {}).get("player_id"):
        PLAYER_ID = resp["state"]["player"]["player_id"]

    for m in resp.get("messages", []):
        print(m)