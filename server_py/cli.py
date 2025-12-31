import requests

SERVER = "http://localhost:8787"
PLAYER_ID = None

print("QuestAI CLI")
print("Commands: create <name>, look, go <dir>, attack <target>, stats, inventory, use <item>")
print("Ctrl+C to exit\n")

try:
    while True:
        text = input("> ").strip()
        if not text:
            continue

        r = requests.post(
            f"{SERVER}/command",
            json={"text": text},
            headers=({"x-player-id": PLAYER_ID} if PLAYER_ID else {}),
        )

        try:
            resp = r.json()
        except Exception:
            print("[error] Server returned non-JSON response")
            print(r.status_code, r.text)
            continue

        # ---- capture player_id if returned ----
        state = resp.get("state")
        player = None
        if isinstance(state, dict):
            player = state.get("player")
            if isinstance(player, dict) and player.get("player_id"):
                PLAYER_ID = player["player_id"]

        # ---- print messages ----
        for m in resp.get("messages", []) or []:
            print(m)

        # ---- show stats after every command (if available) ----
        if isinstance(player, dict):
            hp = player.get("hp")
            max_hp = player.get("max_hp")
            xp = player.get("xp")
            if hp is not None and max_hp is not None and xp is not None:
                print(f"(HP: {hp}/{max_hp} | XP: {xp})")

except KeyboardInterrupt:
    print("\nGoodbye.")