from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.bootstrap_common import train_specialist
from app.bootstrap_coding import (
    CODING_BOT,
    CODING_BOT_SLUG,
    CODING_SKILL_PARAMETERS,
    CODING_SKILLS,
    bootstrap_coding_bot as _bootstrap_coding_only,
)
from app.schemas.skill import SkillCreate
from app.schemas.specialist import SpecialistCreate

logger = logging.getLogger(__name__)

WEB_LEARNER_BOT_SLUG = "web-learner-bot"

WEB_LEARNER_BOT = SpecialistCreate(
    slug=WEB_LEARNER_BOT_SLUG,
    name="Web Learner",
    sector="web-learning",
    description=(
        "Specialist sub-bot that reads HTML web pages, extracts images, "
        "stores compressed learning on the laptop, and recalls it later."
    ),
    system_prompt=(
        "You are a web learning specialist working under Project We, the master assistant. "
        "You read HTML pages, search the web (DuckDuckGo or Bing), extract images, "
        "and store compressed learning on the laptop for later recall. "
        "Other bots (coding-bot, master) delegate URLs and search queries to you. "
        "Always respect internet permission settings. "
        "When answering, prefer previously stored captures listed in STORED WEB LEARNING. "
        "Summarize page content clearly and mention which capture IDs you used."
    ),
)

WEB_LEARNER_SKILLS: tuple[SkillCreate, ...] = (
    SkillCreate(
        slug="read-web-page",
        name="Read Web Page",
        category="web-learning",
        description="Fetch and parse HTML pages into readable text.",
        instructions=(
            "Given a URL, fetch the HTML page, extract the title and main text content, "
            "and summarize the key points for the user."
        ),
        parameters_schema={"max_chars": {"type": "integer", "default": 20000}},
    ),
    SkillCreate(
        slug="extract-page-images",
        name="Extract Page Images",
        category="web-learning",
        description="Find and download images referenced on a web page.",
        instructions=(
            "Locate image tags on the page, resolve absolute URLs, download images, "
            "and report how many were saved."
        ),
        parameters_schema={"max_images": {"type": "integer", "default": 8}},
    ),
    SkillCreate(
        slug="compress-store-learning",
        name="Compress Store Learning",
        category="web-learning",
        description="Store page text and images compressed on the local laptop.",
        instructions=(
            "Save page text as gzip JSON and images as compressed JPEG/binary files under "
            "data/web_learning/captures/. Keep storage efficient for later recall."
        ),
        parameters_schema={"compression": {"type": "string", "default": "gzip+jpeg"}},
    ),
    SkillCreate(
        slug="recall-stored-pages",
        name="Recall Stored Pages",
        category="web-learning",
        description="Use previously stored web captures when answering questions.",
        instructions=(
            "Search recent stored captures by title, URL, or summary and cite capture IDs "
            "when reusing learned web content."
        ),
        parameters_schema={"lookback": {"type": "integer", "default": 5}},
    ),
    SkillCreate(
        slug="web-search",
        name="Web Search",
        category="web-learning",
        description="Search the web via DuckDuckGo or Bing and return ranked links for other bots.",
        instructions=(
            "When any bot or the user needs to find pages on the internet, run a web search. "
            "Return the query, engine used, and top result URLs with titles. "
            "Optionally capture the best result page for deeper reading."
        ),
        parameters_schema={
            "engine": {"type": "string", "default": "duckduckgo"},
            "limit": {"type": "integer", "default": 5},
        },
    ),
)

WEB_LEARNER_SKILL_PARAMETERS: dict[str, dict] = {
    "read-web-page": {"max_chars": 20000},
    "extract-page-images": {"max_images": 8},
    "compress-store-learning": {"compression": "gzip+jpeg"},
    "recall-stored-pages": {"lookback": 5},
    "web-search": {"engine": "duckduckgo", "limit": 5},
}


def bootstrap_web_learner_bot(db: Session) -> None:
    train_specialist(db, WEB_LEARNER_BOT, WEB_LEARNER_SKILLS, WEB_LEARNER_SKILL_PARAMETERS)


def bootstrap_all_bots(db: Session) -> None:
    _bootstrap_coding_only(db)
    bootstrap_web_learner_bot(db)


# Backward-compatible alias
bootstrap_coding_bot = _bootstrap_coding_only
