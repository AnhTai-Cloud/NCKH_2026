import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/check.cjs');
const {chromium}=require('playwright');
const work=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(work,'../..');
const out=path.join(root,'data/_reports/paper_readiness_20261016');
const browser=await chromium.launchPersistentContext(path.join(work,'browser-profile'),{headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  viewport:{width:1440,height:1000},args:['--disable-crash-reporter','--disable-crashpad','--noerrdialogs','--disable-gpu']});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(pathToFileURL(path.join(out,'index.html')).href);
  if(await page.locator('#table52 tbody tr').count()!==12||await page.locator('#table53 tbody tr').count()!==12)throw Error('Expected 12 rows per paper table');
  const missing=page.locator('#table52 tbody tr').nth(4);
  if(!(await missing.innerText()).includes('—'))throw Error('Missing baseline must remain blank, not zero metrics');
  await page.screenshot({path:path.join(work,'report_top_preview.png')});
  await page.locator('#table52').screenshot({path:path.join(work,'table52_preview.png')});
  await page.locator('#table53').screenshot({path:path.join(work,'table53_preview.png')});
  for(const scope of ['CAPTURE_RECORD_MATCH','SYNTHETIC_DOCUMENTED','UNVERIFIED','all']){
    await page.locator('#scope').selectOption(scope);
    if(await page.locator('#table52 tbody tr').count()!==12)throw Error('Source filter lost condition rows');
    if(scope==='CAPTURE_RECORD_MATCH'){
      const r=page.locator('#table53 tbody tr').nth(8);
      if(!(await r.innerText()).includes('—'))throw Error('Three-source capture evidence must not be invented');
    }
  }
  for(const img of await page.locator('img').all())if(!await img.evaluate(e=>e.complete&&e.naturalWidth>0))throw Error('Image failed to load');
  for(const anchor of await page.locator('a').all()){
    const href=await anchor.getAttribute('href');if(href&&!href.startsWith('#')&&!href.includes('://'))await fs.access(path.resolve(out,href));
  }
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>innerWidth))throw Error('Mobile overflow');
  await page.screenshot({path:path.join(work,'mobile_preview.png')});
  if(errors.length)throw Error(errors.join('\n'));
  await fs.writeFile(path.join(out,'browser_verification.json'),JSON.stringify({desktop:true,mobile_no_overflow:true,tables_12_rows_each:true,source_filters:4,missing_cells_preserved:true,images:3,links_verified:true,javascript_errors:errors},null,2));
  console.log(JSON.stringify({status:'BROWSER_VERIFIED',figures:3,source_filters:4}));
}finally{await browser.close();}
