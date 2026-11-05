# Builds film.html: one page that shows the whole project (status, pictures, script, shots, sources).
# Run from the film folder: python3 logs/build_hub.py [out.html]. Images are embedded, so the page opens anywhere.
import base64, html, json, re, subprocess, sys, os

OUT = sys.argv[1] if len(sys.argv) > 1 else 'film.html'
esc = html.escape


def img(path, width=1600):
    if not os.path.exists(path):
        return ''
    tmp = 'logs/_hub.jpg'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', path, '-vf', f"scale='min({width},iw)':-2", '-q:v', '4', tmp], check=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(open(tmp, 'rb').read()).decode()


def table_rows(text, start):
    part = text.split(start, 1)[1]
    rows = []
    for line in part.splitlines()[1:]:
        if not line.startswith('|'):
            if rows:
                break
            continue
        if '---' in line:
            continue
        rows.append([c.strip() for c in line.strip().strip('|').split('|')])
    return rows[1:] if rows else []


S = open('SCRIPT.md', encoding='utf-8').read()
STATE = open('STATE.md', encoding='utf-8').read()
FACTS = open('research/facts.md', encoding='utf-8').read()
shots = json.load(open('shots.json', encoding='utf-8'))['shots']

vo = {r[0]: r for r in table_rows(S, '## Lines') if r and r[0].startswith(('VO', '('))}
acts = [('1. perde · Kapak', 0, 40), ('2. perde · UEFA, oran çizgisi', 40, 95), ('3. perde · EuroLeague, vergi duvarı', 95, 160),
        ('4. perde · TFF, çitler', 160, 199), ('Kapanış', 199, 214)]


def sec(t):
    m, s = t.split('-')[0].split(':')
    return int(m) * 60 + float(s)


script_html = ''
for name, a, b in acts:
    lines = [r for r in vo.values() if re.match(r'\d+:\d', r[1]) and a <= sec(r[1]) < b]
    script_html += f'<h3>{esc(name)}</h3><ol class="lines">'
    for r in lines:
        if r[0].startswith('('):
            script_html += f'<li class="pause"><span class="t">{esc(r[1])}</span><em>{esc(r[0][1:-1])}: {esc(r[2])}</em></li>'
        else:
            script_html += f'<li><span class="t">{esc(r[1])}</span>{esc(r[2])}</li>'
    script_html += '</ol>'

shot_rows = ''.join(
    f'<tr><td>{esc(s["id"])}</td><td class="num">{s["start"]/24:.0f}–{s["end"]/24:.0f} s</td><td>{esc(s["description"])}</td>'
    f'<td>{esc(s["camera"]["size"])} · {esc(s["camera"]["move"]["line"].split(",")[0])}</td>'
    f'<td>{esc(" / ".join(t["text"] for t in s["text_on_screen"]))}</td></tr>' for s in shots)

fact_rows = ''
for r in table_rows(FACTS, '# Facts'):
    if len(r) < 5:
        continue
    st = r[2].split()[0]
    cls = {'OK': 'ok', 'PARTIAL': 'part', 'NO': 'no'}.get(st, '')
    lab = {'OK': 'Doğrulandı', 'PARTIAL': 'Kısmen', 'NO': 'Çıkarıldı'}.get(st, st)
    fact_rows += f'<tr><td class="num">{esc(r[0])}</td><td>{esc(r[1])}</td><td><span class="tag {cls}">{lab}</span></td><td class="src">{esc(r[3])}</td></tr>'

gates = [('Görüşme', True), ('Yol haritası', True), ('Senaryo', True), ('Stil karesi', True), ('Yazı tipi', True),
         ('Ses seçimi', False), ('Animatik', False), ('Taslak kurgu', False), ('Final', False)]
nxt = next(g for g, d in gates if not d)
gate_html = ''.join(f'<li class="{"done" if d else ("now" if g == nxt else "")}">{esc(g)}</li>' for g, d in gates)
words = re.search(r'\*\*Total words:\*\* (\d+)', S)

