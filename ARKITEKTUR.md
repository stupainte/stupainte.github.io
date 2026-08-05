# STUPA Inte — arkitektur

Ett klubbcentrerat skal ovanpå STUPA. Användaren väljer sin klubb och ser allt
aktuellt på en sida: kommande matcher, tabeller, spelade resultat och turneringar.

## Grundproblemet — och lösningen

STUPA (`*.stupaevents.com`) är en **klientrenderad SPA**. Ett anrop mot
`https://sbtfeventsott.stupaevents.com/events/435/1186/2/7/7` returnerar ett tomt
HTML-skal — allt innehåll hämtas av JavaScript efter att sidan laddats.
HTML-skrapning fungerar därför inte.

**Men det behövs inte.** SPA:n hämtar all sin data från ett öppet JSON-API, och
det API:et kan vi anropa direkt. Ingen Playwright, ingen webbläsare, inga
CSS-selektorer som går sönder när STUPA byter design.

Kvar finns dock ett hinder: **CORS**. API:et accepterar bara anrop från
`*.stupaevents.com`. Ett anrop från `stupainte.github.io` blockeras av
webbläsaren (verifierat: `Failed to fetch` från främmande origin, både med
`tenant` som header och som query-parameter). Frontenden kan alltså inte prata
med STUPA direkt — datan måste hämtas i förväg, serverside. Därav GitHub Actions.

## Vald arkitektur

```
  ┌────────────────────────┐
  │ GitHub Actions         │   schemalagt, t.ex. 04:00 varje natt
  │  scraper/hamta.py      │   + manuell körning via workflow_dispatch
  └───────────┬────────────┘
              │ läser
              ▼
  ┌────────────────────────┐
  │ STUPA                  │
  │ stupaevents.com        │
  └───────────┬────────────┘
              │ skriver JSON
              ▼
  ┌────────────────────────┐
  │ data/ i repot          │   git commit + push
  │  index.json            │
  │  klubb/<slug>.json     │
  └───────────┬────────────┘
              │ serveras statiskt
              ▼
  ┌────────────────────────┐
  │ stupainte.github.io    │   index.html, vanilla JS, ingen backend
  └────────────────────────┘
```

**Varför den här lösningen:**

- Gratis och driftfri. Ingen server, inget konto utöver GitHub.
- Snabb. Frontenden läser statiska JSON-filer från GitHub Pages CDN.
- Robust. Om STUPA ändrar sidstruktur går skrapningen sönder, men den senast
  fungerande datan ligger kvar i repot och sidan fortsätter fungera.
- Versionshanterad. Varje commit är en ögonblicksbild — man kan se exakt när och
  hur datan ändrades, vilket gör felsökning enkel.

**Priset:** datan är upp till ett dygn gammal. För seriespel är det oftast
oproblematiskt (matchprogram ändras sällan med kort varsel). Vill man ha färska
resultat under en pågående seriehelg kan man köra workflowet oftare, t.ex.
varje timme lördag–söndag.

## Datamodell

### `data/index.json`

Laddas först. Driver klubbsökningen.

```json
{
  "genererad": "2026-08-05T04:00:00Z",
  "sasong": "2026/2027",
  "klubbar": [
    { "slug": "hammarby", "namn": "Hammarby IF BTF", "antal_lag": 8 }
  ]
}
```

### `data/klubb/<slug>.json`

Laddas när användaren valt klubb. Innehåller allt klubben behöver.

```json
{
  "klubb":     { "slug": "hammarby", "namn": "Hammarby IF BTF" },
  "sasong":    "2026/2027",
  "uppdaterad": "2026-08-05T04:00:00Z",

  "lag": [
    {
      "namn": "Hammarby IF BTF 1",
      "serie": { "namn": "Division 2 Östra", "niva": "regional",
                 "region": "Nordöstra Svealand" },
      "stupa_url": "https://..."
    }
  ],

  "kommande": [
    {
      "datum": "2026-09-13", "tid": "13:00",
      "serie": "Division 2 Östra", "omgang": "Omgång 1",
      "hemma": "Hammarby IF BTF 1", "borta": "Spårvägens BTK",
      "arrangor": "Hammarby IF BTF", "plats": "Eriksdalshallen",
      "stupa_url": "https://..."
    }
  ],

  "resultat":  [ "samma form som kommande, plus \"hemma_poang\" och \"borta_poang\"" ],

  "tabeller": [
    {
      "serie": "Division 2 Östra",
      "rader": [
        { "placering": 1, "lag": "Hammarby IF BTF 1", "spelade": 5,
          "vunna": 4, "oavgjorda": 0, "forlorade": 1,
          "matchpoang": 8, "setdiff": "+12" }
      ]
    }
  ],

  "turneringar": [
    { "namn": "Stockholm Open", "datum": "2026-10-11", "ort": "Stockholm",
      "status": "Anmälan öppen", "sista_anmalan": "2026-09-27",
      "stupa_url": "https://..." }
  ]
}
```

