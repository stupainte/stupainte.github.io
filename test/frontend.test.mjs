import { JSDOM } from 'jsdom';
import fs from 'fs';
const html = fs.readFileSync('index.html','utf8');
const load = p => JSON.parse(fs.readFileSync('data/'+p,'utf8'));
const index = load('index.json');

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

ok(d.getElementById('picker-status').textContent.includes('253 klubbar'),'253 klubbar laddade');

const s=d.getElementById('search');
s.value='hammarby'; s.dispatchEvent(new w.Event('input'));
ok(d.querySelectorAll('.result[data-slug]').length===1,'söker fram Hammarby');
d.querySelector('.result[data-slug]').dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
await vänta(300);

ok(d.getElementById('club-name').textContent.includes('Hammarby'),'klubbvyn öppnas');
ok(d.getElementById('club-meta').textContent.includes('9 lag'),'9 lag');

const m=d.querySelectorAll('#panel .match');
ok(m.length===70,`70 kommande matcher (fick ${m.length})`);
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
ok(d.querySelectorAll('#panel .table-block').length===9,'9 tabeller');
// Säsongen har kommit igång sedan sist — alla Hammarbys serier har nu
// spelat minst en omgång, så ingen visas längre som ren deltagarlista.
ok(d.querySelectorAll('#panel .not-started').length===0,'alla serier har startat');
ok(d.querySelectorAll('#panel thead').length===9,'alla 9 startade serier har tabellhuvud');
ok(d.querySelectorAll('#panel tr.mine-row').length>0,'egna lag markerade i tabellerna');

flik('resultat');
ok(d.querySelectorAll('#panel .match').length===20,'20 spelade matcher');
ok(/\d+–\d+/.test(d.getElementById('panel').innerHTML),'resultatsiffror visas');

flik('arrangerar');
ok(d.querySelectorAll('#panel .dag-block').length===3,'3 speldagar att arrangera');
ok(d.querySelector('#panel .sammanfattning')?.textContent.includes('22 matcher'),'sammanfattning räknar 22 matcher');
ok(d.querySelectorAll('#panel .arr-tabell tr').length===22,'22 matchrader');
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
