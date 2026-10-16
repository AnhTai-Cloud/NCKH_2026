import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/check.cjs');
const {chromium}=require('playwright');const work=path.dirname(fileURLToPath(import.meta.url));
const cfg=JSON.parse(await fs.readFile(path.join(work,'config.json'),'utf8'));const out=cfg.output;
const browser=await chromium.launchPersistentContext(path.join(work,'browser-profile'),{headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
viewport:{width:1440,height:1000},args:['--disable-crash-reporter','--disable-crashpad','--noerrdialogs','--disable-gpu']});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(pathToFileURL(path.join(out,'index.html')).href);
  const tables=page.locator('table');if(await tables.count()!==5)throw Error('Expected counts, metrics, changes and two paper tables');
  for(const i of [0,1,2])if(await tables.nth(i).locator('tbody tr').count()!==23)throw Error('Condition table incomplete');
  for(const i of [3,4])if(await tables.nth(i).locator('tbody tr').count()!==12)throw Error('Paper table incomplete');
  for(const a of await page.locator('a').all()){
    const href=await a.getAttribute('href');await fs.access(href.startsWith('file:')?fileURLToPath(href):path.resolve(out,href));
  }
  if(!await page.locator('img').evaluate(e=>e.complete&&e.naturalWidth>0))throw Error('Chart failed');
  await page.screenshot({path:path.join(work,'report_top.png')});
  await tables.nth(1).screenshot({path:path.join(work,'metrics_preview.png')});
  await page.setViewportSize({width:390,height:844});if(await page.evaluate(()=>Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>innerWidth))throw Error('Mobile overflow');
  await page.screenshot({path:path.join(work,'mobile_preview.png')});if(errors.length)throw Error(errors.join('\n'));
  await fs.writeFile(path.join(out,'browser_verification.json'),JSON.stringify({status:'VERIFIED',group_rows:23,paper_rows_each:12,links:true,chart:true,mobile_no_overflow:true,errors},null,2));
  console.log(JSON.stringify({status:'REPORT_BROWSER_VERIFIED',tables:5,groups:23}));
}finally{await browser.close();}