page = f'''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Teraslar Film Paneli</title>
<style>
:root{{--paper:#f5ebdb;--card:#fffaf1;--ink:#2a2017;--muted:#6b5a48;--line:#d9c9ae;--water:#3f7f8c;--red:#9b3b22;--ok:#3f7f5c;--part:#a06b14}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#1c1712;--card:#251e17;--ink:#f1e6d3;--muted:#b9a68c;--line:#4a3d2f;--water:#6fb3c0;--red:#e0866a;--ok:#7cc59a;--part:#e0b25c}}}}
:root[data-theme="dark"]{{--paper:#1c1712;--card:#251e17;--ink:#f1e6d3;--muted:#b9a68c;--line:#4a3d2f;--water:#6fb3c0;--red:#e0866a;--ok:#7cc59a;--part:#e0b25c}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-family:"IBM Plex Serif",Georgia,serif;font-size:clamp(28px,5vw,44px);line-height:1.1;margin:8px 0 4px}}
h2{{font-family:"IBM Plex Serif",Georgia,serif;font-size:24px;margin:40px 0 12px;padding-top:12px;border-top:2px solid var(--ink)}}
h3{{font-size:17px;margin:22px 0 6px;color:var(--water)}}
.sub{{color:var(--muted);margin:0 0 16px}}
nav{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}}
nav a{{color:var(--ink);text-decoration:none;border:1.5px solid var(--ink);padding:4px 12px;font-size:14px}}
nav a:hover{{background:var(--ink);color:var(--paper)}}
.gates{{list-style:none;display:flex;flex-wrap:wrap;gap:6px;padding:0;margin:12px 0}}
.gates li{{padding:6px 12px;border:1.5px dashed var(--line);font-size:14px;color:var(--muted)}}
.gates li.done{{border-style:solid;border-color:var(--ok);color:var(--ok)}}
.gates li.done::before{{content:"✓ "}}
.gates li.now{{border:2px solid var(--red);color:var(--red);font-weight:600}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.card{{background:var(--card);border:1.5px solid var(--line);padding:14px}}
.card b{{display:block;font-size:13px;color:var(--muted);font-weight:500}}
.card span{{font-size:17px}}
figure{{margin:0 0 20px}} figure img{{width:100%;height:auto;display:block;border:1.5px solid var(--ink)}}
figcaption{{font-size:14px;color:var(--muted);margin-top:6px}}
.lines{{list-style:none;padding:0;margin:0}}
.lines li{{display:flex;gap:14px;padding:5px 0;border-bottom:1px solid var(--line)}}
.lines .t,.num{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px;color:var(--muted);min-width:56px}}
.lines .pause em{{color:var(--red)}}
.thesis{{font-family:"IBM Plex Serif",Georgia,serif;font-size:22px;border-left:4px solid var(--water);padding:6px 14px;margin:16px 0}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;font-size:14px;min-width:640px}}
th,td{{text-align:left;vertical-align:top;padding:7px 8px;border-bottom:1px solid var(--line)}}
th{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
.src{{color:var(--muted);font-size:13px}}
.tag{{font-size:12px;padding:2px 8px;border:1.5px solid;white-space:nowrap}}
.tag.ok{{color:var(--ok)}} .tag.part{{color:var(--part)}} .tag.no{{color:var(--red)}}
ol.steps li{{margin:6px 0}} code{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px;background:var(--card);padding:1px 5px;border:1px solid var(--line)}}
</style></head><body><main>
<p class="sub">Spor Finansı ve Muhasebesi · 5. hafta · cinecode, Film modu</p>
<h1>Sözleşmenin Anatomisi: Teraslar</h1>
<p class="sub">Kulübün maaş bordrosu, kesiti çizilmiş bir teras yamacından akan su. UEFA, EuroLeague ve TFF aynı yamaca üç ayrı şekil çiziyor.</p>
<nav><a href="#durum">Durum</a><a href="#gorunus">Görünüş</a><a href="#senaryo">Senaryo</a><a href="#planlar">Planlar</a><a href="#kaynaklar">Kaynaklar</a><a href="#sonraki">Sıradaki adım</a></nav>

<h2 id="durum">Durum</h2>
<ul class="gates">{gate_html}</ul>
<div class="cards">
<div class="card"><b>Süre ve format</b><span>3:34 · 16:9 · 1920×1080</span></div>
<div class="card"><b>Biçim</b><span>3B maket, kesit çizimi</span></div>
<div class="card"><b>Anlatıcı</b><span>Türkçe, sıcak ve meraklı · {words.group(1) if words else "?"} kelime</span></div>
<div class="card"><b>Ses</b><span>Su ve ahşap · kodla yazılmış müzik</span></div>
<div class="card"><b>Yazı tipi</b><span>IBM Plex Serif, Sans, Mono</span></div>
<div class="card"><b>Plan sayısı</b><span>{len(shots)} plan · ortalama {214/len(shots):.1f} sn</span></div>
</div>

<h2 id="gorunus">Görünüş</h2>
<figure><img src="{img('review/style-v1b.png' if os.path.exists('review/style-v1b.png') else 'review/style-v1.png')}" alt="Stil karesi: Strasbourg terası %70 çizgisini aşıyor, su alt terasa dökülüyor"><figcaption>Onaylı stil karesi, S11 (1:14). Bundan sonraki her kare bu ölçüye göre yapılacak.</figcaption></figure>
<figure><img src="{img('review/directions.jpg')}" alt="Yön panosu"><figcaption>Yön panosu: C Kesit Çizimi seçildi. Kareler yalnızca ruh hali için.</figcaption></figure>
<figure><img src="{img('review/type-board.jpg', 1000)}" alt="Yazı tipi panosu"><figcaption>Yazı tipi: 3. eşleştirme, IBM Plex seçildi.</figcaption></figure>
<figure><img src="{img('research/board-v1/sheet.jpg', 1000)}" alt="Referans panosu"><figcaption>Referans panosu: minyatür çerçeve, gerçek teras duvarları, su kapakları.</figcaption></figure>

<h2 id="senaryo">Senaryo <span class="sub">(v2, kilitli)</span></h2>
<p class="thesis">Her kurum suyu başka bir şekille tutar.</p>
{script_html}

<h2 id="planlar">Planlar</h2>
<div class="scroll"><table><thead><tr><th>Plan</th><th>Zaman</th><th>Ne görüyoruz</th><th>Kamera</th><th>Ekran yazısı</th></tr></thead><tbody>{shot_rows}</tbody></table></div>

<h2 id="kaynaklar">Kaynaklar ve doğrulama</h2>
<p class="sub">Filmde yalnızca "Doğrulandı" satırlar olduğu gibi kullanılıyor. "Kısmen" olanlar genel sözcüklerle anlatılıyor, "Çıkarıldı" olanlar filmde yok.</p>
<div class="scroll"><table><thead><tr><th>#</th><th>İddia</th><th>Durum</th><th>Kaynak</th></tr></thead><tbody>{fact_rows}</tbody></table></div>

<h2 id="sonraki">Sıradaki adım: ses seçimi</h2>
<ol class="steps">
<li>Ücretsiz Gemini anahtarını <code>aistudio.google.com/apikey</code> adresinden al. Bulut oturumunda ortam ayarlarına <code>GEMINI_API_KEY</code> olarak ekle, kendi bilgisayarında Claude'a "anahtarı kaydet" de. Anahtarı sohbete yapıştırma.</li>
<li>2–3 Türkçe ses denemesi gelir; birini kulağınla seçersin.</li>
<li>Ardından animatik: 28 planın durağan kareleri seçtiğin sesin gerçek süreleriyle birleştirilir.</li>
</ol>
</main></body></html>'''
open(OUT, 'w', encoding='utf-8').write(page)
os.remove('logs/_hub.jpg')
print(OUT, f'{os.path.getsize(OUT)/1e6:.1f} MB')
