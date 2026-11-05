<!-- cinecode brief: review -->
# Task (the cold comprehension test or an independent look)

Cold read of the script: from its narration lines and on-screen text alone, write what happened in order, and every place you had to guess (a thing never named, a cause never given, a line left hanging, a number with no referent)

# Files

PROJECT: /home/user/Filmler/sozlesmenin-anatomisi (the film's folder; every path below is inside it)
WRITES: review/script-cold.md
READS: review/script-lines.md
DO NOT TOUCH: STATE.md, shots.json, audio/mix.json, LICENSES.csv (the main chat owns them) and every file not under WRITES
DONE WHEN: review/script-cold.md lists the story in order and every guess, with the line it starts at

# The kit's rules for this task (quoted; they are not optional)

## 8. First-time viewer check (cold)

Read the script and shot list as someone who knows nothing about the idea, the references or the intentions:

- **Referents:** who is "I", "you", "we", "they"; what is "it" and "this" at every occurrence? Each has exactly one answer.
- **Causality:** every effect has a cause the viewer saw or heard. Which line relies on a reason never given?
- **Ending premise:** is everything the last line or image needs already in the film? Where?
- **Muted test:** with sound off, can the viewer say what happened in one sentence?
- **No line left hanging:** every line completes its meaning on its own; a line cut before the word that matters leaves the viewer waiting for it.

Fix the smallest thing where a break starts: reorder or retime first, then one short new line, and only then a rewrite.

1. **Draft cut first:** build the shots (item 2) and the sound (item 3) at draft quality first: shots at half size as the profile says, joined and laid on the mix as `renders/draft-v1.mp4`, checked with `python3 tools/make.py check renders/draft-vN.mp4` (the Quick draft checks on this cut: the hook, darkness, blank frames, stillness and repeats, rhythm, the sound floor, ready sounds and sync; it writes logs/check-draft-vN.txt and the guard holds a cut shown without it; fix what it holds; what is left as it is goes to the user with the cut, one plain line each, what, where and why, and the user decides; never only a line on the roadmap's card), then the silent one-sentence test (`engine.md` §4: a fresh helper sees only its small sheet and says what the film is about; a miss is fixed first). A story over about 3 minutes also gets the **cold comprehension test** on the cut: a fresh helper that knows nothing about the subject gets only the narration transcript and the sheet and writes in `review/comprehension-vN.md` what happened, who did what and why, the order of events, and what stayed unclear or felt like a jump; every unclear point is a red item before the draft is shown. With a narrator, the first line comes within 2 s in any film over a minute (`writing.md` §14; `make.py` names it NARRATION LATE). One question: final, or notes (notes are applied to drafts). The full-size render and the master start only after the OK.

# Report

At most 25 tool calls. Details go in the file under WRITES; reply in 10 lines or fewer: what was done, the files written, what was measured (the command and its result, not a claim), what is still open, and anything you saw that is outside your task.

End your report with these lines, exactly:
Verdict: APPROVE | FIX | UNVERIFIABLE
Red items: none, or one "- " line each (broken, must not reach a final)
Polish: what would make it better (never a reason for another round)
Evidence: the frames, strips and numbers you looked at
UNVERIFIABLE when you could not see or measure what decides it (no film, no frames, a sound question only an ear answers): never APPROVE then.
