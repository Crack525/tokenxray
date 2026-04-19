---
description: Save a high-quality session checkpoint for handoff
allowed-tools: [Bash, Read, Write, Glob, Grep, mcp__crossmem__mem_save]
argument-hint: optional notes about what to capture
---

Create a checkpoint of this session for seamless handoff to a new session. Synthesize the working state from your own context — you know what was discussed, decided, and implemented.

Write the checkpoint to `.claude/checkpoint.md` with this structure:
- **Original Goal**: What the user asked for
- **What Was Done**: Key decisions, implementations, changes made
- **Current State**: Where things stand right now
- **Files Modified**: List of files changed with brief descriptions
- **Next Steps**: What remains to be done
- **Key Decisions**: Important choices made and why

If crossmem is available, also save a summary using `mcp__crossmem__mem_save`.

$ARGUMENTS
