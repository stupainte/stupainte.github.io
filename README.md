# STUPA Inte

Ett klubbcentrerat skal ovanpå STUPA. Välj din klubb och se allt aktuellt på
en sida: kommande matcher, tabeller, spelade resultat och turneringar.

## Repostruktur

Lägg filerna så här i `stupainte/stupainte.github.io`:

```
index.html                            ← frontenden (en fil, inget byggsteg)
scraper/hamta.py                      ← hämtar från STUPA:s API
.github/workflows/uppdatera-data.yml  ← kör hämtaren varje natt
data/                                 ← genereras, committas av workflowet
  index.json
  klubb/<slug>.json
ARKITEKTUR.md                         ← hur alltihop hänger ihop, plus API-referens
```

## Kom igång

```bash
pip install requests

# Hämta ett distrikt först — går på några sekunder
python3 scraper/hamta.py --ut data --serie-id 435

# Eller allt: 14 seriespel, hela landet
python3 scraper/hamta.py --ut data

# Testa frontenden. fetch fungerar inte mot file://, så en server behövs.
python3 -m http.server
# → http://localhost:8000
```

## Så fungerar det

STUPA:s webb är en klientrenderad SPA, men den hämtar sin data från ett öppet
JSON-API som vi kan anropa direkt. API:et tillåter dock bara anrop från
`*.stupaevents.com`, så frontenden kan inte prata med det. Därför hämtar ett
schemalagt GitHub Actions-jobb datan, committar den som JSON, och den statiska
sidan läser filerna.

```
GitHub Actions  →  STUPA:s API  →  data/*.json i repot  →  GitHub Pages
   varje natt                          git commit            index.html
```

Ingen server, inga kostnader, inget att underhålla utöver hämtaren.

Se `ARKITEKTUR.md` för API-referensen: endpoints, datakedjan, hur URL-segmenten
i `/events/435/1186/2/7/7` ska tolkas, och varför klubbtillhörighet inte behöver
gissas fram.

## Publicera

Skapa ett publikt repo som heter `stupainte` på kontot `etxgmg`, och kör:

```bash
git remote add origin https://github.com/etxgmg/stupainte.git
git push -u origin main
```

Slå sedan på GitHub Pages under **Settings → Pages**: källa `main` / `(root)`.
Sidan hamnar på `https://etxgmg.github.io/stupainte`.

Workflowet börjar köra av sig självt kl 04 varje natt. Det går också att
starta manuellt under **Actions → Uppdatera data → Run workflow**.

## Innehåll just nu

Hämtat 2026-08-05 från sex publicerade seriespel:

| Evenemang | Matcher |
| --------- | ------- |
| Nationellt seriespel 2026-2027 | 2131 |
| Nordöstra Svealands BTF 26/27 | 560 |
| Lag-SM 2026 | 165 |
| Nordvästra Götalands BTF 25/26 | 40 |
| Nationellt kvalspel 2026 | 35 |
| Pingisligan by STIGA Slutspel | 18 |

Totalt **177 klubbar, 2949 matcher, 68 serier** — plus 72 turneringar.

Nio av SBTF:s femton distrikt saknas, för att de ännu inte publicerat sitt
seriespel för 26/27 i STUPA. De dyker upp automatiskt när de gör det.

## Om testdata i STUPA

STUPA:s publika evenemangslista blandar skarpa serier med utvecklings- och
testdata. `hamta.py` filtrerar på tre kriterier: `published`,
`event_level != "Testtävling"` och att namnet inte innehåller "test" som eget
ord. 200 av 278 evenemang faller bort.

Var särskilt uppmärksam på att namn kan se helt trovärdiga ut.
*"Bästkustens BTF 26/27"* låter som ett distrikt, men SBTF har bara 15
specialdistriktsförbund och Bästkusten är inte ett av dem — lagen i den serien
heter "Bärke Test", "Lag A", "Lag B", och klubbarna är hopplockade från sju
orelaterade distrikt. Lita på `event_level`-flaggan hellre än på namnet.

Hämtaren varnar när ett distriktsevenemang inte matchar något av de 15 SDF:en.

## Status

Klart:

- Frontenden — klubbsökning, fem flikar, mobilanpassad, mörkt läge, sparar
  klubbval lokalt. 23 automatiska kontroller mot skarp data passerar
  (`node test/frontend.test.mjs`).
- Fliken **Arrangerar** — klubbens egna seriehelger grupperade per speldag,
  med antal matcher, lokal och vilka serier som spelas. Innehåller även
  matcher där inget eget lag deltar, vilket är själva poängen: som värd
  ansvarar man för hela dagen. 139 av 177 klubbar arrangerar minst en dag.
- Hämtaren — går via API:et, ingen Playwright. Filtrerar testdata och städar
  bort klubbfiler från evenemang som försvunnit.
- Workflowet — schemalagt, med skyddsnät mot att skriva över fungerande data
  om STUPA ändrar sitt API.

Kvar:

- **Turneringsfliken är rikstäckande och identisk för alla klubbar.** Samma
  sju turneringar visas oavsett om du valt en klubb i Gävle eller Malmö, och
  orten är tom eftersom `event_venues` bara ger lokalnamn. Det är fliken med
  minst värde just nu — den borde filtreras på distrikt eller geografi.
- Spelade resultat är tunt beprövade. Bara en handfull avgjorda matcher finns
  i datan (Lag-SM 2026), så resultatvyn är i praktiken otestad mot verklig
  seriedrift. Kontrollera i slutet av september när första omgången spelats.
- `Vedums Allmänna IS` arrangerar två speldagar men har inga egna lag i
  datan. Vyn hanterar det, men det är värt att veta att sådana klubbar finns.
- Turneringslistan är rikstäckande och identisk för alla klubbar. Den borde
  filtreras på distrikt eller geografi.
- Spelade resultat är tunt beprövade — bara en handfull avgjorda matcher finns
  i datan (Lag-SM 2026). Värt att kontrollera igen när säsongen dragit igång.
- Rimlighetskontrollen i workflowet kräver minst 20 klubbar. Höj den till
  runt 150 nu när det normala är 177.
