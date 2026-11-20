import {financialMonth} from './monthly.mjs';
export function customerPeriodMatches(table,row,period){
 if(table==='movimentacoes')return !period||financialMonth(row)===period;
 return !['movimentacoes','contas_receber','vencimentos'].includes(table)||!period||String(row.data||row.data_recebimento||row.data_vencimento||'').startsWith(period);
}

