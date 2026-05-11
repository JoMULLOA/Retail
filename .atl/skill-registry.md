# Skill Registry — Retail Vision (hallID)

Generated: 2026-05-11
Source: `~/.config/opencode/skills/`

## User Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| work-unit-commits | implementing a change, preparing commits, splitting PRs, chained/stacked PRs | Structure commits as deliverable work units with tests and docs beside code |
| comment-writer | drafting/posting feedback, review comments, maintainer replies, Slack, GitHub comments | Write warm, direct, human comments |
| cognitive-doc-design | writing guides, READMEs, RFCs, onboarding docs, architecture docs, review docs | Design documentation reducing cognitive load |
| chained-pr | PR exceeds 400 lines, planning chained/stacked PRs, reviewable slices | Split large changes into reviewable PR chains |
| issue-creation | creating GitHub issues, reporting bugs, requesting features | Issue creation workflow for Agent Teams Lite |
| branch-pr | creating PRs, opening PRs, preparing changes for review | PR creation workflow for Agent Teams Lite |
| skill-creator | creating new AI agent skills, adding agent instructions, documenting patterns | Creates new skills following Agent Skills spec |
| go-testing | writing Go tests, using teatest, adding test coverage | Go testing patterns (not applicable — Python project) |
| judgment-day | "judgment day", dual review, "que lo juzguen" | Parallel adversarial review protocol |

## Project Conventions

No project-level convention files detected (no `AGENTS.md`, `.cursorrules`, `CLAUDE.md`, `GEMINI.md`, or `copilot-instructions.md` at project root).

## SDD System Skills

| Skill | Phase |
|-------|-------|
| sdd-init | Initialization |
| sdd-explore | Investigation |
| sdd-propose | Proposal |
| sdd-spec | Specification |
| sdd-design | Design |
| sdd-tasks | Task breakdown |
| sdd-apply | Implementation |
| sdd-verify | Verification |
| sdd-archive | Archival |
| sdd-onboard | Onboarding |

## Compact Rules

### Python / FastAPI Project
- Use `app.py` as single-module entry point (current pattern)
- FastAPI routes: `@app.get`, `@app.post` with path prefixes
- Jinja2 templates in `templates/` directory
- Uploaded files stored in `uploads/` (gitignored)
- Model weights (`.pt`) are gitignored — document download URL
- Use `pathlib.Path` for filesystem operations
- CV2 + numpy for image processing
- Torch device detection: `cuda:0` if available, else `cpu`
- Thread-safe state via `threading.Lock()`
- Spanish comments and UI text (project convention)
- Dark-theme CSS with CSS custom properties
- Docker: multi-stage not needed, single `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime` base

### Conventional Commits
- Format: `type: description` (lowercase type, no scope)
- Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- No AI attribution or Co-Authored-By
- Examples: `feat: add person detection endpoint`, `fix: bind Docker to 0.0.0.0`

### SDD Artifacts (Engram mode)
- All artifacts persist to Engram with topic keys `sdd/{change-name}/{artifact}`
- No `openspec/` directory created
- Testing capabilities cached under `sdd/{project-name}/testing-capabilities`
