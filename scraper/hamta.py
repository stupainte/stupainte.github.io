#!/usr/bin/env python3
"""
Hämtar seriespel och turneringar från STUPA:s JSON-API och skriver
klubbcentrerade JSON-filer som den statiska frontenden läser.

    python3 hamta.py --ut data

Inga beroenden utöver requests. Ingen webbläsare, ingen Playwright.

Bakgrund
--------
STUPA:s publika webb är en klientrenderad SPA, men den hämtar all sin data
från ett öppet JSON-API på testbackend.stupaevents.com (namnet till trots
är det produktionsbackenden — den driver den publika sajten).

API:et kräver bara en `tenant`-header, ingen inloggning. Hela
API-specifikationen finns på https://testbackend.stupaevents.com/openapi.json

Datakedjan:

    get_events            → alla evenemang (event_type L = serier, T = turneringar)
      get_events_categories → divisioner inom ett seriespel
      get_stages            → gruppspelsomgångar per division
        get_group_matches     → matcher + tabell (group_matrix)

Varje lag i svaret bär sin kanoniska klubb i `selected_parents`
(parent_role == "Club"). Därför behövs ingen gissningsbaserad
normalisering av föreningsnamn.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import time

import requests

import ondata

BAS = "https://testbackend.stupaevents.com/ott/v1"
TENANT = "sbtf"
WEBB = "https://sbtfeventsott.stupaevents.com"

TIDGRANS = 30
FORSOK = 3
BACKOFF_SEKUNDER = 4  # mellan omförsök, fördubblas för varje nytt försök


# --------------------------------------------------------------------------
# API-klient
# --------------------------------------------------------------------------

class Stupa:
    def __init__(self, tenant: str = TENANT) -> None:
        self.s = requests.Session()
        self.s.headers.update({
            "tenant": tenant,
            "accept": "application/json",
            "user-agent": "stupainte/1.0 (+https://github.com/stupainte)",
        })

    def get(self, sokvag: str, **q: Any) -> Any:
        url = f"{BAS}/{sokvag}"
        for forsok in range(1, FORSOK + 1):
            try:
                r = self.s.get(url, params=q, timeout=TIDGRANS)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as fel:
                if forsok == FORSOK:
                    raise
                vantetid = BACKOFF_SEKUNDER * forsok
                print(f"  ! {sokvag} misslyckades ({fel}), försök {forsok}/{FORSOK}, "
                      f"väntar {vantetid}s", file=sys.stderr)
                time.sleep(vantetid)
        return None

    def data(self, sokvag: str, **q: Any) -> list[dict]:
        """Returnerar alltid en lista — API:et varierar mellan list och dict."""
        svar = self.get(sokvag, **q)
        if svar is None:
            return []
        d = svar.get("data", svar) if isinstance(svar, dict) else svar
        if isinstance(d, dict):
            return list(d.values())
        return d if isinstance(d, list) else []


# --------------------------------------------------------------------------
# Hjälpare
# --------------------------------------------------------------------------

def slugga(namn: str) -> str:
    """'Örbyhus Idrottsförening' → 'orbyhus-idrottsforening'"""
    t = namn.lower()
    t = t.replace("å", "a").replace("ä", "a").replace("ö", "o")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "okand"


# Ord som skiljer namnvarianter åt utan att ändra vilken förening som avses.
# "Spårvägens BTK" och "Spårvägens Bordtennisklubb" ska ge samma nyckel.
FYLLNADSORD = [
    "bordtennisklubben", "bordtennisklubb", "bordtennisförening", "bordtennis",
    "idrottsförening", "idrottssällskap", "idrottsklubb", "sportklubb",
    "pingisklubb", "pingis", "allmänna", "btk", "btf", "aif", "pk", "sk",
    "if", "ik", "bt", "klubb",
]


def namnyckel(namn: str) -> str:
    t = (namn or "").lower()
    for ord_ in FYLLNADSORD:
        t = re.sub(r"\b" + ord_ + r"\b", " ", t)
    t = t.replace("å", "a").replace("ä", "a").replace("ö", "o")
    return re.sub(r"[^a-z0-9]", "", t)


def hamta_klubbregister(api: Stupa) -> dict[str, str]:
    """
    STUPA för ett eget klubbregister. Det är auktoritativt och används för
    att slå ihop namnvarianter.

    Behovet är litet men verkligt: enstaka lag är taggade med kortnamn i
    stället för föreningens registrerade namn. Ett lag i Pingisligan dam bär
    "Spårvägens BTK" medan alla andra Spårvägslag bär "Spårvägens
    Bordtennisklubb" — utan sammanslagning blir det två klubbar i listan.

    Nyckeln måste vara entydig för att användas. "Spårvägens Veteran
    Bordtennisklubb" får en egen nyckel och slås alltså inte ihop.
    """
    register: dict[str, list[str]] = defaultdict(list)
    for blk in api.data("get_role_parents", role_id=590):
        if blk.get("parent_role_name") != "Club":
            continue
        for u in blk.get("parent_user_roles") or []:
            namn = u.get("parent_role_linked_field_value")
            if namn:
                register[namnyckel(namn)].append(namn)

    entydiga = {k: v[0] for k, v in register.items() if len(v) == 1 and k}
    print(f"  klubbregister: {sum(len(v) for v in register.values())} föreningar, "
          f"{len(entydiga)} entydiga namnnycklar")
    return entydiga


KLUBBREGISTER: dict[str, str] = {}


def klubb_for(deltagare: dict) -> str | None:
    """Plockar ut kanoniskt klubbnamn ur selected_parents."""
    for f in deltagare.get("selected_parents") or []:
        if f.get("parent_role") == "Club":
            namn = f.get("parent_name")
            if not namn:
                return None
            return KLUBBREGISTER.get(namnyckel(namn), namn)
    return None


def dela_tid(iso: str | None) -> tuple[str, str]:
    """'2026-09-20T10:00:00' → ('2026-09-20', '10:00')"""
    if not iso:
        return "", ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d.strftime("%Y-%m-%d"), d.strftime("%H:%M")
    except ValueError:
        return iso[:10], iso[11:16]


def nu() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def idag() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# Hämtning
# --------------------------------------------------------------------------

# Evenemang som är test- eller utvecklingsdata. STUPA:s publika lista blandar
# dem med skarpa serier, så de måste bort innan publicering.
#
# Tre kriterier, alla nödvändiga:
#
#  1. published — opublicerade evenemang syns inte på STUPA:s egen sajt heller.
#  2. event_level != "Testtävling" — STUPA:s egen markering.
#  3. namnet innehåller inte "test" som eget ord.
#
# Punkt 2 är lätt att avfärda eftersom namnen kan se trovärdiga ut.
# "Bästkustens BTF 26/27" låter som ett distrikt, men SBTF har bara 15
# specialdistriktsförbund och Bästkusten är inte ett av dem. Lagen i den
# serien heter "Bärke Test", "Carlstad Test", "Lag A", "Lag B", och
# klubbarna är hopplockade från sju orelaterade distrikt. Lita på flaggan.
#
# Ordgränsen i mönstret träffar "Askims test tävling" men lämnar
# "Adventstesttävling" ifred.
TESTMONSTER = re.compile(r"\btest\b|malin gör", re.IGNORECASE)

# SBTF:s 15 specialdistriktsförbund enligt sbtf.se. Används för att
# kontrollera att ett distriktsevenemang motsvarar ett verkligt distrikt.
SDF = [
    "Dalarnas", "Gotlands", "Göteborgs", "Hallands", "Nordvästra Götalands",
    "Nordöstra Svealands", "Norrlands", "Skånes", "Stockholms",
    "Sydöstra Götalands", "Södermanlands", "Värmlands", "Västmanlands",
    "Örebro läns", "Östergötlands",
]


def ar_riktigt(ev: dict) -> bool:
    if not ev.get("published"):
        return False
    if (ev.get("event_level") or "") == "Testtävling":
        return False
    return not TESTMONSTER.search(ev.get("name") or "")


def hamta_evenemang(api: Stupa) -> tuple[list[dict], list[dict]]:
    """Returnerar (serier, turneringar) med testdata bortfiltrerad."""
    alla = api.data("get_events", per_page=500, page_num=1)
    riktiga = [e for e in alla if ar_riktigt(e)]

    bort = len(alla) - len(riktiga)
    if bort:
        print(f"  filtrerade bort {bort} test-/utvecklingsevenemang")

    serier = [e for e in riktiga if e.get("event_type") == "L"]
    turneringar = [e for e in riktiga if e.get("event_type") == "T"]

    # Varning, inte filtrering: distriktsserier vars namn inte matchar något
    # av SBTF:s 15 SDF är misstänkta. Bättre att flagga än att tyst kasta.
    for e in serier:
        namn = e.get("name") or ""
        if (e.get("event_level") or "").startswith("Distrikt") \
                and not any(d in namn for d in SDF):
            print(f"  ? '{namn}' matchar inget känt distrikt — kontrollera",
                  file=sys.stderr)

    return serier, turneringar


def hamta_serie(api: Stupa, ev: dict) -> tuple[list[dict], list[dict]]:
    """
    Hämtar alla matcher och tabeller för ett seriespel (ett distrikt
    eller det nationella seriespelet).

    Returnerar (matcher, tabeller).
    """
    ev_id = ev["id"]
    ev_namn = ev.get("name", "")

    # Divisionsnamnet ligger inbäddat i varje stage:
    #   stage.event_category.category.category_description → "Division 4A"
    # get_events_categories returnerar bara toppnivåerna ("Division 4") och
    # duger därför inte — undergrupperna A/B/C saknas där.
    stages = api.data("get_stages", event_id=ev_id, per_page=200)

    matcher: list[dict] = []
    tabeller: list[dict] = []

    for st in stages:
        ec = st.get("event_category") or {}
        kat = ec.get("category") or {}
        division = (
            kat.get("category_description")     # "Division 4A"
            or kat.get("abbr")                  # "Div 4"
            or ev_namn
        )
        # Länken öppnar rätt EVENEMANG, men inte rätt division.
        #
        # Det går inte att djuplänka till en division. STUPA skriver om andra
        # URL-segmentet till evenemangets förvalda kategori oavsett vad man
        # anger — /events/435/1189 och /events/435/1193 landar båda på
        # /events/435/1186. Divisionen väljs via en rullgardinsmeny, alltså
        # klienttillstånd som aldrig hamnar i adressen.
        #
        # Den nakna adressen /events/435 duger inte heller, den ger
        # "No Records Found". Vi behåller därför den fullständiga formen så
        # att sidan i alla fall laddar korrekt, och låter frontenden berätta
        # vilken division användaren ska välja i menyn.
        kat_id = ec.get("category_id")
        djuplank = (f"{WEBB}/events/{ev_id}/{kat_id}/2/7/7" if kat_id
                    else f"{WEBB}/events/{ev_id}")

        grupper = api.data(
            "get_group_matches",
            stage_id=st["id"],
            view="standard",
            show_matrix=True,
            fetch_point_system=True,
            # Utan denna parameter saknas fältet "organiser" helt. Den syns
            # inte i OpenAPI-specens exempel utan bara i det anrop STUPA:s
            # egen matchlista gör.
            show_organiser_details=True,
        )

        for gr in grupper:
            serienamn = division
            if (gr.get("name") or "").strip() not in ("", "Group 1"):
                serienamn = f"{division} {gr['name']}"

            # ---- tabell ----
            rader = []
            for r in gr.get("group_matrix") or []:
                rader.append({
                    "placering": r.get("rank") or r.get("order"),
                    "lag": r.get("participant_name"),
                    "klubb": klubb_for(r),
                    "spelade": (r.get("matches_won") or 0) + (r.get("matches_lost") or 0),
                    "vunna": r.get("matches_won") or 0,
                    "oavgjorda": 0,
                    "forlorade": r.get("matches_lost") or 0,
                    "matchpoang": r.get("group_points") or 0,
                    "setdiff": f"{r.get('points_won') or 0}–{r.get('points_lost') or 0}",
                })
            if rader:
                rader.sort(key=lambda r: (r["placering"] is None,
                                          r["placering"] or 0, r["lag"] or ""))
                # Innan första omgången är placeringarna seedning, inte
                # ställning. Frontenden använder flaggan för att visa
                # deltagarlista i stället för tabell.
                tabeller.append({
                    "serie": serienamn,
                    "evenemang": ev_namn,
                    "stupa_url": djuplank,
                    "startad": any(r["spelade"] for r in rader),
                    "rader": rader,
                })

            # ---- matcher ----
            for m in gr.get("matches") or []:
                delt = m.get("participants") or []
                if len(delt) < 2:
                    continue
                datum, tid = dela_tid(m.get("start_time"))
                hemma, borta = delt[0], delt[1]
                lokal = (m.get("venue") or {}).get("name")

                # organiser är en lista med klubbnamn — en seriehelg kan
                # arrangeras av flera föreningar tillsammans.
                arr = m.get("organiser") or []
                if isinstance(arr, str):
                    arr = [arr]
                arr = [a for a in arr if a]

                post = {
                    "datum": datum,
                    "tid": tid,
                    "serie": serienamn,
                    "omgang": (m.get("round") or {}).get("name") or "",
                    "hemma": hemma.get("participant_name"),
                    "borta": borta.get("participant_name"),
                    "hemma_klubb": klubb_for(hemma),
                    "borta_klubb": klubb_for(borta),
                    "plats": lokal,
                    "arrangor": " / ".join(arr) or None,
                    "arrangorer": arr,
                    "stupa_url": djuplank,
                }
                # Obs: score_published duger INTE som markör för spelad match.
                # Det är en inställning på divisionsnivå och är True även för
                # matcher som ligger månader fram i tiden. Statusfältet och
                # förekomsten av en vinnare är det som faktiskt gäller.
                if m.get("status") == "COMPLETED" or m.get("winner"):
                    post["hemma_poang"] = hemma.get("match_points")
                    post["borta_poang"] = borta.get("match_points")
                matcher.append(post)

    return matcher, tabeller


STATUS_SV = {
    "Registration Open": "Anmälan öppen",
    "Registration Closed": "Anmälan stängd",
    "Upcoming": "Kommande",
    "Recent": "Nyligen spelad",
    "Cancelled": "Inställd",
}


def hamta_turneringar(api: Stupa, evenemang: Iterable[dict]) -> list[dict]:
    """
    Alla turneringar i STUPA, både spelade och kommande.

    STUPA har varken stad eller land för sina evenemang — venue-objektet
    innehåller bara ett lokalnamn, och det är ofta oanvändbart ("Hall 4",
    "A-Hallen"). De fälten lämnas därför tomma och fylls i stället av
    ondata där tävlingen finns i båda systemen.

    Länken behöver en category_id för att STUPA ska visa något alls — den
    nakna formen /events/428 ger "No Records Found". Ett extra anrop per
    turnering, vilket är billigare än det event_venues-anrop det ersätter.
    """
    ut = []
    for e in evenemang:
        datum = (e.get("event_start_date") or "")[:10]
        if not datum:
            continue
        if (e.get("event_status_description") or "") == "Cancelled":
            continue

        lank = f"{WEBB}/events/{e['id']}"
        try:
            kat = api.data("get_events_categories", event_id=e["id"], per_page=1)
            if kat and kat[0].get("category_id"):
                lank = f"{WEBB}/events/{e['id']}/{kat[0]['category_id']}/2/7/7"
        except Exception:                                   # noqa: BLE001
            pass

        ut.append({
            "namn": e.get("name"),
            "datum": datum,
            "slutdatum": (e.get("event_end_date") or "")[:10] or datum,
            "ort": "",
            "arena": "",
            "land": "",
            "niva": e.get("event_level") or "",
            "status": STATUS_SV.get(e.get("event_status_description") or "",
                                    e.get("event_status_description") or ""),
            "kalla": "STUPA",
            "lank": lank,
        })
    ut.sort(key=lambda x: x["datum"])
    return ut


def slasamman_turneringar(fran_stupa: list[dict],
                          fran_ondata: list[dict]) -> list[dict]:
    """
    Slår ihop de två tävlingskällorna.

    Vid kontroll i augusti 2026 var överlappet noll — TT-Coordinator används
    på lägre nivåer och STUPA på högre. Men systemen migrerar, så dubbletter
    kan uppstå. Nyckeln är startdatum plus ett normaliserat namn.

    Vid dubblett behålls STUPA-posten som grund (den har anmälningsstatus och
    nivå) och kompletteras med ondatas stad, arena och land.
    """
    def nyckel(t: dict) -> tuple[str, str]:
        n = (t["namn"] or "").lower()
        n = re.sub(r"\b(19|20)\d{2}\b", "", n)      # årtal i namnet
        return (t["datum"], re.sub(r"[^a-z0-9åäö]", "", n))

    per_nyckel: dict[tuple[str, str], dict] = {}
    for t in fran_stupa:
        per_nyckel[nyckel(t)] = dict(t)

    dubbletter = 0
    for t in fran_ondata:
        k = nyckel(t)
        if k in per_nyckel:
            dubbletter += 1
            befintlig = per_nyckel[k]
            for falt in ("ort", "arena", "land"):
                if not befintlig.get(falt):
                    befintlig[falt] = t.get(falt) or ""
            befintlig["kalla"] = "STUPA + TT-Coordinator"
        else:
            per_nyckel[k] = dict(t)

    if dubbletter:
        print(f"  {dubbletter} tävlingar fanns i båda källorna och slogs ihop")

    ut = sorted(per_nyckel.values(), key=lambda x: (x["datum"], x["namn"] or ""))
    return ut


def hinke(t: dict, dagens: str) -> str:
    """kommande | pagaende | passerad"""
    slut = t.get("slutdatum") or t["datum"]
    if slut < dagens:
        return "passerad"
    if t["datum"] <= dagens <= slut:
        return "pagaende"
    return "kommande"


# --------------------------------------------------------------------------
# Sammanställning per klubb
# --------------------------------------------------------------------------

def bygg(matcher: list[dict], tabeller: list[dict], turneringar: list[dict],
         sasong: str) -> tuple[dict, dict[str, dict]]:
    per_klubb: dict[str, dict] = defaultdict(
        lambda: {"lag": set(), "kommande": [], "resultat": [],
                 "arrangerar": [], "serier": set()}
    )

    for m in matcher:
        for sida in ("hemma", "borta"):
            klubb = m.get(f"{sida}_klubb")
            if not klubb:
                continue
            k = per_klubb[klubb]
            # Nyckeln måste innehålla serien. Samma lagnamn förekommer i
            # olika serier — "Spårvägens BTK" spelar både Pingisligan herr
            # och Pingisligan dam — och skulle annars skriva över varandra.
            k["lag"].add((m[sida], m["serie"]))
            k["serier"].add(m["serie"])
            (k["resultat"] if "hemma_poang" in m else k["kommande"]).append(m)

        # En arrangör är värd för hela seriehelgen, även matcher där inget
        # av de egna lagen spelar. De matcherna finns alltså inte i listorna
        # ovan och måste samlas separat.
        for klubb in m.get("arrangorer") or []:
            per_klubb[klubb]["arrangerar"].append(m)

    tabell_per_serie: dict[str, dict] = {t["serie"]: t for t in tabeller}
    dagens = idag()
    filer: dict[str, dict] = {}
    index_klubbar = []

    for klubb, d in sorted(per_klubb.items()):
        slug = slugga(klubb)

        kommande = sorted(
            (m for m in d["kommande"] if m["datum"] >= dagens),
            key=lambda m: (m["datum"], m["tid"]),
        )
        resultat = sorted(d["resultat"], key=lambda m: (m["datum"], m["tid"]))

        # Arrangörsvyn grupperas per speldag — det är så en klubb planerar
        # hallpass, funktionärer och domare.
        per_dag: dict[str, list[dict]] = defaultdict(list)
        for m in d["arrangerar"]:
            if m["datum"] >= dagens:
                per_dag[m["datum"]].append(m)

        arrangerar = []
        for datum in sorted(per_dag):
            rader = sorted(per_dag[datum], key=lambda m: (m["tid"], m["serie"]))
            arrangerar.append({
                "datum": datum,
                "platser": sorted({m["plats"] for m in rader if m["plats"]}),
                "serier": sorted({m["serie"] for m in rader}),
                "antal": len(rader),
                "matcher": rader,
            })

        filer[slug] = {
            "klubb": {"slug": slug, "namn": klubb},
            "sasong": sasong,
            "uppdaterad": nu(),
            "lag": [
                {"namn": namn, "serie": {"namn": serie}, "stupa_url": WEBB}
                for namn, serie in sorted(d["lag"])
            ],
            "kommande": kommande,
            "resultat": resultat,
            "arrangerar": arrangerar,
            "tabeller": [tabell_per_serie[s] for s in sorted(d["serier"])
                         if s in tabell_per_serie],
            # Turneringarna ligger inte här. De är rikstäckande och identiska
            # för alla klubbar — att duplicera 1300 tävlingar in i 177
            # klubbfiler hade gett tiotals megabyte. De ligger i stället i
            # data/turneringar.json och laddas när fliken öppnas.
        }
        index_klubbar.append({
            "slug": slug, "namn": klubb, "antal_lag": len(d["lag"]),
            "arrangerar_dagar": len(arrangerar),
        })

    index = {
        "genererad": nu(),
        "sasong": sasong,
        "klubbar": index_klubbar,
    }
    return index, filer


# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Hämtar bordtennisdata från STUPA.")
    p.add_argument("--ut", default="data", help="målkatalog (standard: data)")
    p.add_argument("--sasong", default="2026/2027")
    p.add_argument("--serie-id", type=int, action="append",
                   help="begränsa till angivna evenemangs-ID (kan upprepas)")
    p.add_argument("--hoppa-ondata", action="store_true",
                   help="hämta inte tävlingskalendern från TT-Coordinator")
    args = p.parse_args()

    api = Stupa()

    print("Hämtar klubbregister…")
    global KLUBBREGISTER
    KLUBBREGISTER = hamta_klubbregister(api)

    print("Hämtar evenemangslista…")
    serier, turneringar_ev = hamta_evenemang(api)
    if args.serie_id:
        serier = [e for e in serier if e["id"] in args.serie_id]
    print(f"  {len(serier)} seriespel, {len(turneringar_ev)} turneringar")

    alla_matcher: list[dict] = []
    alla_tabeller: list[dict] = []

    for ev in serier:
        print(f"Hämtar {ev.get('name')} (id {ev['id']})…")
        try:
            m, t = hamta_serie(api, ev)
        except Exception as fel:                      # noqa: BLE001
            print(f"  ! hoppar över: {fel}", file=sys.stderr)
            continue
        print(f"  {len(m)} matcher, {len(t)} tabeller")
        alla_matcher += m
        alla_tabeller += t

    print("Hämtar turneringar från STUPA…")
    fran_stupa = hamta_turneringar(api, turneringar_ev)
    print(f"  {len(fran_stupa)} turneringar")

    fran_ondata: list[dict] = []
    if not args.hoppa_ondata:
        print("Hämtar tävlingskalendern från TT-Coordinator…")
        try:
            fran_ondata = ondata.hamta()
            print(f"  {len(fran_ondata)} tävlingar, "
                  f"{sum(1 for x in fran_ondata if x['lank'])} med länk")
        except Exception as fel:                      # noqa: BLE001
            # Ondata är ett komplement, inte en förutsättning. Faller den
            # bort ska hämtningen ändå gå igenom med STUPA:s data.
            print(f"  ! ondata misslyckades, fortsätter utan: {fel}",
                  file=sys.stderr)

    turneringar = slasamman_turneringar(fran_stupa, fran_ondata)
    dagens = idag()
    for t in turneringar:
        t["hink"] = hinke(t, dagens)
    fordelning = Counter(t["hink"] for t in turneringar)
    print(f"  totalt {len(turneringar)} tävlingar: "
          + ", ".join(f"{v} {k}" for k, v in fordelning.most_common()))

    index, filer = bygg(alla_matcher, alla_tabeller, turneringar, args.sasong)

    ut = Path(args.ut)
    (ut / "klubb").mkdir(parents=True, exist_ok=True)
    (ut / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    # Delad fil — turneringarna är rikstäckande och laddas separat av
    # frontenden när tävlingsfliken öppnas.
    (ut / "turneringar.json").write_text(
        json.dumps({"genererad": nu(), "turneringar": turneringar},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    for slug, innehall in filer.items():
        (ut / "klubb" / f"{slug}.json").write_text(
            json.dumps(innehall, ensure_ascii=False, indent=1), encoding="utf-8")

    # Städa bort klubbfiler från tidigare körningar som inte längre finns i
    # indexet — annars ligger klubbar från borttagna evenemang kvar för alltid.
    if not args.serie_id:            # bara vid full hämtning
        for gammal in (ut / "klubb").glob("*.json"):
            if gammal.stem not in filer:
                gammal.unlink()
                print(f"  tog bort föräldrad klubbfil: {gammal.name}")

    print(f"\nKlart: {len(filer)} klubbar, {len(alla_matcher)} matcher → {ut}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
