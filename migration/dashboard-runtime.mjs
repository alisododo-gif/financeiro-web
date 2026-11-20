import {financialMonth} from './monthly.mjs';
// Browser state stays inside the authenticated page and is cleared on logout.
export function optimizeDashboardSource(source){
 const start=source.indexOf('async function allMovements(){'),end=source.indexOf('function renderFlow(',start);
 if(start<0||end<0)throw Error('Estrutura do painel não reconhecida');
 const reader=`let fpMovementRead=null,fpMovementEpoch=0,fpMovementLoaded=0,fpDashboardDirty=false;
async function allMovements(){
 const year=$('year').value,epoch=fpMovementEpoch;
 if(loadedMovements!==null&&loadedYear===year&&Date.now()-fpMovementLoaded<120000)return loadedMovements;
 if(fpMovementRead?.year===year&&fpMovementRead.epoch===epoch)return fpMovementRead.promise;
 const promise=(async()=>{const response=await api('financeiro/ano?'+new URLSearchParams({ano:year}));
 if(!Array.isArray(response.registros))throw Error('Extrato anual indisponível.');
 if(epoch===fpMovementEpoch&&year===$('year').value){loadedMovements=response.registros;loadedYear=year;fpMovementLoaded=Date.now();}
 return response.registros;})();
 fpMovementRead={year,epoch,promise};try{return await promise;}finally{if(fpMovementRead?.promise===promise)fpMovementRead=null;}
}
`;
 source=source.slice(0,start)+reader+source.slice(end);
 source=source.replace('dashboard();loadTable();','dashboard();')
  .replaceAll("String(m.data||'')","(financialMonth(m)+'-01')");
 return financialMonth.toString()+'\n'+source+`
function fpInvalidateOverview(){fpMovementEpoch++;fpMovementRead=null;loadedMovements=null;loadedYear=null;fpMovementLoaded=0;fpDashboardDirty=true;}
document.addEventListener('fp:data-changed',fpInvalidateOverview);
document.addEventListener('fp:session-reset',()=>{fpInvalidateOverview();dashboardSerial++;});
const fpOverview=document.getElementById('finance-content');
if(fpOverview)new MutationObserver(()=>{if(fpDashboardDirty&&!fpOverview.classList.contains('hidden')&&!document.getElementById('app-panel').classList.contains('hidden')){fpDashboardDirty=false;dashboard();}}).observe(fpOverview,{attributes:true,attributeFilter:['class']});
`;
}

