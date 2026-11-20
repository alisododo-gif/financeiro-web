import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {script} from './release/financeiro.mjs';
class Element{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.childNodes=[];}append(...nodes){this.childNodes.push(...nodes);}}
function render(table,values){
 const buttons=[new Element('button','Editar'),new Element('button','Excluir'),new Element('button','Marcar pago')];
 buttons[0].onclick=()=>42;const badge=new Element('span','Pendente');
 const cells=values.map(text=>new Element('td',text));cells.at(-2).childNodes=[badge];cells.at(-1).childNodes=buttons;
 const c=vm.createContext({table,node:(tag,text)=>new Element(tag,text)});
 vm.runInContext(script.slice(script.indexOf('function compactRecordCards('),script.indexOf('function compactDueCards(')),c);
 c.grid={querySelectorAll:()=>[{querySelectorAll:()=>cells}]};
 return {result:vm.runInContext('compactRecordCards(grid)',c),buttons,badge};
}
test('compact movement keeps description, financial date, invoice and original action handlers',()=>{
 const f=render('movimentacoes',['9','30/09/2026','Mercado','Despesa','R$ 80,00','Cartão de Crédito','10/2026','Pendente','']);
 const card=f.result.childNodes[0];assert.equal(card.childNodes[0].childNodes[0].textContent,'Mercado');
 assert.equal(card.childNodes[1].childNodes[1].childNodes[1].textContent,'30/09/2026');
 assert.match(card.childNodes[2].textContent,/Fatura 10\/2026/);assert.equal(card.childNodes.at(-2),f.badge);
 assert.equal(card.childNodes.at(-1).childNodes[0],f.buttons[0]);assert.equal(f.buttons[0].onclick(),42);
});
test('compact receivable keeps amount, expected date and existing actions without a movement-only field',()=>{
 const f=render('contas_receber',['12','Serviço','R$ 120,00','15/11/2026','Pendente','']);
 const card=f.result.childNodes[0];assert.equal(card.childNodes[0].childNodes[0].textContent,'Serviço');
 assert.equal(card.childNodes[1].childNodes[0].childNodes[1].textContent,'R$ 120,00');
 assert.equal(card.childNodes[1].childNodes[1].childNodes[1].textContent,'15/11/2026');
 assert.equal(card.childNodes.at(-1).childNodes.length,3);assert.equal(card.childNodes.at(-2),f.badge);
});
