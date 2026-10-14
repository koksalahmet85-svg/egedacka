"""Tahsilat defteri sezon analizi (saf fonksiyonlar; girdi: ledger satırları).

İki sezonu karşılaştırırken tam sezon toplamları yanıltıcıdır (biri 13 ay, diğeri
2,5 ay olabilir). Bu yüzden asıl kıyas "hizalanmış pencere" üzerinden yapılır:
hedef sezonun kapsadığı takvim aylarının aynısı, son ayda da aynı güne kadar
(ör. 1 Ağu–13 Eki 2026 ↔ 1 Ağu–13 Eki 2025).
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

SEASON_KINDS = ("SEASON_UPFRONT", "SEASON_INSTALLMENT")
MONTH_KINDS = ("MONTHLY", "MULTI_MONTH", "PARTIAL")


@dataclass(frozen=True)
class Row:
    sheet_month: date
    paid_on: date
    player_key: str
    group: str
    kind: str
    covered_months: tuple[date, ...]
    scholarship: bool
    amount: float
    dues_amount: float
    textile_amount: float
    channel: str
    cancelled: bool = False


def _pct(a: float, b: float) -> float | None:
    return None if not b else a / b


def _growth(new: float, old: float) -> float | None:
    return None if not old else new / old - 1


def summarize(rows: Iterable[Row]) -> dict[str, Any]:
    rows = [r for r in rows if not r.cancelled]
    total = sum(r.amount for r in rows)
    dues = sum(r.dues_amount for r in rows if r.kind not in ("EVENT",))
    textile = sum(r.textile_amount for r in rows)
    event = sum(r.amount for r in rows if r.kind == "EVENT")

    by_kind: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "rows": 0})
    by_group: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "dues": 0.0, "payers": set()})
    by_channel: Counter = Counter()
    by_month: dict[date, dict] = defaultdict(lambda: {"amount": 0.0, "dues": 0.0, "rows": 0, "payers": set()})
    for r in rows:
        by_kind[r.kind]["amount"] += r.amount
        by_kind[r.kind]["rows"] += 1
        g = by_group[r.group]
        g["amount"] += r.amount
        g["dues"] += r.dues_amount
        g["payers"].add(r.player_key)
        by_channel[r.channel] += r.amount
        m = by_month[r.sheet_month]
        m["amount"] += r.amount
        m["dues"] += r.dues_amount
        m["rows"] += 1
        m["payers"].add(r.player_key)

    payers = {r.player_key for r in rows if r.kind != "EVENT"}
    season_payers = {r.player_key for r in rows if r.kind in SEASON_KINDS}
    season_amount = sum(r.dues_amount for r in rows if r.kind in SEASON_KINDS)

    return {
        "total": total,
        "dues": dues,
        "textile": textile,
        "event": event,
        "rows": len(rows),
        "payers": len(payers),
        "season_plan": {
            "payers": len(season_payers),
            "amount": season_amount,
            "share_of_dues": _pct(season_amount, dues),
            "upfront_payers": len({r.player_key for r in rows if r.kind == "SEASON_UPFRONT"}),
            "upfront_amount": sum(r.dues_amount for r in rows if r.kind == "SEASON_UPFRONT"),
        },
        "by_kind": {k: v for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1]["amount"])},
        "by_group": {k: {"amount": v["amount"], "dues": v["dues"], "payers": len(v["payers"])}
                     for k, v in sorted(by_group.items(), key=lambda kv: -kv[1]["amount"])},
        "by_channel": {k: {"amount": v, "share": _pct(v, total)} for k, v in by_channel.most_common()},
        "by_month": [{"month": m.isoformat()[:7], "amount": v["amount"], "dues": v["dues"], "rows": v["rows"],
                      "payers": len(v["payers"])} for m, v in sorted(by_month.items())],
        "price_ladder": price_ladder(rows),
        "timeliness": timeliness(rows),
    }


def price_ladder(rows: Iterable[Row]) -> list[dict]:
    """Aylık aidatın fiili fiyatı: tek aylık, bursuz ödemelerin modu (en sık tutar).
    Liste fiyatı yoksa defterden fiyat geçmişini çıkarmanın en sağlam yolu."""
    buckets: dict[tuple[str, date], list[float]] = defaultdict(list)
    for r in rows:
        if r.kind == "MONTHLY" and not r.scholarship and len(r.covered_months) == 1 and r.textile_amount == 0:
            buckets[(r.group, r.covered_months[0])].append(r.dues_amount)
    out = []
    for (group, month), vals in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if len(vals) < 5:  # küçük örneklemde mod anlamsız
            continue
        mode, n = Counter(vals).most_common(1)[0]
        out.append({"group": group, "month": month.isoformat()[:7], "price": mode, "share_at_price": n / len(vals),
                    "n": len(vals), "median": statistics.median(vals)})
    return out


def timeliness(rows: Iterable[Row]) -> dict[str, Any]:
    """Tek aylık aidatlar için ödeme zamanı. Kapsanan ayın 10'una kadar = zamanında."""
    early = on_time = late_in_month = after_month = 0
    days_late: list[int] = []
    for r in rows:
        if r.kind != "MONTHLY" or len(r.covered_months) != 1:
            continue
        cm = r.covered_months[0]
        if r.paid_on < cm:
            early += 1
        elif r.paid_on.year == cm.year and r.paid_on.month == cm.month:
            if r.paid_on.day <= 10:
                on_time += 1
            else:
                late_in_month += 1
        else:
            after_month += 1
            days_late.append((r.paid_on - cm).days)
    n = early + on_time + late_in_month + after_month
    return {
        "n": n,
        "advance": _pct(early, n),
        "by_10th": _pct(on_time, n),
        "late_same_month": _pct(late_in_month, n),
        "after_month_end": _pct(after_month, n),
        "median_days_after_month_start_when_late": statistics.median(days_late) if days_late else None,
    }


