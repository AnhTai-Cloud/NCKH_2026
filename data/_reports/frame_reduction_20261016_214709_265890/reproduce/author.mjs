import fs from 'node:fs/promises';
import path from 'node:path';
import readline from 'node:readline';
import {createReadStream} from 'node:fs';
import {createGunzip} from 'node:zlib';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
const require=createRequire('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/check.cjs');
const {Workbook}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')));
const work=path.dirname(fileURLToPath(import.meta.url));
const cfg=JSON.parse(await fs.readFile(path.join(work,'config.json'),'utf8'));
const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
const field=v=>{const s=String(v??'');return /[",\r\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s;};
async function render(wb,sheet,width,name){
  sheet.getRange(`A1:${col(width)}7`).format.columnWidth=18;
  sheet.getRange(`A1:${col(width)}7`).format.font={name:'Arial',size:10};
  sheet.getRange(`A1:${col(width)}1`).format.font={bold:true};
  const png=await wb.render({sheetName:sheet.name,range:`A1:${col(width)}7`,scale:1,format:'png'});
  await fs.writeFile(path.join(work,name),new Uint8Array(await png.arrayBuffer()));
}
if(process.argv[2]==='preview'){
  for(const n of [1,2,3]){
    const op=cfg.plan.find(p=>p.n_sources===n&&p.action==='PARTIAL');
    const csv=await fs.readFile(path.join(cfg.backup,op.path),'utf8');
    const wb=await Workbook.fromCSV(csv,{sheetName:'Original'});
    await render(wb,wb.worksheets.getItemAt(0),4+3*n+1,`before_${n}source.png`);
  }
  console.log(JSON.stringify({status:'ORIGINAL_PREVIEWS_READY',files:3}));
}else if(process.argv[2]==='author'){
  if(cfg.status!=='SNAPSHOT_AND_PLAN_READY')throw Error('Unexpected state; do not regenerate selection');
  const stream=readline.createInterface({input:createReadStream(path.join(work,'operations.jsonl.gz')).pipe(createGunzip()),crlfDelay:Infinity});
  const wb=Workbook.create(),sheet=wb.worksheets.add('Data');const previews=new Set();let count=0;
  for await(const line of stream){
    const op=JSON.parse(line),expected=[op.header,...op.rows];
    const range=sheet.getRange(`A1:${col(op.header.length)}${expected.length}`);
    range.values=expected;wb.recalculate();const actual=range.values;
    if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Source values changed: '+op.path);
    const n=Number(op.path[0]);
    if(!previews.has(n)){
      await render(wb,sheet,op.header.length,`after_${n}source.png`);
      console.log((await wb.inspect({kind:'table',range:`Data!A1:${col(op.header.length)}4`,include:'values',maxChars:850,tableMaxRows:4,tableMaxCols:op.header.length})).ndjson);
      previews.add(n);
    }
    const target=path.join(cfg.stage,op.path);await fs.mkdir(path.dirname(target),{recursive:true});
    const text=actual.map(row=>row.map(field).join(',')).join(op.newline)+op.newline;
    await fs.writeFile(target,text,{flag:'wx'});count++;
    if(count%400===0)console.log(JSON.stringify({csvs_authored:count,total:cfg.partial_files}));
  }
  if(count!==cfg.partial_files)throw Error('Partial file count mismatch');
  cfg.status='CSV_AUTHORED';await fs.writeFile(path.join(work,'config.json'),JSON.stringify(cfg,null,2));
  console.log(JSON.stringify({status:cfg.status,csvs:count}));
}else throw Error('Expected preview or author');
