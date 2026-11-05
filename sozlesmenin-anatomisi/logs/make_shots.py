# Builds shots.json from the locked SCRIPT.md (v2) and the roadmap. Run: python3 logs/make_shots.py
import json, re
FPS = 24
S = open('SCRIPT.md', encoding='utf-8').read()
VO = {m[0]: m[2].strip() for m in re.findall(r'^\| (VO\d+b?) \| ([^|]+)\| ([^|]+)\|', S, re.M)}

# id, start s, end s, location, description, action, size, angle, lens, move line, move type, speed, sound, vo ids, texts [(t0,t1,text)], transition
R = [
("S01",0,6.5,"summit","the wooden sluice at the top of the cut-away hillside, cream paper behind","the sluice lifts and water bursts onto the first terrace from frame 1","CU","eye",50,"crane down, 6 s, follows the water from the sluice to the first terrace","crane-down","medium","sluice creak and splash from frame 1",["VO1"],[],"cut"),
("S02",6.5,13.5,"upper terraces","the water stream reaching the second terrace and settling into a steady flow","the steady stream fills a carved channel","MS","side",35,"truck right with the stream, slow","truck","slow","steady trickle",["VO2","VO3"],[(2.5,5.5,"sabit maaş")],"cut"),
("S03",13.5,18,"upper terraces","a second channel where water arrives in pulses","pulses surge on a beat and fall back","ECU","eye",85,"locked-off hold on the channel lip","static","slow","wave surges, one marimba hit per pulse",["VO4"],[(0,3,"bonus")],"cut"),
("S04",18,25,"upper terraces","a drawn wooden bucket tips once and empties into the top terrace","the bucket tips and pours","CU","high",50,"tilt down with the falling water, medium","tilt","medium","one heavy pour",["VO5"],[(0,3,"imza parası")],"cut"),
("S05",25,34,"whole hillside","the whole hillside in section: many sluices pouring at once","water runs down the terraces from every contract","WS","frontal",35,"pull-back reveal from one sluice to the whole section, slow","pull-back","slow","many trickles; the bamboo clapper starts filling",["VO6","VO7"],[],"cut"),
("S06",34,40,"foot of the hill","a dashed ink line draws itself across the slope and erases","the question line draws and erases","MS","frontal",50,"locked-off hold","static","slow","pencil scratch",["VO8"],[],"wipe"),
("S07",40,50,"UEFA hillside, catchment","rain falls on a catchment basin at the top; a side spring joins it","rain fills the basin; the spring (player sales) adds to it","WS","high",28,"crane down from the clouds to the basin, slow","crane-down","slow","rain on paper, a spring",["VO9","VO10"],[(0,2.5,"UEFA")],"cut"),
("S08",50,56,"UEFA hillside, terraces","the water spent down the terraces, labels drawing on: maaş, amortisman, menajer","three labels ink themselves onto three streams","MCU","side",50,"truck left across the labels, medium","truck","medium","three small knocks",["VO11","VO12"],[],"cut"),
("S09",56,64,"UEFA hillside, the line","a 70% line carved into the slope as a dimension line from the basin","the line drops 90, 80, 70 with year marks","MS","frontal",50,"tilt down along the dimension line, slow","tilt","slow","three stamp knocks",["VO13","VO13b","VO14"],[(1.5,7.5,"kadro maliyeti / gelir ≤ %70")],"cut"),
("S10",64,71,"UEFA hillside, the line","the water level climbing to the line on one club's terrace","water rises to the line; held breath","CU","eye",85,"dolly in, slow, onto the line","push-in","slow","water rises; 0.8 s silence at 69 s",["VO15"],[(0,4.5,"2023 %90  2024 %80  2025 %70")],"cut"),
("S11",71,80,"UEFA hillside, the spill","the terrace overflows the line; the bamboo clapper tips","overflow; dimension lines measure the fine","ECU","eye",100,"whip pan to the clapper, then hold","whip-pan","fast","first tok",["VO16","VO17","VO18"],[(2.5,5.5,"Strasbourg 13 m€"),(5.5,8.5,"+12 m€ koşullu")],"cut"),
("S12",80,87,"UEFA hillside, the spill","a second overflowing terrace; its gate narrows","the terrace's gate narrows (List A)","MCU","high",50,"crane down onto the narrowing gate, medium","crane-down","medium","wood squeeze",["VO19","VO20"],[(0,3.5,"Aston Villa 22,5 m€")],"cut"),
("S13",87,95,"UEFA hillside, the spring","a spring of football profit refills the basin and the level drops under the line","the level falls back under the line","WS","frontal",35,"locked-off hold","static","slow","water calms",["VO21","VO22","VO22b"],[],"wipe"),
("S14",95,103,"EuroLeague hillside, the wall","a stone terrace wall built across the slope","the wall rises course by course","MS","side",35,"crane up over the wall, medium","crane-up","medium","stone knocks",["VO23","VO24"],[(0,2.5,"EUROLEAGUE")],"cut"),
("S15",103,109,"EuroLeague hillside, the wall","three tall stones standing apart, outside the count","three stones are lifted out of the measure","CU","low",50,"truck along the three stones, slow","truck","slow","a knock per stone",["VO25"],[(0,3,"3 çapa oyuncu")],"cut"),
("S16",109,118,"EuroLeague hillside, the overflow","water passes the wall and part of it lifts as vapour","overflow turns to vapour","MCU","eye",50,"tilt up with the vapour, slow","tilt","slow","vapour hiss",["VO26"],[],"cut"),
("S17",118,127,"EuroLeague hillside, Olympiacos terrace","one terrace's spill measured, a counter splits it in half","606.580 splits, half rises","ECU","frontal",85,"dolly in on the counter, slow","push-in","slow","counter ticks",["VO27","VO28"],[(0,6,"Olympiacos +606.580 € → 303.290 €")],"cut"),
("S18",127,136,"EuroLeague sky","four columns of vapour gather into one cloud","the cloud grows from four spills","WS","low",28,"pull-back reveal to the four terraces and the cloud, medium","pull-back","medium","wind builds, one held note",["VO29","VO30"],[(4,8,"5.438.684 €")],"cut"),
("S19",136,149,"EuroLeague hillside, 15 terraces","the cloud rains equally on fifteen terraces","15 equal drops land one by one","EWS","high",24,"pan across the fifteen terraces, slow","pan","slow","15 drops in a rising pattern, bed drops away",["VO31","VO32","VO33"],[(4,9,"15 × 362.579 €")],"cut"),
("S20",149,160,"EuroLeague hillside, a dry terrace","a cracked dry terrace below the floor line; a drawn bucket waters its own plants","the bucket pours into the dry terrace","CU","eye",50,"dolly out from the cracks, slow","dolly-out","slow","dry scrape, then water",["VO34","VO35","VO36"],[],"wipe"),
("S21",160,169,"TFF hillside, plots","fenced plots on a warm-lit slope; fences rise one by one","the tallest fence rises first","WS","frontal",35,"truck right along the fences, medium","truck","medium","posts knocked in",["VO37","VO38"],[(0,2.5,"TFF")],"cut"),
("S22",169,176,"TFF hillside, the tallest fence","the tallest fence, engraved Galatasaray","dimension line measures it","MCU","low",50,"crane up the fence, slow","crane-up","slow","high wood knock",["VO39"],[(0,3,"Galatasaray 9.006.596.835 TL")],"cut"),
("S23",176,180.5,"TFF hillside, two fences","two shorter fences in turn","measure ticks down","MS","side",50,"pan left, medium","pan","medium","two lower knocks",["VO40","VO41"],[],"cut"),
("S24",180.5,185.5,"TFF hillside, the lowest fence","the lowest fence, engraved Alanyaspor","dimension line, short","CU","high",50,"tilt down to the fence top, slow","tilt","slow","low knock",["VO42"],[(0,4,"Alanyaspor 571.608.883 TL")],"cut"),
("S25",185.5,191,"TFF hillside, plots","the fence heights set by each plot's own inflow and outflow channels","channels in and out of each plot glow","WS","high",28,"crane down over the plots, medium","crane-down","medium","water in, water out",["VO43"],[],"cut"),
("S26",191,199,"TFF hillside, a gate","a small gate in a fence swings open, the fence grows a little","the gate opens; the fence rises one notch","ECU","eye",85,"focus pull from latch to fence, slow","rack-focus","slow","latch click",["VO44","VO45"],[],"wipe"),
("S27",199,207,"three hillsides","the three hillsides side by side; one pour reaches all three","water lands three ways","EWS","frontal",24,"pull-back reveal to the full diorama, slow","pull-back","slow","marimba, one note per hillside",["VO46","VO47"],[(4.5,8,"Oran · Vergi · Çit")],"cut"),
("S28",207,214,"summit","the first sluice from S01 closes; the clapper tips a last time","the sluice closes","CU","eye",50,"locked-off hold, on the sluice","static","slow","last tok, 1 s silence",[],[],"cut"),
]
VT = {k: None for k in VO}
times = {m[0]: m[1].strip() for m in re.findall(r'^\| (VO\d+b?) \| ([^|]+)\|', S, re.M)}
def sec(t):
    m, s = t.split(':'); return int(m) * 60 + float(s)
