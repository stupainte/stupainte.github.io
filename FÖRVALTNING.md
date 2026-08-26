# Förvaltning av STUPA Inte

Allt som behövs för att sköta, felsöka och så småningom lämna över projektet —
det som inte framgår av koden.

Läs `ARKITEKTUR.md` för hur systemet är byggt och `README.md` för hur man
kommer igång. Det här dokumentet handlar om att hålla det vid liv.

---

## 1. Vad detta är, och vad det inte är

En statisk webbplats som visar svenskt bordtennisseriespel klubbvis. Den
hämtar data från Svenska Bordtennisförbundets tävlingssystem STUPA
(marknadsfört som *Pingisarenan*) och presenterar den begripligare än
originalet.

**Det är inte en officiell tjänst.** Inget avtal, ingen överenskommelse och
inget stöd från SBTF eller deras leverantör Stupa. Systemet lever på att ett
odokumenterat API råkar vara öppet. Den insikten ska genomsyra all förvaltning:
allt kan sluta fungera utan förvarning, och ingen är skyldig att varna dig.

**Det finns ingen redundans.** Går STUPA:s API sönder finns ingen andra källa.
Den data som senast hämtades ligger kvar i repot och sajten fortsätter visa
den — vilket är bra, men innebär också att den tyst kan bli gammal.

---

## 2. Konton, åtkomst och återställning

| Vad | Var | Ägare |
| --- | --- | ----- |
| Organisation | `github.com/stupainte` | Gunnar Östberg (etxgmg) |
| Repo | `stupainte/stupainte.github.io` | samma |
| Publicerad sajt | `https://stupainte.github.io` | GitHub Pages |
| Faktureringsmejl | gunnar@enskede.nu | — |

Allt är gratis. Ingen betalning, inga hemligheter, inga API-nycklar, inga
miljövariabler. Workflowet använder GitHubs inbyggda `GITHUB_TOKEN`.

**Enskild felkälla:** ett enda GitHub-konto äger alltihop. Förlorad
kontoåtkomst innebär förlorad kontroll över både organisation och domännamn.
Åtgärder värda att göra en gång:

- Slå på tvåfaktorsautentisering på `etxgmg` och spara återställningskoderna
  utanför datorn.
- Lägg till en andra ägare i organisationen (**People → invitera → roll Owner**)
  om någon annan ska kunna ta över.
- Behåll en lokal klon. Repot innehåller allt; ingenting finns bara på GitHub.

**Om organisationen tappas bort:** namnet `stupainte` frigörs inte automatiskt,
och adressen `stupainte.github.io` går inte att återskapa under ett annat konto.
Det är själva anledningen att skydda kontot.

---

## 3. Så fungerar driften

```
04:00 UTC varje natt
  └─ GitHub Actions kör scraper/hamta.py
       ├─ hämtar klubbregister + evenemang + matcher från STUPA
       ├─ skriver data/index.json och data/klubb/*.json
       ├─ avbryter om färre än 150 klubbar hittas
       └─ committar och pushar om något ändrats
            └─ GitHub Pages publicerar om automatiskt (~1 min)
```

Hela körningen tar under en minut. Inga externa beroenden utöver `requests`.

Workflowet kan också startas manuellt: **Actions → Uppdatera data → Run
workflow**. Gör det efter varje ändring i `hamta.py` i stället för att vänta
till natten.

**Sommartid:** cron i GitHub Actions går alltid på UTC. 04:00 UTC är 05:00
svensk vintertid och 06:00 sommartid. Det spelar ingen roll här, men förklarar
varför tidsstämplarna hoppar en timme i mars och oktober.

**Actions kan pausas.** GitHub stänger av schemalagda workflows i repon som
varit helt inaktiva i 60 dagar. Ett mejl skickas först. Sker det räcker det att
gå in i Actions och trycka på knappen som återaktiverar. Eftersom botens egna
commits inte räknas som aktivitet är det här en realistisk framtida orsak till
att datan tyst slutar uppdateras.

---

## 3b. Den andra källan: TT-Coordinator

Tävlingskalendern kommer från **två** system.

`resultat.ondata.se` (*Tournaments Online*, det publika gränssnittet till
TT-Coordinator) används fortfarande av många föreningar för tävlingar på
lägre nivå. Ett enda anrop mot `?viewAll=1` ger hela kalendern — drygt 1300
tävlingar från 2012 och framåt, med namn, start- och slutdatum, stad, arena
och land. Server-renderad HTML, inget JavaScript, ingen autentisering.

