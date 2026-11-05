# State: Sözleşmenin Anatomisi (Spor Finansı, 5. hafta)

Read this first in every new session, after loading the cinecode skill (Claude Code: the Skill tool, never a plain read of SKILL.md), then `python3 KIT/scripts/init_film.py . --update-tools` silently; update "Now" before ending every turn. Keep it short.
Kit: ~/.claude/skills/cinecode
Method: this chat coordinates and builds what it holds the context for; a fresh helper takes only an independent part beside it (sound, narration takes, research, the independent viewer) or a long film's chapter, briefed from files (`/root/.claude/skills/cinecode/references/context-protocol.md`).

## Resume here
<!-- Updated at every gate and before every handoff. A new chat starts with "STATE.md'den devam et" / "Continue from STATE.md". -->
- **Phase:** 4b type picked (plex-system); Step 5 animatic next
- **Pace:** steps (user)
- **Approved gates:** 1 interview, 2 roadmap, 3 script v2 locked, 4 style frame v1, 4b type plex (2026-11-05); thesis line: 'Her kurum suyu başka bir şekille tutar.' (user)
- **Open notes:** none (notes/round-N.md)
- **Next action (on the user's computer):** run `python3 ~/.claude/skills/cinecode/scripts/init_film.py . --update-tools`, set GEMINI_API_KEY with `python3 tools/keys.py open GEMINI_API_KEY`, then narrator auditions (tts.py --audition, 2–3 Turkish Gemini voices, user picks by ear), then Step 5 animatic (references/film-mode.md Step 5): build all 28 shots in engine/teraslar.html (one page, shot table by time), stills per shot, animatic with temp VO; narrator takes first (tts.py, user picks by ear)
- **Budget so far:** ~8% of the Balanced ceiling

## Decisions so far
- **Idea (Q1):** Teraslar (user): a club's payroll is water poured down a diorama hillside of rice terraces. UEFA carves its 70% line into the slope; EuroLeague tax bands are stepped terraces whose overflow evaporates into a cloud that rains equally on 15 neighbouring terraces (changed from 'channels', overlap check); TFF gives each club a fence of its own height. A contract opens as a sluice gate. Spark s2 (Museum Island · terraced rice field · diorama).
- **Overlap:** research/overlap.md (all SHARES, shared element changed as above). Predictions: research/predict.md.
- **Facts (verified earlier, Spor Finansı week 5):** UEFA squad cost rule 90% (2023/24), 80% (2024/25), 70% (2025/26 on): wages + transfer amortisation + agent fees over revenue + player-sale profit. 2025-26 sanctions (Reuters, 30 Jun 2026): 9 clubs over 70% incl. Fenerbahçe; Strasbourg 25 m€ (12 conditional), Aston Villa 22,5 m€ (15 conditional); Bologna and Napoli over 70% but offset by football earnings. EuroLeague CBS: floor 32%, base 40% of ALCDR; 2026-27 ALCDR 22.298.591 €; bands 0,50 / 0,75 / 1,00 € per € (BRL); 4 clubs paid 5.438.684 € in total → 362.579 € to each of 15 compliant clubs. TFF THL 2026-27 (TFF, 22 Jun 2026): Galatasaray 9.006.596.835 TL, Fenerbahçe 6.330.032.702, Beşiktaş 4.123.397.974, Trabzonspor 2.530.783.285.
- **Render note (cloud session only):** no GPU there; capture needed `CHROME_PATH=/usr/bin/google-chrome` and `--flags "--use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist"` (WebGL2 via SwiftShader, slow).

## Now
- **Step:** 1 Interview
- **Gate:** <waiting for user: what / passed>
- **Next step:** <one concrete line>
- **Waiting for:** <user / background job / nothing>
- **Profile:** balanced
- **Mode:** Film (user)
- **Purpose:** ad & product (explainer, user) (`/root/.claude/skills/cinecode/references/purpose-<cinematic|ad>.md`)
- **Format:** 3-4 min, 16:9, 1920x1080 (user)
- **Medium:** 3B maket (three.js diorama) (user)
- **Look:** kesit-cizimi (engine/looks.mjs), from C Kesit Çizimi (user): the diorama hillside cut in section like an engineering drawing; cream paper ground, ink outlines, dimension lines and counters drawn on (70% line, BRL bands, TFF fence heights); frontal symmetric miniature camera (Moebius line + Isle of Dogs / Grand Budapest miniature). Board: review/directions.jpg, palette #2a2017 #735a56 #825c2d #b4a389 #f5ebdb
- **Tone:** meraklı · net · oyunbaz (user) · References: search open sources, one board with the roadmap (user)
- **Finishing:** none (user) <!-- off by default; chosen at the style frame -->
- **Voice:** Turkish narrator, warm and curious (user); takes picked by ear later
- **Sound identity:** Su ve ahşap (user): water on the terraces, a wooden sluice creaks open per contract; signature: a bamboo water clapper (shishi-odoshi) that fills and tips with a 'tok' every time a limit overflows
- **Music:** code (user) <!-- always asked, the recording picked by ear -->
- **Type:** plex-system: IBM Plex Serif (display: cards, titles) + IBM Plex Sans (text: labels) + IBM Plex Mono (numbers on dimension lines) · user: engineering-drawing lineage, Turkish glyphs · sentence case, left-aligned cards on paper with ink frame · no rule breaks
- **Subtitles:** off
- **Last output:** <path, version>
- **Disk free at last check:** <GB, date>

## Running jobs
| Job | Command (short) | PID | Status file | Log | Started |
|---|---|---|---|---|---|

## Gates
| Step | Gate | Result | Date | Note |
|---|---|---|---|---|
| 1 | interview answered / defaults accepted | | | |
| 2 | roadmap approved | | | |
| 3 | script and text approved | | | |
| 4 | style frame approved, finishing chosen | | | |
| 4b | type pairing picked | | | |
| 5 | animatic approved | | | |
| 6a | draft cut approved | | | |
| 6 | final delivered | | | |

## Decisions
| Date | Decision | Why | Who |
|---|---|---|---|
| 2026-11-05 | Narration kept at 289 words (validator asks 385-492) | numbers carry on screen and need reading time; user approved v2 | user |
| 2026-11-05 | VO7 'Soru şu: su nerede durmak zorunda?' kept | it is the film's open question, answered by the coda | agent |
| 2026-11-05 | Fenerbahçe 2025 breach, Villa conditional part, EuroLeague tax bands cut | not confirmed (research/facts.md) | agent |

## Notes rounds
Verbatim notes and the per-shot split live in `notes/round-N.md`.

| Round | File | Shots touched | Unchanged | Status |
|---|---|---|---|---|

## Agent tasks
| Task | Calls | Brief (files read) | Output file | Result |
|---|---|---|---|---|

## Budget meter
Ceiling: <Economy / Balanced / Quality> (internal caps: `references/context-protocol.md` §6). Stop and ask at 80%.

| Phase | Share of ceiling | Estimate so far | % of share | Note |
|---|---|---|---|---|
| 1-2 Interview + roadmap | 10% | | | |
| 3 Script | 10% | | | |
| 4 Style frame | 20% | | | |
| 5 Animatic | 15% | | | |
| 6 Render, sound, final | 35% | | | |
| Notes rounds | 10% | | | |
| **Total** | 100% | | | |

## Versions
| Version | File | What changed | Snapshot |
|---|---|---|---|

- Render time measured: 5.4 s per frame at 1920x1080 on SwiftShader (style-v1); 5136 frames ≈ 7.7 h full size.
