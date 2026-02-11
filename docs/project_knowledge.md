# Project Knowledge Base

Copilot Echo can maintain **per-project knowledge bases** — long-lived markdown files that accumulate context about a specific project over its lifetime. Unlike the personal knowledge file (which holds global facts), project knowledge bases capture decisions, work items, PR outcomes, and lessons learned for a particular effort.

## Why

When working on a large project over weeks or months, you build up context that's easy to forget — why a design decision was made, which work items were completed, what blockers were hit. A project knowledge base gives the agent a persistent memory of that context so it can:

- Answer questions about past decisions without you re-explaining
- Understand which work items and PRs belong to the project
- Track progress and summarize what's been done
- Carry forward lessons learned from earlier in the project

## How It Works

### File Structure

```
config/
  knowledge.md                    ← personal/global knowledge (always loaded)
  projects/
    active/
      metrics-reliability.md      ← injected into system prompt every session
      query-performance.md        ← supports multiple active projects
    archive/
      query-migration.md          ← NOT injected, but loadable on demand
```

- **`config/projects/`** is gitignored — each developer manages their own projects.
- **`active/`** — all files here are automatically injected into the agent's system prompt alongside `knowledge.md`. The agent always has this context.
- **`archive/`** — completed projects live here. They are NOT loaded into the system prompt by default to keep it lean. The agent can load them on demand if you ask about past work.

### Voice Commands

| Phrase | Action |
|---|---|
| **"Start a project called {name}"** | Creates a new project file in `active/` with a template |
| **"Finish project {name}"** / **"Close project {name}"** | Archives the project: moves it to `archive/`, optionally summarizes key takeaways into `knowledge.md` |
| **"List my projects"** | Reads out active and archived project names |
| **"What do we know about {name}?"** | Summarizes the project knowledge base (works for both active and archived) |

### Lifecycle

```
  "Start a project called metrics reliability"
       │
       ▼
  ┌─────────────────────────────────┐
  │  config/projects/active/        │
  │  metrics-reliability.md created │
  │  with template sections         │
  └──────────────┬──────────────────┘
                 │
       ┌─────────▼─────────┐
       │  Active project    │  ◄── auto-injected into every session
       │  Agent appends:    │
       │  • Work item notes │
       │  • PR outcomes     │
       │  • Decisions made  │
       │  • Blockers hit    │
       └─────────┬─────────┘
                 │
  "Finish project metrics reliability"
                 │
       ┌─────────▼──────────────────────────┐
       │  1. Agent summarizes key takeaways │
       │  2. Appends summary to knowledge.md│
       │     (under "## Completed Projects")│
       │  3. Moves file to archive/         │
       └────────────────────────────────────┘
```

### Project File Template

When a new project is created, the file is initialized with this structure:

```markdown
# Project: {Name}

**Created:** {date}
**Status:** Active
**Goal:** (to be filled in by user or agent)

## Repos & Work Items
- Primary repo: (inherited from knowledge.md or specified)
- Work items: (agent appends as they're discussed)

## Key Decisions
<!-- Agent appends decisions as they're made during conversations -->

## Progress Log
<!-- Agent appends one-liner summaries of completed work items, PRs, etc. -->

## Blockers & Issues
<!-- Agent notes blockers encountered and how they were resolved -->

## Lessons Learned
<!-- Insights that might be useful for future projects -->
```

### Auto-Capture

During normal conversations, when the agent interacts with project-related work items or PRs, it should automatically append brief entries to the active project file:

- **Work item resolved:** `- [2026-02-11] WI#12345: Fixed query timeout in dashboard (resolved)`
- **PR completed:** `- [2026-02-11] PR#6789: Added retry logic to metrics pipeline (merged)`
- **Decision made:** `- [2026-02-11] Decided to use exponential backoff instead of fixed retry`
- **Blocker hit:** `- [2026-02-11] Blocked on permissions for prod metrics endpoint — filed WI#12350`

This happens passively — the user doesn't need to say "log this." The agent recognizes project-relevant activity and appends it.

### Archival Behavior

When a project is finished:

1. The agent generates a brief **summary paragraph** of the project (goal, outcome, duration, key stats).
2. That summary is appended to `knowledge.md` under a `## Completed Projects` section, so the agent retains a high-level memory even without loading the archive.
3. The full project file is moved from `active/` to `archive/`.
4. The archived file is no longer injected into the system prompt.

If you later ask about the project ("what did we do in the query migration project?"), the agent loads the archived file on demand to answer in detail.

### Size Management

To prevent the system prompt from growing too large:

- Each active project file is capped at a configurable size (default: ~4000 chars).
- When a project file approaches the cap, the agent summarizes older entries (progress log, resolved blockers) into a compact form and replaces the verbose entries.
- The number of active projects is not artificially limited, but users are encouraged to archive completed work to keep things lean.

## Configuration

```yaml
agent:
  knowledge_file: "config/knowledge.md"
  projects_dir: "config/projects"           # root directory for project files
  project_max_chars: 4000                   # max chars per active project before summarization
```

## Gitignore

`config/projects/` is gitignored. Each developer maintains their own active and archived projects locally. The project structure is personal — your active projects won't conflict with another developer's.