**De två källorna kompletterar varandra nästan perfekt.** Vid kartläggningen
i augusti 2026 fanns bara 5 dubbletter av 1377 tävlingar. STUPA har de högre
nivåerna, TT-Coordinator de lägre.

De har också komplementära luckor, vilket är värt att förstå innan man
felsöker "saknade" uppgifter:

| | TT-Coordinator | STUPA |
| --- | --- | --- |
| Stad, arena, land | ✓ | **saknas helt** |
| Anmälningsstatus | **saknas helt** | ✓ |
| Nivå (Sweden Tour m.m.) | saknas | ✓ |
| Historik | till 2012 | till 2025-02 |

Tomma celler i tävlingstabellen är alltså oftast korrekta, inte en bugg.
Kolumnen *Källa* visar varifrån raden kommer så att användaren förstår varför.

**Tre fällor i ondata:**

1. **Teckenkodningen är windows-1252**, trots att servern anger ISO-8859-1.
   Utan `r.encoding = "windows-1252"` blir alla svenska tecken förstörda.
2. **Tävlingsnamnen är inte länkar.** Adressen ligger i radens
   `onclick`-attribut som `document.location='/001370'`. Färdig länk blir
   `https://resultat.ondata.se/001370/`.
3. **Rader med `class='inactive'` saknar länk.** En tävling får sin sida i
   resultatsystemet först några månader före spel. Frontenden visar dem som
   olänkad text — det är väntat, inte ett fel.

Ondata är ett komplement, inte en förutsättning. Faller källan bort loggar
hämtaren en varning och fortsätter med enbart STUPA-data. Workflowet varnar
om antalet tävlingar understiger 200.

## 4. Beroendet av STUPA

Detta är den enda risk som verkligen betyder något.

**Bas-URL:** `https://testbackend.stupaevents.com/ott/v1`
**Autentisering:** headern `tenant: sbtf`. Inget mer.
**Dokumentation:** hela OpenAPI-specen ligger öppen på
`https://testbackend.stupaevents.com/openapi.json`

Värdnamnet innehåller ordet *testbackend*, men det är produktionsbackenden —
det är den som SBTF:s publika sajt själv anropar. Låt dig inte luras att tro
att det finns en "riktig" backend någon annanstans.

### Vad som kan gå sönder, i fallande sannolikhet

0. **Tillfälligt driftavbrott hos STUPA.** Redan observerat i praktiken
   (se runbooken, avsnitt 6) — inte hypotetiskt. STUPA:s backend kan svara
   med `500`/`502` på breda fronten under kortare perioder. Hämtaren gör tre
   försök med stigande paus (4s, 8s) per anrop, men ett avbrott som varar
   längre än det överlever inte omförsök. Ofarligt: skyddsnätet stoppar
   publicering av ofullständig data, och nästa lyckade körning rättar allt.
1. **Fältnamn eller parametrar ändras.** Mest sannolikt permanent fel.
   Hämtaren slutar hitta något och skriver tomma listor. Rimlighetskontrollen
   fångar de grova fallen.
2. **`tenant`-värdet eller autentiseringen ändras.** Allt slutar fungera på en
   gång. Lätt att upptäcka, kan kräva ny kartläggning.
3. **CORS eller åtkomst stramas åt.** Serveranrop från GitHub Actions kan
   börja blockeras. Då återstår att köra hämtningen från en egen maskin.
4. **Byte av värdnamn.** `testbackend` är ett provisoriskt namn som förr eller
   senare bör bytas. Kartlägg om enligt metoden i avsnitt 6.
5. **SBTF ber dig sluta.** Osannolikt men fullt möjligt. Se avsnitt 11.

### Om du behöver kartlägga om API:et

Metoden som fungerade, och som fungerar igen:

1. Öppna en serie i Pingisarenan i Chrome.
2. `F12` → fliken **Network** → filtrera på **Fetch/XHR**.
3. Ladda om sidan och klicka runt i vyerna.
4. Anropen som listas *är* API:et — inklusive parametrar du aldrig hade gissat.

Punkt 3 är viktig. Det var först när matchlistan renderades som
`show_organiser_details=true` dök upp; den syns inte vid första sidladdningen
och står inte i OpenAPI-specens exempel.

---

## 5. Fällor i STUPA:s data

Var och en av dessa kostade tid att upptäcka. Ändra ingenting i hämtaren utan
att först läsa igenom listan.

### `show_organiser_details=true` måste skickas

