"""
Data models for story arcs - multi-quest narrative storylines.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class StoryArcChapter(BaseModel):
    """A single chapter in a story arc."""
    chapter_num: int
    title: str
    quest_ids: list[str]
    branching_choices: list[str] = []


class StoryArc(BaseModel):
    """A multi-quest storyline with branching narratives."""
    arc_id: str
    title: str
    description: str
    arc_type: str  # 'personal', 'faction', 'world'
    total_chapters: int
    current_chapter: int = 1
    chapters: list[StoryArcChapter]
    faction_alignment: Optional[str] = None
    metadata: dict = {}
    status: str = "active"  # 'active', 'paused', 'completed'
