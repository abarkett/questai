from __future__ import annotations

from typing import Any, Dict


class ParseError(Exception):
    pass


def parse_command(text: str) -> Dict[str, Any]:
    """
    Convert a human text command into an ActionRequest dict.

    Examples:
      "look"           -> {"action": "look"}
      "l"              -> {"action": "look"}
      "go north"       -> {"action": "move", "args": {"to": "north"}}
      "move tavern"    -> {"action": "move", "args": {"to": "tavern"}}
      "create Arlen"   -> {"action": "create_player", "args": {"name": "Arlen"}}
    """
    if not text or not text.strip():
        raise ParseError("Empty command.")

    tokens = text.strip().split()
    verb = tokens[0].lower()
    rest = tokens[1:]

    # ---- LOOK ----
    if verb in ("look", "l"):
        return {"action": "look"}
    
    # ---- STATS ----
    if verb in ("stats", "hp", "me", "status"):
        return {"action": "stats"}

    # ---- MOVE ----
    if verb in ("go", "move", "walk"):
        if not rest:
            raise ParseError("Go where?")
        return {
            "action": "move",
            "args": {"to": " ".join(rest)}
        }
    
    # ---- INVENTORY ----
    if verb in ("inventory", "inv", "i"):
        return {"action": "inventory"}
    
    # ---- USE ITEM ----
    if verb in ("use", "eat", "drink"):
        return {"action": "use", "args": {"item": " ".join(rest)}}

    # ---- CREATE PLAYER ----
    if verb in ("create", "new"):
        if not rest:
            raise ParseError("Create who?")
        return {
            "action": "create_player",
            "args": {"name": " ".join(rest)}
        }

    # ---- ATTACK ----
    if verb in ("attack", "hit", "kill"):
        if not rest:
            raise ParseError("Attack what?")
        return {
            "action": "attack",
            "args": {"target": " ".join(rest)}
        }

    # ---- TALK ----
    if verb == "talk" and rest:
        return {
            "action": "talk",
            "args": {
                "target": " ".join(rest)
            }
        }

    # ---- BUY ----
    if verb == "buy" and rest:
        return {
            "action": "buy",
            "args": {
                "item": " ".join(rest)
            }
        }
    
    if verb == "accept" and rest:
        return {
            "action": "accept_quest",
            "args": {"quest_id": rest[0]}
        }

    # ---- FALLBACK ----
    raise ParseError(f"Unknown command: {text}")