Utan parametern saknas fältet `organiser` helt, och det finns ingen annan väg
till uppgiften. `venue` innehåller bara ett lokalnamn ("Örbyhus", "Hall 1")
utan koppling till klubb. Hela fliken *Arrangerar* står och faller med denna
parameter.

### `score_published` betyder inte att matchen är spelad

Det är en inställning på divisionsnivå och är `True` även för matcher ett år
fram i tiden. Använd `status == "COMPLETED"` eller förekomsten av `winner`.
Misstaget gav 82 "spelade" Hammarby-matcher i en säsong som inte börjat.

### Placeringar före seriestart är seedning

En ospelad serie returnerar rank 1–8 med idel nollor, vilket ser ut som en
riktig tabell. Hämtaren sätter flaggan `startad`; frontenden visar då en
deltagarlista i stället.

### Testdata ser trovärdigt ut

200 av 278 evenemang är test- eller utvecklingsdata. Filtret kräver
`published`, `event_level != "Testtävling"` och att namnet inte innehåller
"test" som eget ord.

Det farliga fallet: *"Bästkustens BTF 26/27"* passerar två av tre kriterier och
låter som ett distrikt. Men SBTF har exakt 15 specialdistriktsförbund och
Bästkusten är inte ett av dem — lagen heter "Bärke Test", "Lag A", "Lag B" och
klubbarna kommer från sju orelaterade distrikt. **Lita på `event_level`, inte
på namnet.** Hämtaren varnar när ett distriktsevenemang inte matchar något av
de 15 förbunden.

De 15 distrikten: Dalarnas, Gotlands, Göteborgs, Hallands, Nordvästra
Götalands, Nordöstra Svealands, Norrlands, Skånes, Stockholms, Sydöstra
Götalands, Södermanlands, Värmlands, Västmanlands, Örebro läns, Östergötlands.

### Klubbnamn varierar i enstaka fall

Ett lag i Pingisligan dam bär "Spårvägens BTK" medan alla andra Spårvägslag
bär "Spårvägens Bordtennisklubb". Utan åtgärd blir det två klubbar i listan.
Löses genom uppslagning mot `get_role_parents?role_id=590`, STUPA:s eget
register om 590 föreningar. Endast entydiga nycklar slås ihop, så "Spårvägens
Veteran Bordtennisklubb" står kvar separat.

Detta är alltså inte fri namnmatchning utan uppslagning mot en auktoritativ
källa. Skillnaden är viktig — utvidga inte till suddig matchning.

### Lagnamn är inte unika

"Spårvägens BTK" spelar både Pingisligan herr och dam. Lag måste identifieras
av namn *och* serie, annars försvinner det ena. Klubben gick från 9 till 14 lag
när felet rättades.

### Det går inte att djuplänka till en division

Andra URL-segmentet väljer ingenting. `/events/435/1189` och `/events/435/1193`
skrivs båda om till `/events/435/1186`. Divisionen väljs via menyer på sidan —
klienttillstånd som aldrig hamnar i adressen. Den nakna formen `/events/435`
ger "No Records Found".

Frontenden länkar därför till evenemanget och talar om i tooltip och sidfot att
serien måste väljas manuellt i STUPA:s menyrad. **Försök inte "fixa" detta** —
det är verifierat att det inte går.

### Divisionsnamn finns inte där man tror

`get_events_categories` returnerar bara toppnivåerna ("Division 4") utan
undergrupperna A/B/C. Rätt namn ligger i
`stage.event_category.category.category_description`.

---

## 6. Runbook

### Sajten visar gammal data

1. **Actions → Uppdatera data.** Finns någon körning senaste dygnet?
   - Inga körningar alls → schemat är pausat, se avsnitt 3. Tryck på
     återaktiveringsknappen.
   - Röd körning → öppna loggen, gå vidare nedan.
   - Grön körning utan commit → STUPA hade inga ändringar. Normalt.
