export const deliveryStatusUI=String.raw`
(()=>{let last=0;document.addEventListener('click',async event=>{
 if(!event.target.closest('#admin-view-btn')||Date.now()-last<60000)return;last=Date.now();
 const pane=document.getElementById('admin-pane-clients');if(!pane)return;
 let notice=pane.querySelector('[data-delivery-status]');if(!notice){notice=document.createElement('p');notice.dataset.deliveryStatus='1';notice.setAttribute('role','status');pane.prepend(notice);}
 try{const response=await fetch('/api/admin/entregas',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('Indisponível');const s=await response.json();notice.textContent='Alertas do bot hoje: '+(s.sent||0)+' confirmados · '+(s.failed||0)+' falharam · '+(s.retry||0)+' aguardam nova tentativa · '+(s.uncertain||0)+' sem confirmação. Entregas incertas não são repetidas automaticamente.';}
 catch{notice.textContent='Não foi possível consultar a situação dos alertas do bot.';last=0;}
 });})();`;
