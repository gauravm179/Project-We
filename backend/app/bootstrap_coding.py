from __future__ import annotations

from sqlalchemy.orm import Session

from app.bootstrap_common import train_specialist
from app.coding.capabilities import SUPPORTED_LANGUAGES
from app.schemas.skill import SkillCreate
from app.schemas.specialist import SpecialistCreate

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
        parameters_schema={"style": {"type": "string", "default": "minimal-diff"}},
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
            "languages": {"type": "list", "description": "Languages for this build"},
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
    train_specialist(db, CODING_BOT, CODING_SKILLS, CODING_SKILL_PARAMETERS)
