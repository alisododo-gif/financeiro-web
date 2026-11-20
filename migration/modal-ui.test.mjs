import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {modalHelpers} from './modal-ui.mjs';import {accessScript} from './release/access-ui.mjs';import {script} from './release/financeiro.mjs';
class Element extends EventTarget{constructor(tag,text){super();this.tag=tag;this.textContent=text;this.children=[];}append(...children){this.children.push(...children);}setAttribute(){}showModal(){this.open=true;}close(){this.open=false;this.dispatchEvent(new Event('close'));}remove(){this.removed=true;}focus(){this.focused=true;}}
function setup(){const main=new Element('main'),context={node:(t,s)=>new Element(t,s),$ :()=>({closest:()=>main})};vm.createContext(context);vm.runInContext(modalHelpers,context);return {main,context};}
test('cancel and Escape resolve false without proceeding to a mutation',async()=>{for(const escape of [false,true]){const {main,context}=setup();let writes=0;const result=vm.runInContext("ask('<b>Excluir cliente?</b>')",context).then(ok=>{if(ok)writes++;return ok;});const dialog=main.children[0];assert.equal(dialog.children[1].textContent,'<b>Excluir cliente?</b>');if(escape)dialog.dispatchEvent(new Event('cancel',{cancelable:true}));else dialog.children[2].children[0].onclick();assert.equal(await result,false);assert.equal(writes,0);assert.equal(dialog.removed,true);}});
test('confirmation proceeds exactly once and removes the dialog',async()=>{const {main,context}=setup();const result=vm.runInContext("ask('Marcar pago?')",context);const d=main.children[0];d.children[2].children[1].onclick();assert.equal(await result,true);assert.equal(d.removed,true);});
test('all integrated scripts parse with modal actions and administration tabs',()=>{new vm.Script(script);new vm.Script(accessScript);assert.doesNotMatch(script,/\bconfirm\(/);assert.match(script,/if\(!await ask\(\(r\[field\]/);for(const text of ['Clientes do sistema','Planos e teste de 7 dias','Acesso por usuário','Cópia de segurança'])assert.ok(accessScript.includes(text));});

test('failed or timed-out operations unlock their controls without enabling previously disabled actions',async()=>{
 for(const name of ['Error','TimeoutError']){
  const controls=[{disabled:false},{disabled:true},{disabled:false}],messages=[];
  const c=vm.createContext({busy:false,document:{querySelectorAll:()=>controls},notify:t=>messages.push(t),syncPager(){}});
  vm.runInContext(script.slice(script.indexOf('async function perform('),script.indexOf('async function mutate(')),c);
  let release;const action=new Promise((_,reject)=>release=()=>reject(Object.assign(new Error('Falha simulada'),{name})));
  c.action=()=>action;const pending=vm.runInContext('perform(action)',c);
  assert.ok(controls.every(x=>x.disabled));let duplicate=0;c.duplicate=()=>duplicate++;
  await vm.runInContext('perform(duplicate)',c);assert.equal(duplicate,0);
  release();await pending;assert.deepEqual(controls.map(x=>x.disabled),[false,true,false]);assert.equal(c.busy,false);
  assert.match(messages[0],name==='TimeoutError'?/mesma chave/:/Falha simulada/);
 }
});

test('invoice opened from due dates offers consultation, while purchase editing stays in Cards',async()=>{
 for(const table of ['vencimentos','cartoes']){
  const items=new Element('div');items.replaceChildren=()=>{items.children=[];};
  const c=vm.createContext({table,invoiceSnapshot:null,invoiceSettle:{},invoiceItems:items,invoiceSummary:{},invoiceTitle:{},invoiceCard:{id:1,nome_cartao:'Synthetic'},invoiceMonth:{value:'2026-10'},node:(t,s)=>new Element(t,s),button:(t)=>new Element('button',t),money:v=>String(v),api:async()=>({registros:[{id:2,descricao:'Synthetic purchase',valor:10,pago:false}]})});
  vm.runInContext(script.slice(script.indexOf('async function consultInvoice(){'),script.indexOf('async function snapshotMovement(')),c);await vm.runInContext('consultInvoice()',c);
  const buttons=items.children[0].children[0].children.filter(x=>x.tag==='button').map(x=>x.textContent);
  assert.deepEqual(buttons,table==='cartoes'?['Editar compra','Excluir compra']:[]);assert.equal(c.invoiceSettle.hidden,false);
 }
});
