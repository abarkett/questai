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
    if verb in ("stats", "hp", "me", "status", "abilities", "skills", "ap"):
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

    # ---- EQUIP / UNEQUIP ----
    if verb in ("equip", "wield", "wear"):
        if not rest:
            raise ParseError("Equip what?")
        return {"action": "equip", "args": {"item": " ".join(rest)}}

    if verb in ("unequip", "remove"):
        if not rest:
            raise ParseError("Unequip which slot? (weapon or armor)")
        return {"action": "unequip", "args": {"slot": " ".join(rest)}}

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

    # ---- FIGHT (whole encounter, with optional stance) ----
    if verb in ("fight", "f"):
        stance = "standard"
        if rest and rest[0].lower() in ("bold", "boldly"):
            stance = "bold"
            rest = rest[1:]
        elif rest and rest[0].lower() in ("cautious", "cautiously", "careful", "carefully"):
            stance = "cautious"
            rest = rest[1:]
        if not rest:
            raise ParseError("Fight what? (fight [bold|cautious] <target>)")
        return {
            "action": "fight",
            "args": {"target": " ".join(rest), "stance": stance},
        }

    # ---- ABILITIES ----
    if verb in ("ability", "cast"):
        if not rest:
            raise ParseError("Use which ability?")
        return {
            "action": "use_ability",
            "args": {"ability": rest[0], "target": " ".join(rest[1:]) or None},
        }

    _ability_aliases = {
        "power_strike": "power_strike",
        "powerstrike": "power_strike",
        "strike": "power_strike",
        "second_wind": "second_wind",
        "secondwind": "second_wind",
        "rend": "rend",
        "cleave": "cleave",
        "rupture": "rupture",
    }
    if verb in _ability_aliases:
        return {
            "action": "use_ability",
            "args": {"ability": _ability_aliases[verb], "target": " ".join(rest) or None},
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

    # ---- SELL ----
    if verb == "sell" and rest:
        return {"action": "sell", "args": {"item": " ".join(rest)}}

    # ---- CRAFT ----
    if verb in ("craft", "make") and rest:
        return {"action": "craft", "args": {"item": " ".join(rest)}}

    # ---- GATHER ----
    if verb in ("gather", "forage", "mine", "harvest"):
        return {"action": "gather"}
    
    if verb == "accept" and rest:
        return {
            "action": "accept_quest",
            "args": {"quest_id": rest[0]}
        }
    
    # ---- OFFER TRADE ----
    if verb == "offer" and len(rest) >= 1:
        # Format: offer <player_name> item:qty [item:qty ...] for item:qty [item:qty ...]
        # Example: offer Alice sword:2 for gold:10
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

            # Parse items: "sword:2 shield:3" -> {"sword": 2, "shield": 3}
            def parse_items(text: str) -> dict[str, int]:
                items = {}
                if not text:
                    return items
                tokens = text.split()
                for token in tokens:
                    if ":" in token:
                        # Format: "item:qty"
                        parts = token.split(":", 1)
                        item_name = parts[0]
                        qty_str = parts[1]
                        try:
                            qty = int(qty_str)
                        except ValueError:
                            raise ParseError(f"Invalid quantity in '{token}': {qty_str}")

                        if qty <= 0:
                            raise ParseError(f"Quantity must be positive in '{token}'")

                        items[item_name] = qty
                    else:
                        # No colon means quantity 1
                        items[token] = 1
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
            raise ParseError("Use format: offer <player> item:qty [item:qty ...] for item:qty [item:qty ...]")
    
    # ---- ACCEPT TRADE ----
    if verb == "accept_trade" and rest:
        return {
            "action": "accept_trade",
            "args": {"trade_id": rest[0]}
        }

    # ---- LIST TRADES ----
    if verb in ("trades", "list_trades"):
        return {"action": "list_trades"}

    # ---- CANCEL TRADE ----
    if verb == "cancel_trade" and rest:
        return {
            "action": "cancel_trade",
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
    
    # ---- EXPLORE (open a frontier) ----
    if verb in ("explore", "search", "chart"):
        return {"action": "explore"}

    # ---- DIG (claim a treasure-map cache) ----
    if verb in ("dig", "excavate", "unearth"):
        return {"action": "dig"}

    # ---- NOTES (noticeboard) ----
    if verb in ("note", "write", "scratch"):
        if not rest:
            raise ParseError("Write what? (note <text>)")
        return {"action": "post_note", "args": {"text": " ".join(rest)}}

    # ---- BOUNTIES ----
    if verb in ("bounties", "board"):
        return {"action": "bounties"}

    if verb == "bounty":
        # bounty <coins> <monster name...>
        if len(rest) >= 2 and rest[0].isdigit():
            return {
                "action": "post_bounty",
                "args": {"coins": int(rest[0]), "target": " ".join(rest[1:])},
            }
        if not rest:
            return {"action": "bounties"}
        raise ParseError("Use: bounty <coins> <monster> (e.g. bounty 10 Wolf)")

    # ---- COMMUNITY GOALS ----
    if verb in ("goals", "goal", "season", "events"):
        return {"action": "goals"}

    # ---- CO-OP RAID BOSS ----
    if verb in ("raid", "worldboss"):
        if rest and rest[0].lower() in ("strike", "hit", "attack", "assault", "assail", "fight"):
            return {"action": "raid_strike"}
        return {"action": "raid_status"}

    if verb in ("assail",):
        return {"action": "raid_strike"}

    # ---- COMPANIONS ----
    if verb in ("recruit", "hire", "enlist") and rest:
        return {"action": "recruit", "args": {"target": " ".join(rest)}}

    if verb in ("dismiss", "farewell"):
        return {"action": "dismiss"}

    if verb in ("companion", "ally", "comp"):
        return {"action": "companion"}

    # ---- GUIDANCE (what now?) ----
    if verb in ("next", "guide", "hint", "todo", "advice"):
        return {"action": "guide"}

    # ---- STRONGHOLD ----
    if verb in ("stronghold", "home", "base", "holding"):
        return {"action": "stronghold"}

    if verb in ("build", "upgrade"):
        return {"action": "build_stronghold"}

    if verb in ("collect", "tribute"):
        return {"action": "collect_tribute"}

    if verb in ("stash", "store", "deposit", "unstash", "withdraw", "retrieve"):
        if not rest:
            raise ParseError(f"{verb.capitalize()} what? (e.g. {verb} dragon_heart 2)")
        # Optional trailing quantity: "stash dragon heart 2".
        qty = None
        if len(rest) > 1 and rest[-1].isdigit():
            qty = int(rest[-1])
            rest = rest[:-1]
        action = "unstash" if verb in ("unstash", "withdraw", "retrieve") else "stash"
        return {"action": action, "args": {"item": " ".join(rest), "qty": qty}}

    # ---- REPUTATION ----
    if verb in ("reputation", "rep", "factions"):
        return {"action": "reputation"}

    # ---- HEAL (temple) ----
    if verb in ("heal", "pray", "worship"):
        return {"action": "heal"}

    # ---- REST (free recovery anywhere safe) ----
    if verb in ("rest", "camp", "sleep", "breathe"):
        return {"action": "rest"}

    # ---- MAP ----
    if verb in ("map", "m"):
        return {"action": "map"}

    # ---- BESTIARY ----
    if verb in ("bestiary", "monsters", "codex"):
        return {"action": "bestiary"}

    # ---- JOURNAL (quests) ----
    if verb in ("journal", "quests", "quest", "log"):
        return {"action": "journal"}

    # ---- STORY ARCS ----
    if verb in ("story", "arcs", "saga", "tales"):
        return {"action": "story"}

    if verb in ("begin", "embark") and rest:
        return {"action": "begin_arc", "args": {"arc_id": rest[0]}}

    if verb == "choose" and rest:
        from ..story_content import STORY_ARCS
        if len(rest) >= 2 and rest[0].lower() in STORY_ARCS:
            return {"action": "choose", "args": {"arc_id": rest[0].lower(), "choice": rest[1]}}
        return {"action": "choose", "args": {"choice": rest[0]}}

    # ---- FALLBACK ----
    raise ParseError(f"Unknown command: {text}")
