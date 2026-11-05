<!-- cinecode brief: predict -->
# Task (the prediction test: the films the user's first message makes anyone expect, five lines, from that message alone)

Spor Finansı ve Muhasebesi dersi, 5. hafta 'Sözleşmenin Anatomisi' için 3-4 dakikalık, 16:9, açıklayıcı bir film: oyuncu maaş yapıları, bonuslar, salary cap ve lüks vergisi. UEFA'nın kadro maliyetini gelirin %70'i ile sınırlayan kuralı (2025-26'da 9 kulüp aştı, Fenerbahçe dahil), EuroLeague lüks vergisi (aşanların ödediği 5.438.684 € uyan 15 kulübe 362.579 € olarak dağıtıldı), TFF Kulüp Lisans Kurulu takım harcama limiti (Galatasaray 2026-27: 9,0 milyar TL). İzleyici: spor bilimleri fakültesinde Z kuşağı lisans öğrencileri.

# Files

PROJECT: /home/claude/Filmler/sozlesmenin-anatomisi (the film's folder; every path below is inside it)
WRITES: research/predict.md
READS: nothing: the user's first message is quoted in the task, and it is all you get
DO NOT TOUCH: STATE.md, shots.json, audio/mix.json, LICENSES.csv (the main chat owns them) and every file not under WRITES
DONE WHEN: research/predict.md holds five lines, one expected film each: its subject, key images and form

# The kit's rules for this task (quoted; they are not optional)

**The prediction test (independent).** The maker cannot judge its own surprise. At the very start, where the tool has helpers, a fresh helper (`python3 tools/brief.py predict`) gets only the user's first message, quoted, and nothing else, and writes `research/predict.md`: the five films it would expect from that message, one line each (subject, key images, form). Write the 10 angles while it runs. A kept angle that shares its subject, key image or form with a predicted line is replaced by the next one on the list; each interpretation offered then says in a few words what it does that the predictions did not. One reply, about a minute, never waited on by the user.

# Report

At most 25 tool calls. Details go in the file under WRITES; reply in 10 lines or fewer: what was done, the files written, what was measured (the command and its result, not a claim), what is still open, and anything you saw that is outside your task.
