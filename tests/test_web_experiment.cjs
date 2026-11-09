// Verify defaults, persistence and scope counts against the real page script.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('plc_agent/web_static/index.html','utf8');
const script=fs.readFileSync('plc_agent/web_static/app.js','utf8');
const storage=new Map();let serviceModel='deepseek-v4.1-flash-1017',serviceComparison='qwen3.8-flash',legacy=false;
let formalConfig={status:'not_configured',saved:false,plcverif:'',java:'',cbmc:'',bound:20,timeout_seconds:120,scan_period_ms:10,unwind:256,message:'未找到 PLCverif CLI、Java、CBMC，请填写路径并保存。',config_file:'agent_data/formal_config.json'};
storage.set('plc-workbench.experiment.v1',JSON.stringify({model_b:'undefined',base_comparison_model:'qwen3.8-flash',model_a:'stale-model',base_model:serviceModel}));
async function openPage(){
 const elements=new Map(),ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]));
 function element(){return {get value(){return this._value??''},set value(v){this._value=String(v)},textContent:'',checked:true,children:[],hidden:false,events:{},classList:{toggle(){}},
  replaceChildren(...xs){this.children=xs;if(xs[0]?.value!==undefined)this.value=xs[0].value},append(...xs){this.children.push(...xs)},
  addEventListener(name,fn){this.events[name]=fn}}}
 function query(sel){assert(ids.has(sel.slice(1)),sel);if(!elements.has(sel))elements.set(sel,element());return elements.get(sel)}
 const context={document:{querySelector:query,querySelectorAll:()=>[],createElement:element,createTextNode:x=>x},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
  Option:function(text,value){this.text=text;this.value=value},setInterval:()=>0,clearInterval(){},setTimeout(){},console,
  fetch:async(url,options)=>{if(url==='/api/formal/config'){if(options?.method==='POST')formalConfig={...formalConfig,...JSON.parse(options.body),status:'tools_ready',saved:true,message:'已找到所需工具'};return {ok:true,json:async()=>formalConfig};}if(url==='/api/config'&&options?.method==='POST'){const v=JSON.parse(options.body);serviceModel=v.model;if(!legacy)serviceComparison=v.comparison_model;}return {ok:true,json:async()=>url==='/api/config'?{model:serviceModel,...(legacy?{}:{comparison_model:serviceComparison}),stream:false}:url.startsWith('/api/tasks/')?{id:url.split('/').pop(),requirements:'demo',ltl:{}}:[]}}};
 vm.createContext(context);vm.runInContext(script,context);await new Promise(resolve=>setImmediate(resolve));
 return {query,run:code=>vm.runInContext(code,context)};
}
(async()=>{
 let p=await openPage();
 assert.equal(p.query('#modelA').value,serviceModel);assert.equal(p.query('#modelB').value,'qwen3.8-flash');
 assert.equal(p.query('#modeA').value,'off');assert.equal(p.query('#modeB').value,'off');
 assert(html.indexOf('01</span><div><h2>模型服务')<html.indexOf('02</span><div><h2>CODESYS'));
 assert(html.indexOf('02</span><div><h2>CODESYS')<html.indexOf('03</span><div><h2>形式化验证'));
 assert.equal(p.query('#codesysExe').value,'');
 assert(p.query('#codesysExeSource').textContent.includes('尚未配置'));
 assert(p.query('#formalPlcverifSource').textContent.includes('尚未找到'));
 assert(p.query('#formalStatus').textContent.includes('未找到'));assert.equal(p.query('#formalBound').value,'20');
 p.query('#formalPlcverif').value='E:/Tools/PLC/plcverif-clic.exe';p.query('#formalJava').value='E:/Tools/Java/bin/java.exe';p.query('#formalCbmc').value='E:/Tools/CBMC/bin/cbmc.exe';await p.query('#saveFormal').onclick();assert(formalConfig.saved);assert.equal(formalConfig.cbmc,'E:/Tools/CBMC/bin/cbmc.exe');
 p=await openPage();assert.equal(p.query('#formalPlcverif').value,'E:/Tools/PLC/plcverif-clic.exe');
 assert(p.query('#formalPlcverifSource').textContent.includes('已保存配置'));
 p.query('#formalPlcverif').events.input();assert(p.query('#formalConfigState').textContent.includes('未保存'));
 p.query('#modeB').value='on';p.query('#budgetB').value='3000';p.query('#modeB').events.change();
 p.query('#campaignConcurrency').value='8';p.query('#campaignConcurrency').events.change();
 p=await openPage();assert.equal(p.query('#modeB').value,'on');assert.equal(p.query('#budgetB').value,'3000');assert.equal(p.query('#campaignConcurrency').value,'8');
 p.query('#comparisonModel').value='another-model';await p.query('#save').onclick();assert.equal(serviceComparison,'another-model');assert.equal(p.query('#modelB').value,'another-model');assert.equal(p.query('#modeB').value,'default');
 p=await openPage();assert.equal(p.query('#modelB').value,'another-model');
 p.query('#comparisonModel').value='qwen3.8-flash';await p.query('#save').onclick();assert.equal(p.query('#modelB').value,'qwen3.8-flash');assert.equal(p.query('#modeB').value,'on');
 p.run(`current={id:'one',bank_version:'v1'};populate({tasks:[{id:'one',title:'1',bank_version:'v1'},{id:'two',title:'2',bank_version:'v1'}]});`);
 assert(p.query('#campaignScopeHint').textContent.includes('前两个范围相同'));
 assert(p.query('#campaignScope').children[1].disabled);assert(p.query('#campaignCount').textContent.includes('8 次任务'));
 p.run(`populate({tasks:[{id:'one',title:'1',bank_version:'v1'},{id:'two',title:'2',bank_version:'v2'}]});`);
 p.query('#campaignScope').value='currentBank';p.query('#campaignScope').onchange();
 assert.equal(p.run('selectedTaskIds().length'),1);assert(p.query('#campaignCount').textContent.includes('4 次任务'));
 assert(p.query('#concurrencyHint').textContent.includes('最多同时运行 4 次'));
 assert(!p.query('#campaignScope').children[1].disabled);
 p.run("populate({tasks:[]})");assert(p.query('#startCampaign').disabled);
 serviceModel='new-model';p=await openPage();assert.equal(p.query('#modelA').value,'new-model');
 assert.equal(p.query('#modelB').value,'qwen3.8-flash');
 assert(p.run("preflightText({errors:[],models:['A','B'],task_count:32,total:128,effective_concurrency:16})").includes('不会请求模型'));
 serviceModel='';p=await openPage();assert.equal(p.query('#title').textContent,'模型与环境');assert(!p.query('#notice').textContent.includes('旧启动窗口'));serviceModel='new-model';
 legacy=true;p=await openPage();assert.notEqual(p.query('#modelB').value,'undefined');assert(p.query('#notice').textContent.includes('旧启动窗口'));
 p.query('#model').value='new-model';p.query('#comparisonModel').value='qwen3.8-flash';await p.query('#save').onclick();assert.notEqual(p.query('#modelB').value,'undefined');assert(!p.query('#notice').textContent.includes('已保存到'));
 assert(/id="modelA" readonly/.test(html));assert(/id="modelB" readonly/.test(html));
 console.log('Experiment UI passed: config is authoritative, save/reload synchronizes both models, stale cache and legacy responses cannot show undefined, scope counts and inference persistence.');
})().catch(e=>{console.error(e);process.exitCode=1});