def aligned_window(base: list[Row], target: list[Row],
                   season_only_months: frozenset[date] = frozenset()) -> tuple[list[Row], list[Row], dict]:
    """Hedefin takvim aylarını ve son aydaki son gününü baz sezona uygular.
    season_only_months: hedefe yalnız sezonluk ödemesi taşınmış aylar (ekonomik mod) —
    bazda da o ayların yalnız sezonluk satırları alınır, simetri korunur."""
    tgt = [r for r in target if not r.cancelled]
    if not tgt:
        return [], [], {}
    months = sorted({r.sheet_month for r in tgt})
    last = months[-1]
    cutoff_day = max(r.paid_on.day for r in tgt if r.sheet_month == last and r.paid_on.month == last.month) \
        if any(r.sheet_month == last and r.paid_on.month == last.month for r in tgt) else 31
    moy = {(m.month) for m in months}
    b = [r for r in base if not r.cancelled and r.sheet_month.month in moy
         and not (r.sheet_month.month == last.month and r.paid_on.month == last.month and r.paid_on.day > cutoff_day)]
    # Baz sezonda aynı takvim ayından birden fazla varsa (13 aylık sezon), hedefe 12 ay önceki eşleşir.
    b = [r for r in b if any(_months_between(t, r.sheet_month) == 12 for t in months)]
    shifted = {date(m.year - 1, m.month, 1) for m in season_only_months}
    b = [r for r in b if r.sheet_month not in shifted or r.kind in SEASON_KINDS]
    return b, tgt, {"months": [m.isoformat()[:7] for m in months], "last_month_cutoff_day": cutoff_day,
                    "season_only_months": sorted(m.isoformat()[:7] for m in season_only_months)}


