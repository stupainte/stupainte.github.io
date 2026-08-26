"""
Hämtar tävlingskalendern från Tournaments Online (resultat.ondata.se), det
publika gränssnittet till TT-Coordinator.

Systemet används fortfarande av många föreningar för tävlingar på lägre nivå
och innehåller därför nästan inga av de tävlingar som ligger i STUPA — vid
kontroll i augusti 2026 var överlappet noll. De två källorna kompletterar
alltså varandra i stället för att konkurrera.

Vad ondata ger som STUPA saknar:  stad, arena, land, djuplänk till tävlingen.
Vad STUPA ger som ondata saknar:  anmälningsstatus och tävlingsnivå.

Sidan är server-renderad HTML utan JavaScript — ett enda anrop mot
?viewAll=1 ger hela kalendern, drygt 1300 tävlingar från 2012 och framåt.

Två detaljer att känna till:

  * Teckenkodningen är windows-1252, inte UTF-8. Utan explicit avkodning blir
    alla svenska tecken förstörda ("Brogårdshallen" → "Brog?rdshallen").
  * Tävlingsnamnen är inte länkar. Adressen ligger i radens onclick-attribut
    som document.location='/001370'. Rader med class='inactive' saknar den
    helt — en tävling får sin sida först när den lagts upp i resultat-
    systemet, vilket sker några månader före spel.
"""

from __future__ import annotations

import re
from html import unescape

import requests

BAS = "https://resultat.ondata.se"
KALLA = "TT-Coordinator"

TIDGRANS = 45

# <tr class='active' onclick="document.location='/001370';">
RAD = re.compile(r"<tr([^>]*)>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
ID_UR_ONCLICK = re.compile(r"document\.location\s*=\s*'/(\d+)'")
DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TAGGAR = re.compile(r"<[^>]+>")


def _text(cell: str) -> str:
    return unescape(TAGGAR.sub("", cell)).strip()


def hamta(session: requests.Session | None = None) -> list[dict]:
    """Returnerar hela tävlingskalendern som en lista av dictar."""
    s = session or requests.Session()
    r = s.get(f"{BAS}/?viewAll=1", timeout=TIDGRANS)
    r.raise_for_status()

    # Servern anger ISO-8859-1 men sidan är i praktiken windows-1252.
    # Skillnaden spelar roll för tecken som citattecken och bindestreck.
    r.encoding = "windows-1252"

    ut: list[dict] = []
    for attribut, innehall in RAD.findall(r.text):
        celler = CELL.findall(innehall)
        if len(celler) != 6:
            continue

        namn, start, slut, ort, arena, land = (_text(c) for c in celler)
        if not DATUM.match(start):
            continue

        m = ID_UR_ONCLICK.search(attribut)
        tavlings_id = m.group(1) if m else None

        ut.append({
            "namn": namn,
            "datum": start,
            "slutdatum": slut if DATUM.match(slut) else start,
            "ort": ort,
            "arena": arena,
            "land": land,
            "niva": "",          # finns inte i ondata
            "status": "",        # anmälningsstatus finns inte i ondata
            "kalla": KALLA,
            # Tävlingar långt fram i tiden har ännu ingen sida i
            # resultatsystemet och saknar därför länk.
            "lank": f"{BAS}/{tavlings_id}/" if tavlings_id else None,
        })

    ut.sort(key=lambda x: x["datum"])
    return ut


if __name__ == "__main__":
    t = hamta()
    print(f"{len(t)} tävlingar, {t[0]['datum']} – {t[-1]['datum']}")
    print(f"{sum(1 for x in t if x['lank'])} med länk")
    for x in t[-3:]:
        print(" ", x["datum"], x["namn"], "|", x["ort"], "|", x["lank"])
