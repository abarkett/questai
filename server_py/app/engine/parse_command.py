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
    
    # ---- OFFER TRADE ----
    if verb == "offer" and len(rest) >= 1:
        # Format: offer <player_name> <offer_items> for <request_items>
        # Example: offer Alice 2x sword for 10x gold
        # Simple parsing: find "for" keyword
        text_parts = " ".join(rest)
        if " for " in text_parts:
            before_for, after_for = text_parts.split(" for ", 1)
            parts = before_for.split()
            if not parts:
                raise ParseError("Specify player to trade with.")
            
            to_player = parts[0]
            offer_text = " ".join(parts[1:]) if len(parts) > 1 else ""
            request_text = after_for.strip()
            
            # Parse items: "2x sword 3x shield" -> {"sword": 2, "shield": 3}
            def parse_items(text: str) -> dict[str, int]:
                items = {}
                if not text:
                    return items
                tokens = text.split()
                i = 0
                while i < len(tokens):
                    token = tokens[i]
                    if "x" in token:
                        # Format: "2x"
                        qty_str = token.split("x")[0]
                        try:
                            qty = int(qty_str)
                        except ValueError:
                            raise ParseError(f"Invalid quantity: {qty_str}")
                        
                        if qty <= 0:
                            raise ParseError(f"Invalid quantity: {qty_str}")
                        
                        if i + 1 < len(tokens):
                            item_name = tokens[i + 1]
                            items[item_name] = qty
                            i += 2
                        else:
                            i += 1
                    else:
                        # Assume quantity 1
                        items[token] = 1
                        i += 1
                return items
            
            offer_items = parse_items(offer_text)
            request_items = parse_items(request_text)
            
            return {
                "action": "offer_trade",
                "args": {
                    "to_player": to_player,
                    "offer_items": offer_items,
                    "request_items": request_items,
                }
            }
        else:
            raise ParseError("Use format: offer <player> <items> for <items>")
    
    # ---- ACCEPT TRADE ----
    if verb == "accept_trade" and rest:
        return {
            "action": "accept_trade",
            "args": {"trade_id": rest[0]}
        }
    
    # ---- PARTY COMMANDS ----
    if verb == "party":
        if not rest:
            return {"action": "party_status"}
        
        subcommand = rest[0].lower()
        
        if subcommand == "invite" and len(rest) >= 2:
            return {
                "action": "party_invite",
                "args": {"target_player": " ".join(rest[1:])}
            }
        
        if subcommand == "leave":
            return {"action": "leave_party"}
        
        if subcommand in ("status", "info"):
            return {"action": "party_status"}
        
        raise ParseError("Party commands: party invite <player>, party leave, party status")
    
    if verb == "accept_party_invite" and rest:
        return {
            "action": "accept_party_invite",
            "args": {"invite_id": rest[0]}
        }
    
    # ---- REPUTATION ----
    if verb in ("reputation", "rep", "factions"):
        return {"action": "reputation"}

    # ---- FALLBACK ----
    raise ParseError(f"Unknown command: {text}")