Datumen är alltid `YYYY-MM-DD`. Tider är `HH:MM` i 24-timmarsformat.

Fältet `stupa_url` finns överallt så att användaren alltid kan klicka sig
vidare till originalsidan i STUPA när något saknas eller behöver verifieras.
Skalet ersätter inte STUPA, det gör det navigerbart.

## API-referens

Allt nedan är verifierat mot skarp data i augusti 2026.

**Bas-URL:** `https://testbackend.stupaevents.com/ott/v1`

Namnet till trots är detta produktionsbackenden — det är den värd som den
publika sajten `sbtfeventsott.stupaevents.com` själv anropar. Innehållet
stämmer exakt med vad sidan renderar.

**Autentisering:** ingen. Enda kravet är headern `tenant: sbtf`.
Utan den svarar API:et `422 field required`. Fel värde ger
`400 Ogiltig organisation`.

**Dokumentation:** hela OpenAPI-specifikationen ligger öppen på
`https://testbackend.stupaevents.com/openapi.json` (1,9 MB, 893 endpoints,
varav 71 under `/ott/`). `/docs` kräver inloggning, men specen gör inte det.

### Datakedjan

```
get_events                            → 278 evenemang
  event_type "L" = seriespel (14 st)  ·  "T" = turneringar (264 st)
  │
  ├── get_stages?event_id=435         → en stage per division
  │     stage.event_category.category.category_description → "Division 4A"
  │     stage.event_category.category_id                   → 1186
  │
  └── get_group_matches?stage_id=6137&view=standard&show_matrix=true
                       &fetch_point_system=true&show_organiser_details=true
        ├── group_matrix[]  → tabellen (rank, matches_won/lost, group_points)
        └── matches[]       → matcherna
              start_time, round.name, venue.name
              organiser[]                      → arrangerande förening(ar)
              participants[].participant_name  → "Heby AIF B"
              participants[].selected_parents  → klubbtillhörighet
```

**Glöm inte `show_organiser_details=true`.** Utan den saknas fältet
`organiser` helt, och det finns ingen annan väg till uppgiften — `venue`
innehåller bara ett lokalnamn ("Örbyhus", "Hall 1") utan koppling till klubb.
Parametern förekommer inte i OpenAPI-specens exempel; den syns bara om man
läser av det anrop STUPA:s egen matchlista gör.

Arrangören är en lista eftersom en seriehelg kan arrangeras av flera
föreningar. 99 % av matchposterna har den ifylld.

Använd **inte** `get_events_categories` för divisionsnamn — den returnerar bara
toppnivåerna (`Division 4`) och saknar undergrupperna A/B/C. Namnet finns
inbäddat i varje stage enligt ovan.

### Klubbtillhörighet är löst i API:et

Varje lag bär sin kanoniska förening i `selected_parents`:

```json
"selected_parents": [
  { "parent_role": "Member Association",
    "parent_name": "Nordöstra Svealands Bordtennisförbund", "parent_abbr": "Nordö" },
  { "parent_role": "Club",
    "parent_name": "Vassunda Idrottsförening", "parent_abbr": "Vassunda IF" }
]
```

Det problem som `thelinkan/bt-serier` lägger mest möda på — att gissa vilken
förening ett lagnamn tillhör — är därmed till 99 % löst. Föreningen följer med
som strukturerad data.

Men bara till 99 %. Enstaka lag är taggade med kortnamn i stället för
föreningens registrerade namn: ett lag i Pingisligan dam bär *"Spårvägens
BTK"* medan alla andra Spårvägslag bär *"Spårvägens Bordtennisklubb"*. Utan
åtgärd blir det två klubbar i listan, och användaren som söker "Spårvägen"
får välja mellan dem utan att veta vilken som är rätt.

Lösningen är dock inte fri namnmatchning. `get_role_parents?role_id=590`
returnerar STUPA:s eget klubbregister — 590 föreningar — och det är
auktoritativt. Hämtaren normaliserar bort fyllnadsord ("BTK", "Idrottsförening"),
slår upp resultatet i registret och använder det registrerade namnet. Nycklar
som inte är entydiga används inte, så *"Spårvägens Veteran Bordtennisklubb"*
slås inte ihop med *"Spårvägens Bordtennisklubb"*.

Samma lagnamn kan dessutom förekomma i flera serier — "Spårvägens BTK" spelar
både Pingisligan herr och dam. Lag måste därför identifieras av namn *och*
serie, annars försvinner det ena.

### URL-strukturen — och varför djuplänkar inte går

`https://sbtfeventsott.stupaevents.com/events/435/1186/2/7/7`

Det första segmentet är `event_id` och pekar ut evenemanget. Resten ser ut
att peka ut division och vy, men gör det inte.

**Andra segmentet väljer ingenting.** STUPA skriver om det till evenemangets
förvalda kategori oavsett vad man anger. `/events/435/1189` (Division 5B) och
`/events/435/1193` (Division 7A) landar båda på `/events/435/1186` och visar
Division 4. Samma sak för det nationella seriespelet: `/events/417/1176`
(Div 3 SSSV) skrivs om till `/events/417/1119` och visar Pingisligan dam.

