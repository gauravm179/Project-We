from __future__ import annotations

SUPPORTED_LANGUAGES: tuple[dict[str, str], ...] = (
    {"id": "python", "name": "Python", "notes": "Scripts, APIs, data, automation"},
    {"id": "javascript", "name": "JavaScript", "notes": "Web apps, Node.js, browser logic"},
    {"id": "typescript", "name": "TypeScript", "notes": "Typed frontends and backends"},
    {"id": "java", "name": "Java", "notes": "Enterprise apps, Android, services"},
    {"id": "csharp", "name": "C#", "notes": ".NET apps, Unity, backend services"},
    {"id": "cpp", "name": "C++", "notes": "Systems, performance-critical code"},
    {"id": "c", "name": "C", "notes": "Embedded, systems, low-level logic"},
    {"id": "go", "name": "Go", "notes": "CLI tools, services, concurrency"},
    {"id": "rust", "name": "Rust", "notes": "Safe systems programming"},
    {"id": "ruby", "name": "Ruby", "notes": "Rails apps and scripting"},
    {"id": "php", "name": "PHP", "notes": "Web backends and CMS logic"},
    {"id": "swift", "name": "Swift", "notes": "iOS and macOS apps"},
    {"id": "kotlin", "name": "Kotlin", "notes": "Android and JVM services"},
    {"id": "sql", "name": "SQL", "notes": "Queries, schemas, data logic"},
    {"id": "bash", "name": "Bash / Shell", "notes": "Automation and devops scripts"},
    {"id": "html_css", "name": "HTML / CSS", "notes": "Markup, layout, UI structure"},
    {"id": "r", "name": "R", "notes": "Statistics and data analysis"},
    {"id": "scala", "name": "Scala", "notes": "JVM services and data pipelines"},
)

LOGIC_CAPABILITIES: tuple[str, ...] = (
    "Understand requirements and translate them into working code",
    "Design algorithms, data structures, and control flow",
    "Build features end-to-end from pseudocode to implementation",
    "Debug logic errors, off-by-one bugs, and race conditions",
    "Refactor messy code while preserving behavior",
    "Write and explain unit tests for critical paths",
    "Review code for correctness, security, and maintainability",
)

BUILD_CAPABILITIES: tuple[str, ...] = (
    "Scaffold new modules, classes, and project structure",
    "Implement API endpoints, services, and database models",
    "Create CLI tools, scripts, and automation workflows",
    "Build UI components and wire up frontend logic",
    "Add error handling, validation, and edge-case coverage",
    "Suggest minimal diffs that fit existing project conventions",
)
