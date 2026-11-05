<!-- cinecode brief: overlap -->
# Task (the overlap check: each candidate idea against the expected films and this user's own films, judged by someone who did not write them)

Judge each candidate in research/candidates.md against the predictions and this user's own films. The user's first message, quoted, so an overlap it asks for (a sequel, the same subject on purpose) is known and counts as CLEAR: Spor Finansı ve Muhasebesi dersi, 5. hafta 'Sözleşmenin Anatomisi' için 3-4 dakikalık, 16:9, açıklayıcı bir film: oyuncu maaş yapıları, bonuslar, salary cap ve lüks vergisi. UEFA'nın kadro maliyetini gelirin %70'i ile sınırlayan kuralı, EuroLeague lüks vergisi, TFF takım harcama limiti. İzleyici: spor bilimleri fakültesinde Z kuşağı lisans öğrencileri.

# Files

PROJECT: /home/claude/Filmler/sozlesmenin-anatomisi (the film's folder; every path below is inside it)
WRITES: research/overlap.md
READS: research/candidates.md (the ideas to judge), research/predict.md (the films anyone would expect; not there yet: python3 tools/brief.py wait research/predict.md), research/past-films.md (this user's own films)
DO NOT TOUCH: STATE.md, shots.json, audio/mix.json, LICENSES.csv (the main chat owns them) and every file not under WRITES
DONE WHEN: research/overlap.md holds one line per candidate: its number, then CLEAR, SHARES (one element repeats: which, and with what) or OVERLAP (the idea itself repeats: with what); a prediction by its number, a film by its title

# The kit's rules for this task (quoted; they are not optional)

**The overlap check (independent).** The maker cannot judge its own repeats either. Before the ideas reach the user, write the best five angles as candidates in `research/candidates.md` (numbered, each with its logline, key images, worlds or places, form, and the seed it grew from), then `python3 tools/brief.py overlap --task "<the user's first message, quoted>"`: it writes this user's own films into `research/past-films.md` (the memory `make.py` keeps, and the films on the same shelf) and prints the brief for a fresh helper, which reads the candidates beside `research/predict.md` and those films and writes `research/overlap.md`: one line per candidate, CLEAR; SHARES, when one element repeats while the idea is new (an ending, a form, a key image or a world; which one, and with what: a prediction by its number, a film by its title); or OVERLAP, when the idea itself repeats (its premise and key images, whatever the details; with what). What the message itself names (a brand, a product, a person, a place) is the user's and never an overlap on its own: a film about the same brand repeats only in its idea, images, worlds or form. About half a minute. The three strongest that are not OVERLAP are offered, a SHARES one with its shared element changed; an OVERLAP is dropped, never argued with, unless the user's own message asks for that film again (a sequel, the same subject on purpose); with fewer than three left, new candidates go through the check once more. The guard holds the ideas question until the check has read the latest candidates.

# Report

At most 25 tool calls. Details go in the file under WRITES; reply in 10 lines or fewer: what was done, the files written, what was measured (the command and its result, not a claim), what is still open, and anything you saw that is outside your task.
