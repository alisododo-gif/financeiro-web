import test from 'node:test';
import assert from 'node:assert/strict';
import {customerPeriodMatches} from './customer-period.mjs';
test('customers remain visible regardless of due month or missing date',()=>{for(const row of [{data_vencimento:'2026-09-10'},{data_vencimento:'2026-11-10'},{data_vencimento:null}])assert.equal(customerPeriodMatches('clientes',row,'2026-10'),true);});
test('undated accounts and planning records cannot be removed by a hidden period filter',()=>{for(const table of ['contas','metas','orcamentos'])assert.equal(customerPeriodMatches(table,{nome:'Synthetic'},'2026-10'),true);});
test('financial dates continue to respect the selected month',()=>{assert.equal(customerPeriodMatches('movimentacoes',{data:'2026-09-10'},'2026-10'),false);assert.equal(customerPeriodMatches('contas_receber',{data_recebimento:'2026-10-10'},'2026-10'),true);});
