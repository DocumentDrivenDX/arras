import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
const require=createRequire('/private/tmp/arras-ashlar-integration-20261029/ui/package.json');
const { chromium }=require('@playwright/test');
const folder=new URL('.',import.meta.url);
const prior=readFileSync(new URL('published064.css',folder),'utf8');
const current=readFileSync(new URL('candidate065.css',folder),'utf8');
const oldReset='.arras-root .gb :where(button:not(.arras-btn),input,select)';
if(!prior.includes(oldReset))throw new Error('Original reset differs');
const reconstructed=prior.replace(oldReset,'.arras-root .gb button:not(.arras-btn),.arras-root .gb input,.arras-root .gb select');
const fixed=current+'\n.arras-root .gb-seg button{font:inherit}';
const started=performance.now();const rows=[];
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1280,height:900}});
 await page.route('**/*',route=>route.abort());
 for(const [profile,css] of [['pre-f7-cascade-reconstruction',reconstructed],['published064',prior],['candidate065',current],['candidate-mode-font-inherit',fixed]]){
  await page.setContent('<style>'+css+'</style><div class="arras-root"><main class="gb"><fieldset class="gb-seg"><legend class="gb-sr">Mode</legend><button type="button" aria-pressed="true">Explore</button><button type="button" aria-pressed="false">Operate</button></fieldset></main></div>');
  const measurements=await page.locator('.gb-seg button').evaluateAll(buttons=>buttons.map(button=>{const s=getComputedStyle(button),r=button.getBoundingClientRect();return {label:button.textContent,fontSize:s.fontSize,lineHeight:s.lineHeight,fontWeight:s.fontWeight,height:r.height,width:r.width};}));
  rows.push({profile,measurements});
 }
 await page.close();
}finally{await browser.close();}
const receipt={scope:'Actual Chromium computed styles using original064/candidate065 wheel CSS; pre-f7 profile explicitly reconstructed by reverting only the Oct22 reset selector; final profile applies proposed mode-only inheritance fix; no HTTP/DB/network',rows,elapsedSeconds:(performance.now()-started)/1000,browserClosed:true};
writeFileSync(new URL('computed-style-receipt.json',folder),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
