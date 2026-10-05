// Invarianter som måste gälla för genererad data, oavsett säsongsläge.
//
// Bakgrund: serienamn är inte unika (Stockholm och Götaland har båda
// "Div 5 Södra"), och hämtaren slog tidigare ihop tabeller på namn. Boo
// Racketklubb fick då Götalands Div 5 Södra i stället för Stockholms. I
// datan 2026-10-05 hade 203 av 1271 tabeller fel serie, hos 128 av 307 klubbar.
import fs from 'fs';
const load = p => JSON.parse(fs.readFileSync('data/'+p,'utf8'));
const fel = [];
const index = load('index.json');
let tabeller = 0;

for (const k of index.klubbar) {
  const d = load(`klubb/${k.slug}.json`);
  const egna = new Set(d.lag.map(l => l.namn));
  for (const t of d.tabeller) {
    tabeller++;
    // 1. En tabell som visas för en klubb måste innehålla minst ett av klubbens egna lag.
    if (!t.rader.some(r => egna.has(r.lag)))
      fel.push(`${k.namn}: tabellen "${t.serie}" (${t.evenemang}) innehåller inget av klubbens lag`);
  }
  // 2. Varje lag ska ha en tabell i just sin serie och sitt evenemang.
  const tabellnycklar = new Set(d.tabeller.map(t => t.evenemang + '|' + t.serie));
  for (const l of d.lag) {
    if (l.evenemang && !tabellnycklar.has(l.evenemang + '|' + l.serie.namn) &&
        !d.kommande.concat(d.resultat).every(m => m.serie !== l.serie.namn))
      fel.push(`${k.namn}: laget ${l.namn} saknar tabell för ${l.serie.namn} (${l.evenemang})`);
  }
  // 3. Inga två tabeller i samma klubbvy får heta likadant inom ett evenemang.
  const sedda = new Set();
  for (const t of d.tabeller) {
    const n = t.evenemang + '|' + t.serie;
    if (sedda.has(n)) fel.push(`${k.namn}: dubblettserie ${t.serie} i ${t.evenemang}`);
    sedda.add(n);
  }
}
console.log(`  ${index.klubbar.length} klubbar, ${tabeller} tabeller kontrollerade`);
console.log(fel.length ? '\nMISSLYCKADES:\n  ' + fel.slice(0, 15).join('\n  ') + (fel.length > 15 ? `\n  … och ${fel.length-15} till` : '') : '\nAlla kontroller godkända.');
process.exit(fel.length ? 1 : 0);