2. **Röd på "Kontrollera att resultatet är rimligt"** → hämtningen returnerade
   för få klubbar. Skyddsnätet fungerade som det skulle och gammal data ligger
   kvar. Öppna loggen för steget **Hämta från STUPA** (inte kontrollsteget) —
   den visar vilka anrop som misslyckades och varför.

   Vanligaste orsaken är ett tillfälligt driftavbrott hos STUPA: en klase av
   `500`/`502`-fel över många olika `stage_id` och `event_id` samtidigt,
   snarare än ett enskilt trasigt anrop. Så hände 2026-08-06 (körning #14):
   `testbackend.stupaevents.com` svarade med serverfel på allt från
   matchhämtning till lokaluppslagning under en dryg minut, vilket gav 43
   klubbar i stället för normala ~178. Inget att åtgärda i koden — kör
   `python3 scraper/hamta.py --ut data` igen (manuellt via **Actions → Run
   workflow**, eller vänta till nästa natt) när STUPA svarar normalt igen.
   Ett enda lyckat anrop mot `get_events` är ett snabbt sätt att kontrollera
   om driften är tillbaka.

   Är det däremot ett enskilt evenemang som konsekvent saknas natt efter
   natt är felet mer sannolikt på vår sida — se avsnitt 5.
3. **Röd på "Committa ändringar"** → skrivrättigheter saknas. **Settings →
   Actions → General → Workflow permissions → Read and write**. Detta nollställs
   vid flytt mellan konton och organisationer.

### Sajten är helt tom eller visar felruta

Öppna `https://stupainte.github.io/data/index.json` direkt.

- **404** → Pages är avstängt eller pekar fel gren. **Settings → Pages**,
  gren `main`, mapp `/ (root)`.
- **Giltig JSON** → felet ligger i frontenden. Öppna konsolen i webbläsaren.

### En klubb saknas eller ser fel ut

Sannolikt att klubbens distrikt inte publicerat sitt seriespel än, eller att
evenemanget filtrerats som testdata. Kör lokalt och läs varningarna:

```bash
python3 scraper/hamta.py --ut data 2>&1 | grep -E '^\s+[?!]'
```

### Hämtaren kraschar efter en STUPA-ändring

```bash
python3 scraper/hamta.py --ut data --serie-id 435   # ett distrikt, går snabbt
```

Jämför fältnamnen i svaret mot avsnitt 5. Har STUPA döpt om något är det oftast
en enradsändring. Kartlägg om enligt avsnitt 4 om det är större.

### Git vägrar pusha

Nattjobbet har committat sedan du senast hämtade.

```bash
git pull --rebase && git push
```

Uppstår konflikter i `data/` — strunta i att lösa dem. Katalogen är helt
regenererbar:

```bash
git checkout --theirs data && git rebase --continue
python3 scraper/hamta.py --ut data
```

---

## 7. Övervakning

Det finns ingen. Det är ett medvetet val — men var medveten om vad det innebär:
**sajten kan visa flera veckor gammal data utan att någon märker det**, eftersom
den ser precis lika fungerande ut.

Två saker gör läget acceptabelt:

- Sidfoten och klubbrubriken visar när datan senast uppdaterades. En
  uppmärksam användare ser det.
- GitHub mejlar automatiskt när ett schemalagt workflow misslyckas. Kontrollera
  att notiserna går till en adress du läser: **Settings → Notifications →
  Actions**.

Vill du ha bättre täckning är det billigaste steget att låta workflowet
misslyckas högljutt även när datan blir *stillastående* — exempelvis genom att
avbryta om `index.json` inte ändrats på sju dagar. Det är inte byggt.

---

## 8. Årscykeln

Bordtennissäsongen går juli–juni. Systemet är i huvudsak självgående, men fyra
tillfällen kräver uppmärksamhet.

**Augusti–september — distrikten publicerar.** Vid skrivande stund saknas nio
av femton distrikt eftersom de inte lagt upp sitt seriespel i STUPA. De dyker
upp automatiskt allteftersom. Kontrollera i mitten av september att antalet
klubbar stigit rejält från 177, och **höj då rimlighetskontrollen i workflowet**
så den ligger strax under det nya normalläget.

**Slutet av september — första seriehelgen.** Nu spelas de första matcherna på
riktigt. Detta är enda tillfället att verifiera att resultatvyn fungerar; den
är i praktiken otestad eftersom bara en handfull avgjorda matcher funnits i
datan. Kontrollera samtidigt att tabellerna byter från deltagarlista till
riktig tabell (flaggan `startad`).

**Vid årsskiftet — inget särskilt.** Säsongen löper vidare.

**Juni–juli — säsongsskifte.** Nya evenemang med nya `event_id` skapas.
Hämtaren plockar upp dem automatiskt eftersom den listar alla evenemang, men:

- `--sasong` i `hamta.py` har standardvärdet `2026/2027` och är hårdkodat.
  Det måste ändras.
- Föregående säsongs evenemang ligger kvar i STUPA och fortsätter hämtas.
  Rimligt ett tag — spelade resultat är intressanta — men vid något läge vill
  du filtrera på säsong.
- Klubbfiler för föreningar som inte längre har lag städas bort automatiskt.

---

## 9. Kapacitet, kostnad och den tickande bomben

Allt är gratis. GitHub Pages har mjuka gränser: **1 GB repostorlek, 1 GB
publicerad sajt, 100 GB trafik per månad**. Trafiken är ingen risk — sajten är
någon megabyte per besök och skulle klara tiotusentals besökare i månaden.

**Repostorleken är däremot ett verkligt problem.**

Varje nattlig commit skriver om **samtliga 178 filer**, även när ingenting i
sakinnehållet ändrats, eftersom varje klubbfil innehåller en `uppdaterad`-
tidsstämpel. Botens första körning gav `178 files changed, 178 insertions,
178 deletions` — allt för att byta en tidsstämpel i varje fil.

Konsekvens: ungefär **0,9 MB komprimerat per dygn**, alltså cirka 330 MB per
år. Efter tre år närmar sig repot 1 GB-gränsen. Det påverkar också klontider
och Actions-körningar långt innan dess.

**Rekommenderad åtgärd, ogjord:** låt hämtaren bara skriva filer vars
sakinnehåll faktiskt ändrats — jämför mot befintlig fil med tidsstämpeln
bortmaskad, eller flytta `uppdaterad` till enbart `index.json`. Då blir en
typisk natt några få ändrade filer i stället för 178, och tillväxten sjunker
med en storleksordning.

Görs inte detta är alternativet att med några års mellanrum kollapsa
historiken (`git checkout --orphan`), vilket kastar bort all historik och
kräver en tvingad push.

---

## 10. Kontraktet mellan hämtare och frontend

Ingenting validerar detta. Ändrar du ett fältnamn i `hamta.py` slutar
frontenden tyst visa uppgiften — utan felmeddelande, eftersom JavaScript ger
`undefined` i stället för att klaga.

Fält som frontenden läser och som därför inte får byta namn:

| Fil | Fält |
| --- | ---- |
| `index.json` | `sasong`, `klubbar[].slug`, `.namn`, `.antal_lag` |
| `turneringar.json` | `turneringar[].namn`, `.datum`, `.slutdatum`, `.ort`, `.arena`, `.land`, `.niva`, `.status`, `.kalla`, `.lank`, `.hink` |
| klubbfil | `klubb.namn`, `sasong`, `uppdaterad`, `lag[].namn`, `lag[].serie.namn` |
| match | `datum`, `tid`, `serie`, `omgang`, `hemma`, `borta`, `plats`, `arrangor`, `arrangorer`, `stupa_url`, `hemma_poang`, `borta_poang` |
| tabell | `serie`, `startad`, `rader[].placering`, `.lag`, `.spelade`, `.vunna`, `.oavgjorda`, `.forlorade`, `.matchpoang`, `.setdiff` |
| arrangerar | `datum`, `antal`, `platser`, `serier`, `matcher[]` |
| turnering | `namn`, `datum`, `ort`, `niva`, `status`, `stupa_url` |

### Fält som skrivs men aldrig läses

Kontrollerat mot koden, inte antaget. Dessa kan tas bort utan att något går
sönder, och skulle krympa datan en del:

| Var | Fält | Kommentar |
| --- | ---- | --------- |
| `index.json` | `arrangerar_dagar` | tillagt för framtida bruk, används inte |
| match | `hemma_klubb`, `borta_klubb` | behövs under bearbetningen men inte i utdatan |
| tabell | `evenemang` | |
| tabellrad | `klubb` | |
| turnering | `slutdatum` | |

`hemma_klubb` och `borta_klubb` finns på varje matchpost och förekommer i
tusentals rader. Att sluta skriva dem är den enskilt största enkla
besparingen i filstorlek.

Kör `npm test` efter varje ändring i hämtaren. Testet laddar `index.html` i en
riktig DOM mot verklig data och fångar de flesta brott mot kontraktet.

**Testet är dock bundet till Hammarby IF och dagens datamängd** — det
kontrollerar exakta antal som "80 kommande matcher" och "4 speldagar". Dessa
siffror ändras när säsongen fortskrider och måste då justeras. Ett fallerande
test betyder alltså inte nödvändigtvis att något är trasigt. Läs vilken
kontroll som brast innan du drar slutsatser.

---

## 11. Juridik, etik och relationer

**Licens.** Koden är MIT. Tävlingsdatan i `data/` kommer från SBTF:s system och
ägs inte av projektet. Att vidarelicensiera den vore att ta sig friheter man
inte har.

**Personuppgifter.** Systemet lagrar inga. Endast lag-, klubb- och lokalnamn.
Spelarnamn finns i STUPA:s API men hämtas medvetet inte. **Behåll den
begränsningen** — så fort spelarnamn lagras blir projektet en
personuppgiftsbehandling med allt vad det innebär.

**Belastning.** Hämtaren gör ungefär hundra anrop en gång per dygn. Det är
försumbart och långt under vad en enskild användare av STUPA:s egen sajt
genererar. Öka inte frekvensen utan skäl, och lägg inte till en
"uppdatera nu"-knapp som låter användare trigga hämtning.

**Förhållandet till SBTF.** Detta är den viktigaste posten i hela dokumentet.

Systemet bygger på ett odokumenterat API som råkar vara öppet. Det är inte
olagligt och inte ohederligt — datan är publik och visas redan för vem som
helst — men det finns ingen överenskommelse. Om sajten får spridning kommer
SBTF eller Stupa förr eller senare att upptäcka den.

Rekommendationen är att ta kontakt innan det sker, inte efter: beskriv vad du
byggt, att du hämtar en gång per dygn, att du inte lagrar personuppgifter och
att du länkar tillbaka till Pingisarenan. Blir de positiva har du något
stabilt och kanske till och med en dialog om ett riktigt API. Blir de negativa
vill du veta det medan hundra spelare ännu inte gjort sajten till en vana.

`info@sbtf.se` är ingången.

**Förhållandet till thelinkan.** `github.com/thelinkan/bt-serier` löser en
angränsande uppgift — samma data, arrangörscentrerat, som desktopprogram med
Playwright. Hans `MatchRecord`-fält var det som ledde fram till
`show_organiser_details`, och fliken *Arrangerar* är i praktiken hans idé i
klubbform. Han förtjänar att veta att API:et finns; det gör hans Playwright-
lager onödigt.

---

## 12. Beslut och varför

Sådant som ser ut som misstag men är avsiktligt.

**Statisk sajt med förhämtad data i stället för live-anrop.** STUPA:s API
tillåter bara anrop från `*.stupaevents.com`. En webbläsare på
`stupainte.github.io` blockeras av CORS. Verifierat, inte antaget. Därför
hämtas datan serverside och committas.

**JSON i git i stället för databas.** Datan är liten, läses aldrig
transaktionellt och versionshanteringen är en gratis revisionslogg. En databas
hade krävt en server och därmed kostnad och underhåll.

**En fil per klubb i stället för en stor.** Frontenden laddar ett index på
några kilobyte och sedan bara den valda klubben. Skulle allt ligga i en fil
vore första sidladdningen 5 MB.

**Ingen byggkedja, inget ramverk.** `index.html` är en fil utan beroenden.
Den fungerar om tio år, vilket få byggkedjor gör. Priset är att filen är lång.

**Turneringsfliken är rikstäckande och därför nästan värdelös.** Samma sju
turneringar visas för alla klubbar och orten är tom eftersom `event_venues`
bara ger lokalnamn. Det är medvetet lämnat — men överväg att dölja fliken
tills den filtrerar på distrikt. En irrelevant flik skadar förtroendet mer än
en saknad.

**Arrangörsvyn innehåller matcher där inga egna lag spelar.** Det är hela
poängen: som värd ansvarar man för dagen, inte bara för sina egna matcher.

**Klubbnormalisering endast mot register, aldrig suddig matchning.** Se
avsnitt 5.

---

## 13. Om du vill lämna över eller lägga ner

**Lämna över:** lägg till mottagaren som Owner i organisationen, överför sedan
ägarskapet. Repot innehåller allt som behövs — ingen kunskap sitter någon
annanstans än i detta dokument och `ARKITEKTUR.md`.

**Lägga ner:** stäng av workflowet (**Actions → Uppdatera data → ⋯ → Disable
workflow**) och lämna sajten uppe. Den fortsätter visa sin sista data utan
kostnad. Lägg till en rad i sidfoten om att den inte längre uppdateras — en
tyst frusen sajt är sämre än en ärligt avslutad.

**Radera:** att ta bort repot frigör inte namnet `stupainte` på GitHub.
Organisationen måste raderas separat om namnet ska bli ledigt igen.

---

*Senast uppdaterad: 2026-08-05*
