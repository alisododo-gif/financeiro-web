export const experience=String.raw`
(()=>{'use strict';
 const root=document.documentElement;
 document.title='FinanceiroPro Web';
 let chosen;try{chosen=localStorage.getItem('fp-theme');}catch{}
 const theme=chosen==='light'||chosen==='dark'?chosen:(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
 root.dataset.theme=theme;
 const toggle=document.createElement('button');toggle.type='button';toggle.className='theme-toggle';
 const updateToggle=()=>{toggle.textContent=root.dataset.theme==='dark'?'☀ Tema claro':'☾ Tema escuro';toggle.setAttribute('aria-label',root.dataset.theme==='dark'?'Ativar tema claro':'Ativar tema escuro');};updateToggle();
 toggle.addEventListener('click',()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('fp-theme',root.dataset.theme);}catch{}updateToggle();});
 const app=document.getElementById('app-panel');if(!app)return;
 const nav=document.querySelector('.view-nav');
 const account=document.createElement('button');account.id='account-view-btn';account.type='button';account.textContent='Alterar senha';
 const dialog=document.createElement('dialog');dialog.className='account-dialog';dialog.setAttribute('aria-labelledby','account-title');
 dialog.innerHTML='<form id="account-form"><h2 id="account-title">Alterar senha</h2><p>Confirme sua senha atual e escolha uma nova. Depois, entre novamente.</p><label>Senha atual<input name="atual" type="password" autocomplete="current-password" required maxlength="1024"></label><label>Nova senha<input name="nova" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></label><label>Confirmar nova senha<input name="confirmacao" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></label><p class="account-message" role="status"></p><div class="account-actions"><button type="button" class="outlined" id="account-cancel">Cancelar</button><button type="submit">Salvar nova senha</button></div></form>';
 document.body.append(dialog);
 const accountForm=dialog.querySelector('form'),accountMessage=dialog.querySelector('[role=status]');
 account.addEventListener('click',()=>{document.dispatchEvent(new Event('fp:close-menu'));accountForm.reset();accountMessage.textContent='';dialog.showModal();});
 dialog.querySelector('#account-cancel').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>accountForm.reset());
 accountForm.addEventListener('submit',async event=>{event.preventDefault();const submit=accountForm.querySelector('[type=submit]');if(submit.disabled)return;const data=Object.fromEntries(new FormData(accountForm));if(data.nova!==data.confirmacao){accountMessage.textContent='A confirmação deve ser igual à nova senha.';return;}submit.disabled=true;accountMessage.textContent='Verificando e salvando...';try{const response=await fetch('/api/conta/senha',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-financeiro-operacao':'1'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.erro||'Não foi possível alterar a senha');accountForm.reset();document.dispatchEvent(new Event('fp:session-reset'));location.replace('/app');}catch(error){accountMessage.textContent=error.message;}finally{submit.disabled=false;}});
 const additions=[['accounts-view-btn','Contas'],['goals-view-btn','Metas'],['budgets-view-btn','Orçamentos']];
 for(const [id,label]of additions){if(document.getElementById(id))continue;const b=document.createElement('button');b.id=id;b.type='button';b.textContent=label;nav?.append(b);}
 const sidebar=document.createElement('aside');sidebar.className='sidebar';sidebar.setAttribute('aria-label','Navegação principal');
 const brand=document.createElement('div');brand.className='sidebar-brand';brand.setAttribute('aria-label','FinanceiroPro Web');const brandImage=document.createElement('img');brandImage.src=document.querySelector('.login-logo img')?.getAttribute('src')||'/static/financeiropro-logo.webp';brandImage.alt='FinanceiroPro Web';brand.append(brandImage);sidebar.append(brand);
 const entries=[['finance-view-btn','Visão geral','◈'],['launch-view-btn','Novo lançamento','＋'],['manage-view-btn','Movimentações','⇄'],['invoices-view-btn','Cartões e faturas','▤'],['receivables-view-btn','Recebimentos','↙'],['due-view-btn','Vencimentos','▦'],['clients-view-btn','Clientes','♙'],['accounts-view-btn','Contas','▣'],['goals-view-btn','Metas','◎'],['budgets-view-btn','Orçamentos','◴'],['admin-view-btn','Administração','⚙']];
 if(nav){nav.setAttribute('aria-label','Seções do sistema');for(const [id,label,icon]of entries){const b=document.getElementById(id);if(!b)continue;b.replaceChildren();const i=document.createElement('span');i.className='nav-icon';i.setAttribute('aria-hidden','true');i.textContent=icon;b.append(i,document.createTextNode(label));nav.append(b);}nav.append(toggle);const logout=document.getElementById('logout-btn');if(logout){logout.classList.add('sidebar-logout');nav.append(logout);}sidebar.append(nav);}
 const note=document.createElement('div');note.className='sidebar-note';note.innerHTML='<b>Um só lugar para suas finanças</b>Contas, clientes e planejamento conectados ao seu dia a dia.';sidebar.append(note);app.prepend(sidebar);
 sidebar.id='fp-sidebar';
 const mobileBar=document.createElement('div');mobileBar.className='mobile-toolbar';
 const mobileButton=document.createElement('button');mobileButton.type='button';mobileButton.className='outlined mobile-menu-button';mobileButton.textContent='☰ Menu';mobileButton.setAttribute('aria-controls','fp-sidebar');mobileButton.setAttribute('aria-expanded','false');
 const mobileTitle=document.createElement('strong');mobileTitle.textContent='FinanceiroPro Web';mobileBar.append(mobileButton,mobileTitle);app.prepend(mobileBar);
 const closeMenu=document.createElement('button');closeMenu.type='button';closeMenu.className='outlined mobile-menu-close';closeMenu.textContent='Fechar menu ✕';sidebar.prepend(closeMenu);
 const shade=document.createElement('button');shade.type='button';shade.className='mobile-menu-shade';shade.setAttribute('aria-label','Fechar menu');shade.hidden=true;app.prepend(shade);
 const mobileMedia=matchMedia('(max-width:760px)');let drawerOpen=false;
 function setDrawer(open,focus=false){drawerOpen=Boolean(open&&mobileMedia.matches);document.body.classList.toggle('mobile-nav-open',drawerOpen);mobileButton.setAttribute('aria-expanded',String(drawerOpen));sidebar.inert=mobileMedia.matches&&!drawerOpen;shade.hidden=!drawerOpen;document.body.style.overflow=drawerOpen?'hidden':'';if(focus)(drawerOpen?closeMenu:mobileButton).focus();}
 mobileButton.addEventListener('click',()=>setDrawer(!drawerOpen,true));closeMenu.addEventListener('click',()=>setDrawer(false,true));shade.addEventListener('click',()=>setDrawer(false,true));
 document.addEventListener('fp:close-menu',()=>setDrawer(false));mobileMedia.addEventListener('change',()=>setDrawer(false));setDrawer(false);
 document.addEventListener('keydown',event=>{if(!drawerOpen)return;if(event.key==='Escape'){event.preventDefault();setDrawer(false,true);}if(event.key==='Tab'){const focusable=[...sidebar.querySelectorAll('button:not([disabled])')].filter(b=>!b.hidden&&!b.classList.contains('hidden')),first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}});
 const updateMobileTitle=()=>{const active=nav?.querySelector('.view-active');mobileTitle.textContent=active?active.textContent.replace(/^[^\p{L}]+/u,''):'FinanceiroPro Web';};if(nav)new MutationObserver(updateMobileTitle).observe(nav,{subtree:true,attributes:true,attributeFilter:['class']});updateMobileTitle();
 const welcome=document.querySelector('.welcome>div');if(welcome){const eyebrow=document.createElement('div');eyebrow.className='eyebrow';eyebrow.textContent='Seu espaço financeiro';welcome.prepend(eyebrow);}
 for(const [id,label,note]of [['income','Receitas','Entradas do período'],['expense','Despesas','Compromissos do período'],['balance','Saldo do período','Receitas menos despesas'],['efficiency','Eficiência','Saldo em relação às receitas']]){const value=document.getElementById(id),card=value?.closest('.kpi');if(!card)continue;card.querySelector('.kpi-title').textContent=label;const small=document.createElement('span');small.className='kpi-note';small.textContent=note;card.append(small);}
 for(const h of document.querySelectorAll('.heading h2'))h.textContent=h.textContent.replace(/^[^\p{L}\p{N}]+/u,'');
 const status=document.getElementById('status');
 const idleLimit=2*60*60*1000,activityKey='fp-last-activity';let lastActivity=Date.now(),lastSaved=0,expiring=false;
 try{const stored=Number(localStorage.getItem(activityKey));if(stored>0&&stored<=Date.now())lastActivity=stored;}catch{}
 const readActivity=()=>{try{const saved=Number(localStorage.getItem(activityKey));if(saved>lastActivity&&saved<=Date.now())lastActivity=saved;}catch{}return lastActivity;};
 const checkIdle=()=>{if(expiring||app.classList.contains('hidden'))return false;if(Date.now()-readActivity()<idleLimit)return false;expiring=true;app.classList.add('hidden');document.body.classList.remove('signed-in');document.dispatchEvent(new Event('fp:session-reset'));accountForm.reset();if(dialog.open)dialog.close();fetch('/api/logout',{method:'POST',credentials:'same-origin'}).catch(()=>{}).finally(()=>location.replace('/app?motivo=inatividade'));return true;};
 const activity=event=>{if(!event.isTrusted||app.classList.contains('hidden')||checkIdle())return;lastActivity=Date.now();if(lastActivity-lastSaved>=15000){lastSaved=lastActivity;try{localStorage.setItem(activityKey,String(lastActivity));}catch{}}};
 for(const name of ['pointerdown','pointermove','keydown','wheel','touchstart'])document.addEventListener(name,activity,{capture:true,passive:true});
 document.addEventListener('visibilitychange',checkIdle);window.addEventListener('focus',checkIdle);window.addEventListener('pageshow',checkIdle);window.addEventListener('storage',event=>{if(event.key===activityKey)checkIdle();});setInterval(checkIdle,15000);
 new MutationObserver(checkIdle).observe(app,{attributes:true,attributeFilter:['class']});
 if(new URLSearchParams(location.search).get('motivo')==='inatividade'){const error=document.getElementById('login-error');if(error){error.textContent='Sua sessão foi encerrada após duas horas sem atividade. Entre novamente com usuário e senha.';error.classList.remove('hidden');}}
 checkIdle();
 if(nav)nav.insertBefore(account,nav.querySelector('.theme-toggle'));
 const sync=()=>{const logged=!app.classList.contains('hidden');document.body.classList.toggle('signed-in',logged);if(status&&/Homologação|Versão de testes|Finanças reais em consulta|Financeiro em leitura/.test(status.textContent))status.textContent=logged?'Sessão protegida · Dados sincronizados':'Seu financeiro, em um só lugar';};
 new MutationObserver(sync).observe(app,{attributes:true,attributeFilter:['class']});if(status)new MutationObserver(sync).observe(status,{childList:true,characterData:true,subtree:true});sync();
 const recordHelp=document.querySelector('.record-title p');if(recordHelp)recordHelp.textContent='Explore seu extrato ou abra um módulo para gerenciar seus registros.';
 const periodHelp=document.querySelector('.records .help');if(periodHelp)periodHelp.textContent='Crédito segue o mês da fatura; os demais meios seguem a data do lançamento. A mesma regra vale para os relatórios.';
 const footer=document.querySelector('footer');if(footer)footer.textContent='FinanceiroPro Web · Organize hoje. Planeje o próximo passo.';
})();
`;

