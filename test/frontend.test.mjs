import { JSDOM } from 'jsdom';
import fs from 'fs';
const html = fs.readFileSync('index.html','utf8');
const load = p => JSON.parse(fs.readFileSync('data/'+p,'utf8'));
const index = load('index.json');
// Förväntade antal räknas ur datafilerna i stället för att hårdkodas — säsongen
// förändrar dem varje vecka och testet ska fånga renderingsfel, inte datadrift.
const H = load('klubb/hammarby-if-bordtennisforening.json');
const ejStartade = H.tabeller.filter(t => t.startad === false).length;
const arrDagar = H.arrangerar.length;
const arrMatcher = H.arrangerar.reduce((a, x) => a + x.antal, 0);

// exakt_lank (länken öppnar rätt division direkt) finns bara på matcher i
// serier utan lettrade undergrupper — sällsynt i stickprovsdatan. Tvinga
// fram ett sant fall på Hammarbys första kommande match så båda
// title-varianterna i matchKort() går att testa deterministiskt.
const dom = new JSDOM(html,{runScripts:'dangerously',url:'https://etxgmg.github.io/stupainte/',
  beforeParse(w){ w.fetch = async u => {
    const s=String(u).replace(/^.*?data\//,'');
    try {
      const data = load(s);
      if (s === 'klubb/hammarby-if-bordtennisforening.json' && data.kommande?.[0]) {
        data.kommande[0] = {...data.kommande[0], exakt_lank: true};
      }
      return {ok:true,status:200,json:async()=>data};
    }
    catch { return {ok:false,status:404,json:async()=>({})}; } }; }});
const w=dom.window, d=w.document, vänta=ms=>new Promise(r=>setTimeout(r,ms));
await vänta(400);
const fel=[], ok=(v,t)=>(v?console.log('  ✓ '+t):fel.push(t));

ok(d.getElementById('picker-status').textContent.includes(index.klubbar.length+' klubbar'),`${index.klubbar.length} klubbar laddade`);

const s=d.getElementById('search');
s.value='hammarby'; s.dispatchEvent(new w.Event('input'));
ok(d.querySelectorAll('.result[data-slug]').length===1,'söker fram Hammarby');
d.querySelector('.result[data-slug]').dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
await vänta(300);

ok(d.getElementById('club-name').textContent.includes('Hammarby'),'klubbvyn öppnas');
ok(d.getElementById('club-meta').textContent.includes(H.lag.length+' lag'),`${H.lag.length} lag`);

const m=d.querySelectorAll('#panel .match');
ok(m.length===H.kommande.length,`${H.kommande.length} kommande matcher (fick ${m.length})`);
ok(d.querySelectorAll('#panel .day').length>1,'grupperade per datum');
ok(d.getElementById('panel').innerHTML.includes('class="mine"'),'egna lag markerade');
// STUPA kan bara ibland djuplänka till rätt division (se exakt_lank i
// hamta.py). Testet kontrollerar båda varianterna av title-texten.
ok(/href="https:\/\/sbtfeventsott[^"]*\/events\/\d+\//.test(d.getElementById('panel').innerHTML),'länk till rätt evenemang i STUPA');
ok(/title="Öppnar STUPA\. Sidan visar en annan division — byt till [^"]+ i menyraden högst upp på STUPA-sidan\."/.test(d.getElementById('panel').innerHTML),'title säger var och vad som ska väljas (osäker länk)');
ok(d.getElementById('panel').innerHTML.includes('title="Öppnar rätt division direkt i STUPA."'),'title säger att länken är exakt (säker länk)');
ok(/arr\. \S/.test(d.getElementById('panel').innerHTML),'arrangör visas på matchkorten');

const flik=n=>[...d.querySelectorAll('nav.tabs button')].find(b=>b.dataset.tab===n)
  .dispatchEvent(new w.MouseEvent('click',{bubbles:true}));

flik('tabeller');
ok(d.querySelectorAll('#panel .table-block').length===H.tabeller.length,`${H.tabeller.length} tabeller`);
// Säsongen har kommit igång sedan sist — alla Hammarbys serier har nu
// spelat minst en omgång, så ingen visas längre som ren deltagarlista.
ok(d.querySelectorAll('#panel .not-started').length===ejStartade,`${ejStartade} ej startade serier visas som deltagarlista`);
ok(d.querySelectorAll('#panel thead').length===H.tabeller.length-ejStartade,'bara startade serier har tabellhuvud');
ok(d.querySelectorAll('#panel tr.mine-row').length>0,'egna lag markerade i tabellerna');
ok(d.querySelectorAll('#panel .table-block h3 .evenemang').length===H.tabeller.length,'varje tabell visar vilket evenemang den tillhör');

flik('resultat');
ok(d.querySelectorAll('#panel .match').length===H.resultat.length,`${H.resultat.length} spelade matcher`);
ok(/\d+–\d+/.test(d.getElementById('panel').innerHTML),'resultatsiffror visas');

flik('arrangerar');
ok(d.querySelectorAll('#panel .dag-block').length===arrDagar,`${arrDagar} speldagar att arrangera`);
ok(d.querySelector('#panel .sammanfattning')?.textContent.includes(arrMatcher+' matcher'),`sammanfattning räknar ${arrMatcher} matcher`);
ok(d.querySelectorAll('#panel .arr-tabell tr').length===arrMatcher,`${arrMatcher} matchrader`);
ok(d.querySelector('#panel .dag-topp').textContent.includes('A-hallen'),'spelplats i dagsrubriken');
ok(d.getElementById('panel').innerHTML.includes('class="mine"'),'egna lag markerade även här');

// Tävlingsfliken testas separat i turneringar.test.mjs — den laddar en
// egen datafil och har eget filterläge.

console.log('\nStickprov — tre klubbar till:');
for (const slug of ['ik-sirius-bordtennisklubb','spargavagens-btk','orebro-bordtennisklubb']) {
  try { const k=load('klubb/'+slug+'.json');
    console.log(`  ${k.klubb.namn}: ${k.lag.length} lag, ${k.kommande.length} kommande`); } catch {}
}
console.log(fel.length?'\nMISSLYCKADES:\n  '+fel.join('\n  '):'\nAlla kontroller godkända.');
process.exit(fel.length?1:0);