def _prev_month(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def season_rows(rows: Iterable[Row], start: date, end: date, mode: str = "economic"
                ) -> tuple[list[Row], frozenset[date]]:
    """Bir sezonun satırları. `rows` sezon başından 1 ay önce başlayarak verilmelidir.

    cash: defter sayfası sezon aralığındaysa sezona aittir.
    economic: sezonluk plan (peşin/taksit) ödemesi sezon başından önceki ayda alındıysa
    (erken kayıt: Temmuz) BU sezona; sezonun son ayında alındıysa GELECEK sezona aittir.
    Sezon öncesi ayın aylık aidatları önceki sezonundur ve alınmaz.
    Dönüş: (satırlar, yalnız sezonluk satırı taşınmış aylar)."""
    first, last, prev = date(start.year, start.month, 1), date(end.year, end.month, 1), _prev_month(start)
    rows = list(rows)
    if mode == "cash":
        return [r for r in rows if first <= r.sheet_month <= last], frozenset()
    keep = [r for r in rows if first <= r.sheet_month <= last
            and not (r.sheet_month == last and r.kind in SEASON_KINDS)]
    carried = [r for r in rows if r.sheet_month == prev and r.kind in SEASON_KINDS]
    return carried + keep, frozenset({prev} if carried else ())


def _months_between(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + a.month - b.month


def coverage_months(season_end: date, months: int = 12) -> list[date]:
    """Sezonluk planın kapsadığı aylar: sezon bitişinden geriye `months` ay
    (2026-2027 → Ağu 2026 … Tem 2027)."""
    last = date(season_end.year, season_end.month, 1)
    out = []
    for i in range(months - 1, -1, -1):
        y, m = divmod(last.year * 12 + last.month - 1 - i, 12)
        out.append(date(y, m + 1, 1))
    return out


def _ladders(rows: list[Row]) -> dict[str, dict[date, float]]:
    ladder: dict[str, dict[date, float]] = defaultdict(dict)
    for p in price_ladder(rows):
        y, m = map(int, p["month"].split("-"))
        ladder[p["group"]][date(y, m, 1)] = p["price"]
    return ladder


def _monthly_path(prices: dict[date, float], coverage: list[date], hike_from: date | None = None,
                  hike_pct: float = 0.0) -> dict[str, float]:
    """12 ayı aylık ödemenin toplamı. Merdivende olmayan (gelecek) aylar son bilinen fiyatla
    doldurulur; `hike_from` ve sonrasındaki gelecek aylara `hike_pct` zam uygulanır.

    pre: zam öncesi tahmini aylar, post_base: zam uygulanacak aylar (zamsız fiyatla)."""
    known = sorted(prices)
    known_sum = pre = post_base = 0.0
    projected, last = 0, None
    for m in coverage:
        if m in prices:
            last = prices[m]
            known_sum += last
            continue
        projected += 1
        if last is None:  # kapsamın başı merdivenden önceyse ilk bilinen fiyat
            last = prices[known[0]]
        if hike_from is None or m >= hike_from:
            post_base += last
        else:
            pre += last
    return {"known": known_sum, "pre": pre, "post_base": post_base, "projected": projected,
            "path": known_sum + pre + post_base * (1 + hike_pct)}


def _breakeven(price: float, mp: dict[str, float]) -> float | None:
    """Zam uygulanacak aylarda aylık aidata ne kadar zam gelirse peşin aylıkla başabaş olur?"""
    return (price - mp["known"] - mp["pre"]) / mp["post_base"] - 1 if mp["post_base"] else None


def plan_tiers(rows: Iterable[Row], tiers: list[dict], coverage: list[date], hike_from: date | None = None,
               hike_pct: float = 0.0) -> list[dict]:
    """Tanımlı sezonluk plan kademeleri (erken kayıt / standart / geç) için gerçekleşme.

    Oyuncunun sezonluk toplamı (peşin + taksitler) bir kademe fiyatına ±%1 yakınsa o
    kademeden alınmış sayılır; taksitli plan da aynı ürün olduğundan dahildir. Kademede
    `valid_until` varsa, o tarihten sonra başlayan ödemeler "son tarih sonrası" sayılır
    (erken fiyatın süresi dolduktan sonra verilmesi = gelir kaçağı)."""
    rows = [r for r in rows if not r.cancelled]
    ladder = _ladders(rows)
    plans: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r.kind not in SEASON_KINDS or r.scholarship:
            continue
        p = plans.setdefault((r.group, r.player_key), {"total": 0.0, "first": r.paid_on, "upfront": False})
        p["total"] += r.dues_amount
        p["first"] = min(p["first"], r.paid_on)
        p["upfront"] |= r.kind == "SEASON_UPFRONT"
    out = []
    for group in sorted({t["group"] for t in tiers}):
        g_tiers = sorted((t for t in tiers if t["group"] == group), key=lambda t: t["price"])
        g_plans = [v for (g, _), v in plans.items() if g == group]
        mp = _monthly_path(ladder[group], coverage, hike_from, hike_pct) if ladder.get(group) else \
            {"known": 0.0, "pre": 0.0, "post_base": 0.0, "projected": 0, "path": 0.0}
        path, projected = mp["path"], mp["projected"]
        matched_ids: set[int] = set()
        rows_out = []
        for t in g_tiers:
            hits = [(i, v) for i, v in enumerate(g_plans) if abs(v["total"] - t["price"]) <= t["price"] * 0.01]
            matched_ids |= {i for i, _ in hits}
            dates = sorted(v["first"] for _, v in hits)
            vu = t.get("valid_until")
            rows_out.append({
                "tier": t["tier"], "label": t.get("label") or t["tier"], "price": t["price"],
                "valid_until": vu.isoformat() if vu else None,
                "players": len(hits), "upfront": sum(v["upfront"] for _, v in hits),
                "installment": sum(not v["upfront"] for _, v in hits),
                "first_paid": dates[0].isoformat() if dates else None,
                "last_paid": dates[-1].isoformat() if dates else None,
                "after_deadline": sum(d > vu for d in dates) if vu else None,
                "discount_vs_monthly": 1 - t["price"] / path if path else None,
                "breakeven_hike": _breakeven(t["price"], mp),
            })
        others = [v for i, v in enumerate(g_plans) if i not in matched_ids]
        # Yalnız taksit ödemiş ve toplamı en yüksek kademenin altında kalan = taksiti sürüyor.
        top = g_tiers[-1]["price"] if g_tiers else 0
        in_progress = [v for v in others if not v["upfront"] and v["total"] < top * 0.99]
        other_price = [v for v in others if v not in in_progress]
        prices = Counter(round(v["total"], -3) for v in other_price)
        out.append({"group": group, "monthly_path": path, "projected_months": projected, "tiers": rows_out,
                    "in_progress_players": len(in_progress),
                    "in_progress_amount": sum(v["total"] for v in in_progress),
                    "other_price_players": len(other_price),
                    "other_price_amount": sum(v["total"] for v in other_price),
                    "other_price_points": [{"price": p, "n": n} for p, n in prices.most_common(5)]})
    return out


def upfront_vs_monthly(rows: Iterable[Row], coverage: list[date], hike_from: date | None = None,
                       hike_pct: float = 0.0) -> list[dict]:
    """Sezonluk peşin fiyatı ↔ aynı 12 ayı aylık ödemenin toplamı.

    Aylık yol, defterden çıkan fiili fiyat merdivenidir (price_ladder). Henüz yaşanmamış
    aylar son bilinen fiyatla doldurulur (= sezon içinde zam yapılmazsa) ve `projected_months`
    ile işaretlenir. Peşin ödemenin velinin gözündeki değeri bu farktır."""
    rows = [r for r in rows if not r.cancelled]
    out = []
    for group, prices in sorted(_ladders(rows).items()):
        ups = [r.dues_amount for r in rows
               if r.group == group and r.kind == "SEASON_UPFRONT" and not r.scholarship]
        if len(ups) < 5:
            continue
        mp = _monthly_path(prices, coverage, hike_from, hike_pct)
        path, projected = mp["path"], mp["projected"]
        total_n = len(ups)
        # n<3 fiyat noktası kardeş/burs/özel anlaşma gürültüsüdür; plan fiyatı sayılmaz.
        points = [(pr, n) for pr, n in Counter(ups).most_common(3) if n >= 3]
        out.append({
            "group": group,
            "monthly_path": path,
            "projected_months": projected,
            "price_points": [{
                "price": pr, "n": n, "share": n / total_n,
                "discount_vs_monthly": 1 - pr / path if path else None,
                # Kalan aylarda aylık aidata ne kadar zam gelirse peşin aylıkla başabaş olur?
                "breakeven_hike": _breakeven(pr, mp),
            } for pr, n in points],
        })
    return out


def compare(base_name: str, base: list[Row], target_name: str, target: list[Row],
            mode: str = "economic", base_coverage: list[date] | None = None,
            target_coverage: list[date] | None = None, base_tiers: list[dict] | None = None,
            target_tiers: list[dict] | None = None, target_carried: frozenset[date] = frozenset(),
            hike_from: date | None = None, hike_pct: float = 0.0) -> dict[str, Any]:
    """Satırlar season_rows() ile hazırlanmış olmalıdır (mode orada uygulanır).
    hike_from/hike_pct: hedef sezonda henüz yaşanmamış aylara uygulanacak zam senaryosu
    (ör. Ocak'tan itibaren enflasyon oranında artış)."""
    season_only = target_carried
    b_all, t_all = summarize(base), summarize(target)
    b_win, t_win, window = aligned_window(base, target, season_only)
    bw, tw = summarize(b_win), summarize(t_win)

    def delta(key_path: tuple[str, ...]) -> dict:
        x, y = bw, tw
        for k in key_path:
            x, y = x.get(k, {}) if isinstance(x, dict) else 0, y.get(k, {}) if isinstance(y, dict) else 0
        x = x if isinstance(x, (int, float)) else 0
        y = y if isinstance(y, (int, float)) else 0
        return {"base": x, "target": y, "growth": _growth(y, x)}

    groups = sorted(set(bw["by_group"]) | set(tw["by_group"]))
    kinds = sorted(set(bw["by_kind"]) | set(tw["by_kind"]))

    # Oyuncu tutma: baz sezonun SON 3 ayında aidat ödeyenlerden kaçı hedef sezonda ödedi?
    b_valid = [r for r in base if not r.cancelled and r.kind != "EVENT"]
    t_payers = {r.player_key for r in target if not r.cancelled and r.kind != "EVENT"}
    b_months = sorted({r.sheet_month for r in b_valid})
    tail = set(b_months[-3:])
    recent = {r.player_key for r in b_valid if r.sheet_month in tail}
    b_payers = {r.player_key for r in b_valid}
    retained = recent & t_payers

    # Fiyat değişimi: aynı grup, takvim ayı 12 ay arayla
    b_price = {(p["group"], p["month"]): p["price"] for p in b_all["price_ladder"]}
    price_changes = []
    for p in t_all["price_ladder"]:
        y, m = map(int, p["month"].split("-"))
        prev = b_price.get((p["group"], f"{y - 1:04d}-{m:02d}"))
        if prev:
            price_changes.append({"group": p["group"], "month": p["month"], "base_price": prev,
                                  "target_price": p["price"], "change": _growth(p["price"], prev)})

    return {
        "mode": mode,
        "base": {"name": base_name, **b_all},
        "target": {"name": target_name, **t_all},
        "aligned": {
            "window": window,
            "total": delta(("total",)),
            "dues": delta(("dues",)),
            "textile": delta(("textile",)),
            "event": delta(("event",)),
            "payers": delta(("payers",)),
            "season_plan_amount": delta(("season_plan", "amount")),
            "season_plan_payers": delta(("season_plan", "payers")),
            "by_group": {g: {"base": bw["by_group"].get(g, {}).get("amount", 0),
                             "target": tw["by_group"].get(g, {}).get("amount", 0),
                             "growth": _growth(tw["by_group"].get(g, {}).get("amount", 0),
                                               bw["by_group"].get(g, {}).get("amount", 0)),
                             "payers_base": bw["by_group"].get(g, {}).get("payers", 0),
                             "payers_target": tw["by_group"].get(g, {}).get("payers", 0)} for g in groups},
            "by_kind": {k: {"base": bw["by_kind"].get(k, {}).get("amount", 0),
                            "target": tw["by_kind"].get(k, {}).get("amount", 0)} for k in kinds},
            "by_month": {"base": bw["by_month"], "target": tw["by_month"]},
            "timeliness": {"base": bw["timeliness"], "target": tw["timeliness"]},
        },
        "retention": {
            "base_payers": len(b_payers),
            "base_recent_payers": len(recent),
            "recent_retained": len(retained),
            "recent_retention_rate": _pct(len(retained), len(recent)),
            "target_payers": len(t_payers),
            "target_new": len(t_payers - b_payers),
            "recent_not_yet_returned": len(recent - t_payers),
        },
        "price_changes": price_changes,
        # Peşin ↔ aylık (ekonomik bölme sonrası: Temmuz'da alınan peşinler hedef sezonun planıdır,
        # Temmuz aylık aidatı ise baz sezonun fiyat merdiveninde kalır).
        "season_plan_value": {
            "base": upfront_vs_monthly(base, base_coverage) if base_coverage else [],
            "target": upfront_vs_monthly(target, target_coverage, hike_from, hike_pct) if target_coverage else [],
        },
        "plan_tiers": {
            "base": plan_tiers(base, base_tiers, base_coverage) if base_tiers and base_coverage else [],
            "target": plan_tiers(target, target_tiers, target_coverage, hike_from, hike_pct)
            if target_tiers and target_coverage else [],
        },
        "hike_scenario": {"from": hike_from.isoformat() if hike_from else None, "pct": hike_pct},
    }