Divisionen väljs via Angular Material-menyer på sidan — klienttillstånd som
aldrig hamnar i adressen. Det är därför `thelinkan/bt-serier` styr
rullgardinsmenyerna med Playwright i stället för att konstruera adresser.
Kommentaren i hans `scraper.py` säger det rakt ut: *"serie väljs i sidans
eget gränssnitt"*.

Även de sista segmenten normaliseras. `/events/302/962/2/7/7` blir
`/events/302/962/0/7/7` för ett slutspel, som saknar tabellvy.

Den nakna formen `/events/435` duger inte som alternativ — den ger
"No Records Found".

**Slutsats:** vi länkar till `/events/{event_id}/{category_id}/2/7/7`. Sidan
laddar då korrekt och visar rätt evenemang, men användaren måste själv välja
serien i menyn. Frontenden säger det i länkens `title` och i sidfoten. Det är
det bästa STUPA tillåter.

### Omfattning

Ett enda anrop till `get_events` ger hela Sverige: 14 seriespel (13 distrikt
plus *Nationellt seriespel 2026-2027*, id 417) och 264 turneringar. För
Nordöstra Svealand (id 435) ger kedjan **560 matcher, 10 divisioner och
24 klubbar** på ungefär tio HTTP-anrop.

### Testdata är rikligt och ibland välkamouflerat

200 av 278 evenemang i den publika listan är utvecklings- eller testdata.
Filtret bygger på tre kriterier, alla nödvändiga:

1. `published` måste vara sant — opublicerade evenemang syns inte på STUPA:s
   egen sajt heller.
2. `event_level` får inte vara `"Testtävling"`.
3. Namnet får inte innehålla `test` som eget ord.

Punkt 2 är den viktiga och den lättaste att avfärda, eftersom namnen kan se
fullt trovärdiga ut. *"Bästkustens BTF 26/27"* passerar kriterium 1 och 3, och
låter som vilket distrikt som helst. Men SBTF har exakt 15
specialdistriktsförbund, och Bästkusten är inte ett av dem. Lagen i serien
heter *"Bärke Test"*, *"Carlstad Test"*, *"Lag A"*, *"Lag B"*, och klubbarna är
hopplockade från sju orelaterade distrikt.

Hämtaren varnar därför när ett evenemang med `event_level` som börjar på
"Distrikt" inte matchar något av de 15 förbunden i SBTF:s officiella lista.

### Två fallgropar i matchdatan

**`score_published` betyder inte att matchen är spelad.** Det är en
inställning på divisionsnivå och är `True` även för matcher som ligger ett år
fram i tiden. Använd `status == "COMPLETED"` eller förekomsten av `winner`.

**Placeringarna i `group_matrix` är seedning innan första omgången.** En
ospelad serie returnerar rank 1–8 med idel nollor, vilket ser ut som en riktig
tabell. Hämtaren sätter därför flaggan `startad`, och frontenden visar en
deltagarlista i stället för en tabell när serien inte börjat.

## Förhållande till `thelinkan/bt-serier`

Det projektet är ett **desktopprogram** (PySide6 + SQLite) för den som vill
analysera matchprogram lokalt. Det löser en angränsande men annan uppgift.

Skillnaden i ansats: bt-serier är arrangörscentrerat (vem arrangerar vilken
seriehelg), medan detta skal är spelarcentrerat (vad händer i min klubb).

Den tekniska skillnaden är dock större än så. bt-serier skrapar den renderade
webbsidan med Playwright, vilket medför att:

- hämtningen tar minuter istället för sekunder,
- den går sönder varje gång STUPA ändrar sin layout,
- föreningsnamn måste gissas fram med normaliseringsregler,
- man måste manuellt registrera en fungerande startadress per distrikt.

Ingen av dessa svårigheter finns när man går via API:et. Det är värt att höra
av sig till honom — han har lagt ner rejält med arbete på ett problem som
`openapi.json` löser gratis, och hans domänkunskap om seriespelet vore
värdefull i det här projektet.

## Nästa steg

1. Skapa repot `stupainte/stupainte.github.io` med följande struktur:

   ```
   index.html                       ← frontenden
   scraper/hamta.py                 ← hämtaren
   .github/workflows/uppdatera-data.yml
   data/                            ← genereras av hämtaren
   ```

2. Kör `python3 scraper/hamta.py --ut data` lokalt och kontrollera resultatet.
   Börja gärna med ett distrikt: `--serie-id 435`.
3. Starta en lokal server (`python3 -m http.server`) och testa frontenden.
   `fetch` fungerar inte mot `file://`.
4. Slå på GitHub Pages för repot, committa, och låt workflowet ta över.
5. Filtrera bort testevenemangen ur `get_events`.
6. Fyll ut turneringsdelen — `get_events` ger namn och datum, men
   anmälningsstatus och deltagarlistor kräver ytterligare endpoints
   (`get_event_participants`, `bookings/{event_id}/get_registered_players`).
