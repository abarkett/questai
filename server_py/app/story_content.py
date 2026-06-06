"""
Authored, branching story arcs and the recurring NPC who tells them.

Arcs are plain data: a list of chapters, each with narration and optional
branching choices. A chapter with choices waits for the player to `choose`;
a chapter with no choices is the epilogue and completing into it finishes the
arc. Rewards can depend on the branch the player took.

Adding an arc is a data-only change here.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel


class ArcChoice(BaseModel):
    key: str        # short token the player types, e.g. "mercy"
    label: str      # human description shown in the prompt
    result: str     # narration shown when this branch is chosen


class ArcTask(BaseModel):
    """A gameplay objective that must be completed before a chapter's choices unlock."""
    type: str         # "kill" | "collect" | "visit"
    target: str
    required: int = 1
    title: str
    description: str


class ArcChapter(BaseModel):
    chapter: int
    title: str
    narration: str
    task: Optional[ArcTask] = None  # gameplay gate before choices unlock
    choices: List[ArcChoice] = []   # empty => epilogue (completes the arc)


class ArcReward(BaseModel):
    items: Dict[str, int] = {}
    xp: int = 0


class StoryArcDef(BaseModel):
    arc_id: str
    title: str
    description: str
    arc_type: str                       # 'personal' | 'world'
    chapters: List[ArcChapter]
    default_reward: ArcReward = ArcReward()
    # Reward overrides keyed by a choice key the player took during the arc.
    branch_rewards: Dict[str, ArcReward] = {}

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    def chapter(self, num: int) -> Optional[ArcChapter]:
        for ch in self.chapters:
            if ch.chapter == num:
                return ch
        return None


STORY_ARCS: Dict[str, StoryArcDef] = {
    "wanderers_pact": StoryArcDef(
        arc_id="wanderers_pact",
        title="The Wanderer's Pact",
        description="A hooded stranger seeks help recovering a captured forest sprite.",
        arc_type="personal",
        chapters=[
            ArcChapter(
                chapter=1,
                title="A Stranger's Plea",
                narration=(
                    "The Wanderer lowers her hood. 'A sprite of the old wood was taken. "
                    "I cannot reach the one who holds it — but you can. Will you help?'"
                ),
                choices=[
                    ArcChoice(key="agree", label="Agree to help freely",
                              result="You clasp her hand. 'Then we are bound,' she says softly."),
                    ArcChoice(key="bargain", label="Demand payment first",
                              result="'Mercenary,' she smirks, 'but fair. You shall be paid.'"),
                ],
            ),
            ArcChapter(
                chapter=2,
                title="The Captor's Den",
                narration=(
                    "'The captor keeps goblin guards in the deep wood,' the Wanderer says. "
                    "'Cut through them to reach the den.'"
                ),
                task=ArcTask(
                    type="kill", target="Goblin", required=1,
                    title="Hunt the captor's guard",
                    description="Slay the Goblin guarding the path in the Deep Forest.",
                ),
                choices=[
                    ArcChoice(key="mercy", label="Spare the captor",
                              result="You lower your blade. He flees weeping, and the sprite glows warm with gratitude."),
                    ArcChoice(key="wrath", label="Strike the captor down",
                              result="Your blade falls. The sprite is freed, though its light dims at the sight."),
                ],
            ),
            ArcChapter(
                chapter=3,
                title="The Pact Fulfilled",
                narration=(
                    "The Wanderer receives the freed sprite. 'You kept your word,' she says. "
                    "'Few do.' She presses a reward into your hands and vanishes into the trees."
                ),
                choices=[],  # epilogue
            ),
        ],
        default_reward=ArcReward(items={"coin": 50}, xp=80),
        branch_rewards={
            "mercy": ArcReward(items={"greater_healing_potion": 2, "coin": 30}, xp=120),
            "wrath": ArcReward(items={"knight_blade": 1}, xp=120),
        },
    ),
    "embers_of_the_deep": StoryArcDef(
        arc_id="embers_of_the_deep",
        title="Embers of the Deep",
        description="Something ancient stirs beneath the cavern, and the deep grows hot.",
        arc_type="world",
        chapters=[
            ArcChapter(
                chapter=1,
                title="Whispers of Fire",
                narration=(
                    "The Wanderer studies a glowing ember. 'The deep is waking. "
                    "Go down to the Echoing Cavern and see for yourself — then decide what to do.'"
                ),
                task=ArcTask(
                    type="visit", target="cavern", required=1,
                    title="Scout the cavern",
                    description="Travel to the Echoing Cavern to investigate the stirring deep.",
                ),
                choices=[
                    ArcChoice(key="investigate", label="Descend toward the heat",
                              result="You turn toward the dark stairs down. The air grows warmer with every step."),
                    ArcChoice(key="warn", label="Warn the town first",
                              result="You raise the alarm. The town readies itself — and remembers your name."),
                ],
            ),
            ArcChapter(
                chapter=2,
                title="The Molten Heart",
                narration=(
                    "Whatever you chose, the embers settle for now. The Wanderer nods. "
                    "'You have done what you could. The deep will remember it.'"
                ),
                choices=[],  # epilogue
            ),
        ],
        default_reward=ArcReward(items={"coin": 40}, xp=60),
    ),
}


def get_arc(arc_id: str) -> Optional[StoryArcDef]:
    return STORY_ARCS.get(arc_id)


def all_arc_ids() -> List[str]:
    return list(STORY_ARCS.keys())
