// Exercise actual rendering functions against the actual HTML IDs, without a network.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('plc_agent/web_static/index.html','utf8');
const ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(x=>x[1]));
const elements=new Map();
function element(){return {value:'',textContent:'',children:[],hidden:false,classList:{toggle(){}},
 replaceChildren(...xs){this.children=xs},append(...xs){this.children.push(...xs)},addEventListener(){}}}
function query(s){assert(ids.has(s.slice(1)),`Missing HTML control ${s}`);if(!elements.has(s))elements.set(s,element());return elements.get(s)}
const context={document:{querySelector:query,querySelectorAll:()=>[],createElement:element,createTextNode:x=>x},
 Option:function(label,value){this.text=label;this.value=value},fetch:()=>new Promise(()=>{}),console,
 setInterval:()=>0,clearInterval(){},setTimeout(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync('plc_agent/web_static/app.js','utf8'),context);
vm.runInContext(`render({status:'finite_pass',output_path:'outputs/single/fixture',receipt:{model_calls:1,
 target_compile:'passed',metrics_summary:{test_cases_passed:3,test_cases_total:4,mapped_assertions_proved:2,mapped_assertions_total:3,declared_ltl_total:9},
 final_evaluation:{formal_verification:{status:'timeout'}}}})`,context);
assert(query('#taskMetrics').textContent.includes('3/4 (75.0%)'));
assert(query('#taskMetrics').textContent.includes('超时'));
assert(query('#taskMetrics').textContent.includes('完整 LTL 尚未证明'));
assert(query('#outputPath').textContent.includes('outputs/single/fixture'));
vm.runInContext(`renderCampaign({id:'fixture',status:'completed',completed:1,total:4,models:['A','B'],task_ids:['CUSTOM_09'],results:[],summary:[{
 framework:'self',model:'A',completed:1,codesys_compiled:1,codesys_first_compile_passed:1,passed:1,pass_at_1:1,test_cases_passed:3,test_cases_total:4,
 mapped_assertions_proved:2,mapped_assertions_total:3,formal_statuses:{timeout:1}}]})`,context);
assert.equal(query('#campaignRows').children[0].children.length,12);
vm.runInContext(`renderCampaign({id:'fixture',status:'running',completed:1,total:4,
 models:['deepseek-v4.1-flash-1017','qwen3.8-flash'],task_ids:['IMPORT_abc__CUSTOM_01'],summary:[],
 results:[{task_id:'IMPORT_abc__CUSTOM_01',framework:'codex',model:'deepseek-v4.1-flash-1017',
 status:'missing_candidate',cli_exit_code:1,target_compile:'not_executed',ltl_status:'not_executed',model_calls:0,
 metrics_summary:{test_cases_passed:null,test_cases_total:7}}]})`,context);
const failureRow=query('#runRows').children[0].children;
assert.equal(failureRow.length,10);
assert.equal(failureRow[0].textContent,'CUSTOM_01');
assert.equal(failureRow[1].textContent,'Codex');
assert.equal(failureRow[2].textContent,'模型 A');
assert.equal(failureRow[3].textContent,'未生成 ST 代码');
assert(failureRow[3].children[0].textContent.includes('未进入编译'));
assert.equal(failureRow[4].textContent,'未执行');
assert.equal(failureRow[5].textContent,'未执行（共 7 场景）');
console.log('Web metrics rendering passed: controls, task ratios, formal statuses, output paths, campaign columns.');
