from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class GuidelineSource:
    title: str
    language: str
    url: str
    summary: str


# Curated official / widely accepted coding guidelines.
GUIDELINE_CATALOG: tuple[GuidelineSource, ...] = (
    GuidelineSource(
        title="PEP 8 — Style Guide for Python Code",
        language="python",
        url="https://peps.python.org/pep-0008/",
        summary="Official Python style: naming, imports, line length, and readability conventions.",
    ),
    GuidelineSource(
        title="PEP 20 — The Zen of Python",
        language="python",
        url="https://peps.python.org/pep-0020/",
        summary="Core Python design principles: explicit over implicit, simple over complex.",
    ),
    GuidelineSource(
        title="MDN JavaScript Guide",
        language="javascript",
        url="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide",
        summary="Official MDN guidance for modern JavaScript language features and patterns.",
    ),
    GuidelineSource(
        title="MDN TypeScript / JS typed patterns",
        language="typescript",
        url="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide",
        summary="Prefer typed APIs, narrow unions, and explicit interfaces for maintainability.",
    ),
    GuidelineSource(
        title="Go Code Review Comments",
        language="go",
        url="https://go.dev/wiki/CodeReviewComments",
        summary="Official Go team guidance used in code review for idiomatic Go.",
    ),
    GuidelineSource(
        title="Rust API Guidelines",
        language="rust",
        url="https://rust-lang.github.io/api-guidelines/",
        summary="Official Rust API design checklist for crates and public interfaces.",
    ),
    GuidelineSource(
        title="Effective Java / Oracle Java Docs",
        language="java",
        url="https://docs.oracle.com/en/java/",
        summary="Prefer clear APIs, immutable data where practical, and checked error handling.",
    ),
    GuidelineSource(
        title="Microsoft C# Coding Conventions",
        language="csharp",
        url="https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/coding-style/coding-conventions",
        summary="Official .NET C# naming, layout, and language usage conventions.",
    ),
)


class GuidelinesService:
    def local_match(self, query: str, language: str | None = None) -> list[GuidelineSource]:
        q = query.casefold()
        lang = (language or "").casefold().strip()
        matches: list[GuidelineSource] = []
        for source in GUIDELINE_CATALOG:
            if lang and source.language != lang:
                continue
            haystack = f"{source.title} {source.summary} {source.language}".casefold()
            if any(token in haystack for token in q.split() if len(token) > 2) or (
                lang and source.language == lang
            ):
                matches.append(source)
        if not matches and lang:
            matches = [s for s in GUIDELINE_CATALOG if s.language == lang]
        if not matches:
            matches = list(GUIDELINE_CATALOG[:3])
        return matches[:5]

    async def fetch_online_summary(self, url: str) -> str | None:
        timeout = httpx.Timeout(8.0, connect=3.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "ProjectWe-CodingBot/0.3"})
                response.raise_for_status()
                text = response.text
        except Exception:
            return None

        # Keep a short plain-text snippet for prompt context.
        cleaned = " ".join(text.split())
        return cleaned[:500] if cleaned else None
