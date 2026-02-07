---
name: reflect
description: Use before finishing work (committing, creating PRs) and after completing any task, fixing bugs, debugging, or when something unexpected happened — captures learnings into CLAUDE.md, MEMORY.md, or skills to prevent recurrence
---

# Reflect

Capture learnings before they're lost. Two modes depending on context.

## When to Use

- **Before committing or creating PRs** (quick check)
- After debugging a non-trivial issue
- When something unexpected happened (wrong assumption, surprising behavior)
- When user corrects your approach
- After a validation or deployment failure
- When you discover a new HA platform gotcha

**Skip for:** trivial typos, external failures, user-initiated requirement changes.

## Mode 1: Quick Check (before commits/PRs)

Ask yourself: "Did anything unexpected happen? Any new gotcha or pattern worth capturing?"

- **If no** — done. Move on.
- **If yes** — switch to Mode 2.

## Mode 2: Full Reflection (after mistakes, debugging, corrections)

### Reflect → Abstract → Document

| Phase | Key Questions | Output |
|-------|--------------|--------|
| Reflect | What happened? What assumption failed? | Root cause statement |
| Abstract | Is this a pattern? What's the general rule? | Generalized learning |
| Document | Where should this live? Is it already documented? | Updated docs |

**Reflect:** What was the specific mistake or surprise? What assumption was wrong?

**Abstract:** Is this a one-off or a recurring pattern? Express as a general rule ("Always X before Y", "Never assume X without checking").

**Document:** Check where it belongs (see below), then Grep existing docs for the topic before writing. **Update existing entries rather than adding new ones.** If the learning is already captured, stop.

## Where Learnings Live

Before documenting, check these locations — slot into the right place:

| Learning Type | Location | Examples |
|--------------|----------|----------|
| HA platform gotchas | `CLAUDE.md` → Critical Gotchas | Template whitespace, required_zones format, shell_command subprocess |
| Camera/streaming patterns | `CLAUDE.md` → Streaming/Frigate sections | go2rtc config, play_stream vs play_media |
| Session-to-session context | `MEMORY.md` | Entity refs, historical decisions, transition notes |
| Automation workflow pitfalls | `home-assistant-automation` skill → Common Mistakes | Entity discovery, validation, deployment |
| Debugging patterns | `home-assistant-debugging` skill → Common Mistakes/Failure Patterns | Template issues, restart behavior |
| Backup/deployment process | `home-assistant-backup` skill | Retention, sync issues |

**Dedup rule:** Grep existing docs for the topic first. If already covered, update the existing entry or stop. Don't create duplicates.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Superficial reflection ("I made an error") | Ask "why" at least 3 times to find root cause |
| Too specific (only fixes this instance) | Abstract to pattern that prevents future occurrences |
| Documenting without checking existing docs | Grep first — update existing entries, don't duplicate |
| Vague updates like "be more careful" | Express as a concrete, actionable rule |
| Skipping quick check before commits | Always pause to ask "anything unexpected?" |

## Red Flags

- Moving on after a significant debugging session or user correction without at least a quick check
- Writing documentation that doesn't address root cause
- Adding a new entry when an existing one covers the same topic
- Documenting in a place no one will find