shots = []
for (i, a, b, loc, d, act, size, ang, lens, line, typ, spd, snd, vos, txt, tr) in R:
    shots.append({
        "id": i, "start": round(a * FPS), "end": round(b * FPS), "location": loc, "description": d, "action": act,
        "reads": [{"t": [0.0, round(b - a, 2)], "read": act}],
        "camera": {"size": size, "angle": ang, "lens_mm": lens,
                   "move": {"line": f"{line.split(',')[0]}, {b-a:g} s, {spd} ease-in-out, {(line.split(',',1)[1].strip() if ',' in line else 'on the subject')}", "type": typ, "speed": spd, "moving_at_start": True}},
        "hook": "motion from frame 1: the sluice lifts and water bursts" if i == "S01" else "",
        "action_from_frame_1": True, "sound": snd, "transition": tr, "status": "planned", **({"motif": True} if i in ("S01","S28") else {}),
        "vo": [{"id": v, "at": round(sec(times[v]) - a, 2), "text": VO[v]} for v in vos],
        "text_on_screen": [{"t": [t0, t1], "text": t} for t0, t1, t in txt],
    })
film = {"title": "Teraslar (Sözleşmenin Anatomisi)", "version": 1, "fps": FPS, "width": 1920, "height": 1080,
        "duration_frames": 214 * FPS, "seed": 5051, "look": "custom: Kesit Çizimi", "shots": shots}
json.dump(film, open('shots.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(shots), "shots,", film["duration_frames"], "frames")
