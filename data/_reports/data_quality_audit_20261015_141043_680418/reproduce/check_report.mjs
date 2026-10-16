import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/check.cjs');
const {chromium}=require('playwright');
const work=path.dirname(fileURLToPath(import.meta.url));const config=JSON.parse(await fs.readFile(path.join(work,'config.json'),'utf8'));
const out=config.output;const result=JSON.parse(await fs.readFile(path.join(out,'results.json'),'utf8'));
const browser=await chromium.launchPersistentContext(path.join(work,'browser-profile'),{headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  viewport:{width:1440,height:1000},args:['--disable-crash-reporter','--disable-crashpad','--noerrdialogs','--disable-gpu']});
try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(pathToFileURL(path.join(out,'index.html')).href);
  if(await page.locator('#summary_table tbody tr').count()!==23)throw Error('Missing summary groups');
  if(await page.locator('#files tbody tr').count()!==100)throw Error('File table incomplete');
  await page.screenshot({path:path.join(work,'report_top_preview.png')});
  await page.locator('#n').selectOption('3');await page.locator('#mode').selectOption('AI');await page.locator('#distance').selectOption('40');
  if(!(await page.locator('#count').innerText()).startsWith('676 '))throw Error('Expected 676 CSVs with observed 40 cm metadata; header-only file has no observed distance');
  await page.locator('#origin').selectOption('SYNTHETIC_DOCUMENTED');
  if(!(await page.locator('#count').innerText()).startsWith('660 '))throw Error('Incorrect provenance filter');
  await page.locator('#search').fill('150_210_240');
  if(await page.locator('#files tbody tr').count()!==3)throw Error('Case search failed');
  await page.locator('#summary_origin').selectOption('UNVERIFIED');
  if(await page.locator('#summary_table tbody tr').count()===0)throw Error('Unknown-origin summary missing');
  await page.locator('#summary_origin').selectOption('all');
  await page.locator('#summary_table').screenshot({path:path.join(work,'summary_preview.png')});
  const imgs=page.locator('img');if(await imgs.count()!==4)throw Error('Missing scientific figures');
  for(let i=0;i<4;i++)if(!await imgs.nth(i).evaluate(el=>el.complete&&el.naturalWidth>0))throw Error('Figure failed');
  for(const a of await page.locator('nav a').all()){
    const target=await a.getAttribute('href');await fs.access(path.join(out,target));
  }
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>innerWidth))throw Error('Mobile overflow');
  await page.screenshot({path:path.join(work,'mobile_preview.png')});
  if(errors.length)throw Error(errors.join('\n'));
  await fs.writeFile(path.join(out,'browser_verification.json'),JSON.stringify({default_summary_groups:23,all_csv_files:result.files_checked,
    provenance_filter:true,case_search:true,download_links:true,scientific_figures:4,mobile_no_overflow:true,page_errors:errors},null,2));
  console.log(JSON.stringify({status:'BROWSER_VERIFIED',summary_groups:23,images:4,mobile_no_overflow:true}));
}finally{await browser.close();}
