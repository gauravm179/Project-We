from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coding.capabilities import SUPPORTED_LANGUAGES
from app.db.models import Skill, SkillAssignment, Specialist
from app.schemas.skill import SkillCreate, SkillLearnRequest
from app.schemas.specialist import SpecialistCreate, SpecialistUpdate
from app.skills.service import SkillService
from app.specialists.service import SpecialistService

logger = logging.getLogger(__name__)

CODING_BOT_SLUG = "coding-bot"

_LANGUAGE_LIST = ", ".join(lang["name"] for lang in SUPPORTED_LANGUAGES)

CODING_BOT = SpecialistCreate(
    slug=CODING_BOT_SLUG,
    name="Code Assistant",
    sector="coding",
    description=(
        "Specialist sub-bot for writing, reviewing, debugging, and building code across "
        f"{len(SUPPORTED_LANGUAGES)} languages."
    ),
    system_prompt=(
        "You are an expert software engineer working under Project We, the master assistant. "
        "You understand program logic deeply: algorithms, data structures, control flow, state, "
        "and how systems are built end-to-end. "
        "You write clean, tested, production-quality code and can build features from requirements, "
        "pseudocode, or partial implementations. "
        "You explain trade-offs clearly, prefer minimal diffs, follow existing project conventions, "
        "and consider edge cases. "
        "When reviewing code, focus on correctness, security, performance, and maintainability. "
        "When debugging, reason step-by-step from symptoms to root cause. "
        f"You can help with these languages: {_LANGUAGE_LIST}. "
        "If the user does not specify a language, infer it from context or ask briefly."
    ),
)

CODING_SKILLS: tuple[SkillCreate, ...] = (
    SkillCreate(
        slug="code-review",
        name="Code Review",
        category="coding",
        description="Review code for bugs, security issues, and maintainability.",
        instructions=(
            "Review the provided code carefully. Report issues by severity (critical, major, minor). "
            "Suggest concrete fixes with minimal diffs. Check for edge cases, error handling, "
            "naming clarity, and security risks such as injection or unsafe deserialization."
        ),
        parameters_schema={
            "language": {"type": "string", "description": "Primary language or framework"},
            "focus": {"type": "string", "default": "correctness"},
        },
    ),
    SkillCreate(
        slug="write-tests",
        name="Write Tests",
        category="coding",
        description="Generate focused unit and integration tests.",
        instructions=(
            "Write tests that cover happy paths, edge cases, and failure modes. "
            "Use the project's existing test framework and naming conventions. "
            "Prefer clear arrange-act-assert structure and avoid testing implementation details."
        ),
        parameters_schema={
            "framework": {"type": "string", "description": "Test framework, e.g. pytest or jest"},
            "coverage_goal": {"type": "string", "default": "critical paths"},
        },
    ),
    SkillCreate(
        slug="debug-errors",
        name="Debug Errors",
        category="coding",
        description="Diagnose stack traces, logs, and failing tests.",
        instructions=(
            "Analyze errors systematically: reproduce the failure, identify the failing layer, "
            "trace the call path, propose the most likely root cause, and recommend a fix. "
            "If information is missing, state assumptions explicitly."
        ),
        parameters_schema={
            "runtime": {"type": "string", "description": "Runtime or environment, e.g. python, node"},
            "log_source": {"type": "string", "default": "user-provided"},
        },
    ),
    SkillCreate(
        slug="refactor-code",
        name="Refactor Code",
        category="coding",
        description="Improve structure without changing behavior.",
        instructions=(
            "Refactor for readability and maintainability while preserving behavior. "
            "Extract functions when logic repeats, simplify conditionals, improve naming, "
            "and keep changes scoped. Call out any behavior risks before suggesting large moves."
        ),
        parameters_schema={
            "style": {"type": "string", "default": "minimal-diff"},
        },
    ),
    SkillCreate(
        slug="build-logic",
        name="Build Logic",
        category="coding",
        description="Design and implement program logic and features from requirements.",
        instructions=(
            "Break the request into inputs, outputs, data structures, and control flow. "
            "State assumptions, outline the algorithm, then provide working code. "
            "Cover edge cases, validation, and error paths. "
            "Explain how the logic fits together so the user can extend it."
        ),
        parameters_schema={
            "languages": {
                "type": "list",
                "description": "Languages the bot should use for this build",
            },
            "delivery": {"type": "string", "default": "working code with brief explanation"},
        },
    ),
)

CODING_SKILL_PARAMETERS: dict[str, dict] = {
    "code-review": {"language": "any", "focus": "correctness"},
    "write-tests": {"framework": "auto-detect", "coverage_goal": "critical paths"},
    "debug-errors": {"runtime": "auto-detect", "log_source": "user-provided"},
    "refactor-code": {"style": "minimal-diff"},
    "build-logic": {
        "languages": [lang["id"] for lang in SUPPORTED_LANGUAGES],
        "delivery": "working code with brief explanation",
    },
}


def bootstrap_coding_bot(db: Session) -> None:
    """Ensure the coding specialist exists under the master bot and is fully trained."""
    specialists = SpecialistService()
    skills = SkillService()

    existing = specialists.get_by_slug(db, CODING_BOT_SLUG)
    if existing is None:
        created = specialists.create(db, CODING_BOT)
        if created is None:
            logger.warning("Could not create %s; slug may already exist", CODING_BOT_SLUG)
            return
        logger.info("Bootstrapped specialist %s under master bot", CODING_BOT_SLUG)
    else:
        specialists.update(
            db,
            CODING_BOT_SLUG,
            SpecialistUpdate(
                system_prompt=CODING_BOT.system_prompt,
                description=CODING_BOT.description,
            ),
        )
        logger.info("Refreshed %s profile with latest language and build capabilities", CODING_BOT_SLUG)

    for skill_payload in CODING_SKILLS:
        if skills.get_skill(db, skill_payload.slug) is None:
            created_skill = skills.create_skill(db, skill_payload)
            if created_skill:
                logger.info("Bootstrapped coding skill %s", skill_payload.slug)

    specialist_row = db.scalar(select(Specialist).where(Specialist.slug == CODING_BOT_SLUG))
    if specialist_row is None:
        return

    for skill_payload in CODING_SKILLS:
        skill_row = db.scalar(select(Skill).where(Skill.slug == skill_payload.slug))
        if skill_row is None:
            continue

        assignment = db.scalar(
            select(SkillAssignment).where(
                SkillAssignment.skill_id == skill_row.id,
                SkillAssignment.specialist_id == specialist_row.id,
            )
        )
        if assignment is None:
            learned = skills.learn_skill(
                db,
                specialist_slug=CODING_BOT_SLUG,
                payload=SkillLearnRequest(
                    skill_slug=skill_payload.slug,
                    parameters=CODING_SKILL_PARAMETERS.get(skill_payload.slug, {}),
                ),
            )
            if learned is None:
                logger.warning("Could not train %s with skill %s", CODING_BOT_SLUG, skill_payload.slug)
                continue
            assignment = db.scalar(
                select(SkillAssignment).where(SkillAssignment.id == learned.id)
            )

        if assignment and assignment.status != "active":
            skills.activate_skill(db, assignment.id)
            logger.info("Activated skill %s for %s", skill_payload.slug, CODING_BOT_SLUG)
