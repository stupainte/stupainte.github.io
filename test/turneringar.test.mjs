import { JSDOM } from 'jsdom';
import fs from 'fs';
const load = p => JSON.parse(fs.readFileSync('data/'+p,'utf8'));

// Turneringsdatan drivs av dagens datum (hink-fältet flyttas löpande mellan
// kommande/pågående/passerad), så antal per filter och "senaste spelade"
// räknas ut från själva datafilen i stället för att hårdkodas — annars
// blev testet en återkommande underhållsbörda varje gång tiden gick.
const tv = load('turneringar.json').turneringar;
const antalKommande = tv.filter(t => t.hink === 'kommande').length;
const senasteSpelad = tv.filter(t => t.hink === 'passerad')
  .map(t => t.datum).sort().at(-1);

const dom = new JSDOM(fs.readFileSync('index.html','utf8'),{runScripts:'dangerously',url:'https://stupainte.github.io/',
  beforeParse(w){ w.fetch=async u=>{const s=String(u).replace(/^.*?data\//,'');
    try{return{ok:true,status:200,json:async()=>load(s)}}catch{return{ok:false,status:404,json:async()=>({})}}}; }});
const w=dom.window,d=w.document,v=ms=>new Promise(r=>setTimeout(r,ms));
await v(400);
const fel=[], ok=(c,t)=>(c?console.log('  ✓ '+t):fel.push(t));

const s=d.getElementById('search'); s.value='hammarby'; s.dispatchEvent(new w.Event('input'));
await v(200); d.querySelector('.result[data-slug]').click(); await v(300);
[...d.querySelectorAll('nav.tabs button')].find(b=>b.dataset.tab==='turneringar').click();
await v(600);

const knappar=[...d.querySelectorAll('.filterrad button')];
ok(knappar.length===4,`4 filterknappar (fick ${knappar.length})`);
console.log('    ' + knappar.map(b=>b.textContent.trim()).join('  |  '));
ok(d.querySelector('.filterrad button[aria-pressed="true"]')?.dataset.filter==='kommande','Kommande är förvalt');

const rader=d.querySelectorAll('.tourn-tabell tbody tr');
ok(rader.length===antalKommande,`${antalKommande} kommande tävlingar (fick ${rader.length})`);
ok(d.querySelectorAll('.tourn-tabell thead th').length===8,'8 kolumner');
console.log('    kolumner: '+[...d.querySelectorAll('thead th')].map(t=>t.textContent).join(', '));

const html=d.querySelector('.tourn-tabell').innerHTML;
ok(html.includes('resultat.ondata.se'),'länkar till ondata');
ok(html.includes('sbtfeventsott.stupaevents.com'),'länkar till STUPA');
ok(html.includes('Uppsala Life Arena'),'arena visas');
ok(html.includes('SWE'),'land visas');
ok(d.querySelectorAll('.stat.oppen').length>0,'anmälan öppen markeras');
ok(d.querySelectorAll('.olankad').length>0,'olänkade tävlingar renderas som text');

console.log('  Byter till Spelade:');
knappar.find(b=>b.dataset.filter==='passerad').click(); await v(400);
const p=d.querySelectorAll('.tourn-tabell tbody tr');
ok(p.length===150,`begränsat till 150 rader (fick ${p.length})`);
ok(!!d.querySelector('.visa-fler'),'"visa fler"-knapp finns');
const forsta=d.querySelector('.tourn-tabell tbody tr td.datum').textContent.trim();
ok(forsta===senasteSpelad,`senaste först (${forsta}, väntat ${senasteSpelad})`);
d.querySelector('.visa-fler').click(); await v(400);
ok(d.querySelectorAll('.tourn-tabell tbody tr').length===450,'visa fler laddar 300 till');

console.log('  Anmälan öppen:');
[...d.querySelectorAll('.filterrad button')].find(b=>b.dataset.filter==='oppen').click(); await v(300);
const o=[...d.querySelectorAll('.tourn-tabell tbody tr')];
ok(o.length>0,`${o.length} med öppen anmälan`);
ok(o.every(r=>r.querySelector('.stat.oppen')),'alla har öppen anmälan');

console.log(fel.length?'\nMISSLYCKADES:\n  '+fel.join('\n  '):'\nAlla kontroller godkända.');
process.exit(fel.length?1:0);
