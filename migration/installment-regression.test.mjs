import test from 'node:test';
import assert from 'node:assert/strict';
import {launchRows} from './launch.mjs';
const base={descricao:'Synthetic',valor:100,tipo:'Despesa',data:'2027-01-31',categoria:'Outros',forma_pagamento:'Pix',modalidade:'Parcelado',quantidade:3};
test('every allowed installment count preserves exact cents',()=>{
 for(let count=2;count<=72;count++)for(const cents of [count,count+1,100,10001,99999999,100000000]){if(cents<count)continue;const rows=launchRows({...base,valor:cents/100,quantidade:count});assert.equal(rows.reduce((sum,r)=>sum+Math.round(r.valor*100),0),cents);const amounts=rows.map(r=>Math.round(r.valor*100));assert.ok(Math.max(...amounts)-Math.min(...amounts)<=1);assert.ok(amounts.every(n=>n>=1));}
});
test('leap years, short months and original day restore correctly',()=>{
 assert.deepEqual(launchRows({...base,data:'2028-01-31'}).map(r=>r.data),['2028-01-31','2028-02-29','2028-03-31']);
 assert.deepEqual(launchRows({...base,data:'2026-12-30'}).map(r=>r.data),['2026-12-30','2027-01-30','2027-02-28']);
});
