<!-- cinecode: kit block, replaced by --update-tools -->
# Film project

This folder is a short film made with code. When the user asks about the film (or says "continue", "devam"),
load the cinecode skill (in Claude Code through the Skill tool, which also starts its context guard; elsewhere read
`/root/.claude/skills/cinecode/SKILL.md` once). State lives in `STATE.md`; read it first ("Resume here").
The main chat builds what it holds the context for and makes small revisions (up to five targeted edits) itself;
independent parts and larger revisions go to fresh subagents briefed from files (`/root/.claude/skills/cinecode/references/context-protocol.md` §1).
<!-- cinecode: end of kit block -->
