import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import readline from 'node:readline';
import {createReadStream} from 'node:fs';
import {createGunzip} from 'node:zlib';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/check.cjs');
const {Workbook}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')));
const work=path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1'));
const cfg=JSON.parse(await fs.readFile(path.join(work,'config.json'),'utf8'));
const out=cfg.output;
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const field=v=>{const s=String(v??'');return /[",\r\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s;};
const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
async function* ops(){
  const stream=readline.createInterface({input:createReadStream(path.join(out,'operations.jsonl.gz')).pipe(createGunzip()),crlfDelay:Infinity});
  for await(const line of stream)yield JSON.parse(line);
}
async function render(wb,sheet,width,name){
  sheet.getRange(`A1:${col(width)}7`).format.columnWidth=18;
  sheet.getRange(`A1:${col(width)}7`).format.font={name:'Arial',size:10};
  sheet.getRange(`A1:${col(width)}1`).format.font={bold:true};
  console.log((await wb.inspect({kind:'table',range:`${sheet.name}!A1:${col(width)}5`,include:'values',maxChars:1800,tableMaxRows:5,tableMaxCols:width})).ndjson);
  const png=await wb.render({sheetName:sheet.name,range:`A1:${col(width)}7`,scale:1,format:'png'});
  await fs.writeFile(path.join(work,name),new Uint8Array(await png.arrayBuffer()));
}
if(process.argv[2]==='preview'){
  for await(const op of ops()){
    const original=await fs.readFile(path.join(cfg.backup,op.path));
    if(sha(original)!==op.before_sha256)throw Error('Backup changed');
    const wb=await Workbook.fromCSV(original.toString('utf8').replace(/^\uFEFF/,''),{sheetName:'Original'});
    await render(wb,wb.worksheets.getItemAt(0),op.header.length,'before_edit_preview.png');
    console.log(JSON.stringify({previewed:op.path}));break;
  }
}else if(process.argv[2]==='corrections'){
  const result=[];let first=true;
  for await(const op of ops()){
    const original=await fs.readFile(path.join(cfg.backup,op.path));
    if(sha(original)!==op.before_sha256)throw Error('Backup changed');
    const originalText=original.toString('utf8'),bom=originalText.startsWith('\uFEFF')?'\uFEFF':'';
    const text=originalText.replace(/^\uFEFF/,'');
    const wb=await Workbook.fromCSV(text,{sheetName:'Data'}),sheet=wb.worksheets.getItemAt(0);
    const expected=[op.header,...op.rows],range=sheet.getRange(`A1:${col(op.header.length)}${expected.length}`);
    range.values=expected;wb.recalculate();const actual=range.values;
    if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Artifact changed source cell values');
    if(first){await render(wb,sheet,op.header.length,'after_edit_preview.png');first=false;}
    const physical=text.match(/[^\r\n]*(?:\r\n|\n|\r|$)/g).filter(v=>v.length);
    if(physical.length!==expected.length)throw Error('Multiline/extra blank CSV requires review');
    const modified=new Set(op.row_changes.map(r=>r.row));
    const output=physical.map((line,i)=>{
      if(!op.header_reorder&&!modified.has(i))return line;
      const ending=line.match(/(?:\r\n|\n|\r)$/)?.[0]??'';
      return actual[i].map(field).join(',')+ending;
    }).join('');
    const target=path.join(out,'corrected_files',op.path);await fs.mkdir(path.dirname(target),{recursive:true});
    const bytes=Buffer.from(bom+output,'utf8');await fs.writeFile(target,bytes,{flag:'wx'});
    result.push({path:op.path,before_sha256:op.before_sha256,after_sha256:sha(bytes),header_reorder:op.header_reorder,
      serialized_rows_changed:op.header_reorder?op.rows.length:modified.size,value_rows_changed:modified.size,
      value_cells_changed:op.row_changes.reduce((s,r)=>s+r.cells.length,0),header_before:text.split(/\r\n|\n|\r/)[0],header_after:op.header.join(',')});
    if(result.length%25===0)console.log(JSON.stringify({staged_corrections:result.length}));
  }
  await fs.writeFile(path.join(out,'file_changes.json'),JSON.stringify(result,null,2),{flag:'wx'});
  console.log(JSON.stringify({staged_files:result.length,value_rows_changed:result.reduce((s,r)=>s+r.value_rows_changed,0)}));
}else if(process.argv[2]==='tables'){
  const tables=JSON.parse(await fs.readFile(path.join(work,'report_tables.json'),'utf8'));
  for(const table of tables){
    const target=path.join(out,table.name);const f=await fs.open(target,'wx');
    const wb=Workbook.create(),sheet=wb.worksheets.add('Data');let rendered=false;
    try{
      for(let start=0;start<table.rows.length||start===0;start+=500){
        const expected=[table.header,...table.rows.slice(start,start+500)],range=sheet.getRange(`A1:${col(table.header.length)}${expected.length}`);
        range.values=expected;wb.recalculate();const actual=range.values;
        if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Report values changed: '+table.name);
        if(!rendered&&table.name==='summary_metrics.csv'){
          await render(wb,sheet,Math.min(table.header.length,10),'summary_table_preview.png');rendered=true;
        }
        const records=start===0?actual:actual.slice(1);
        await f.write(records.map(row=>row.map(field).join(',')).join('\r\n')+'\r\n');
      }
    }finally{await f.close();}
    console.log(JSON.stringify({table:table.name,rows:table.rows.length,columns:table.header.length}));
  }
}else throw Error('Expected preview, corrections or tables');
