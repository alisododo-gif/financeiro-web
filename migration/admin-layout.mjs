export const adminLayout=String.raw`
const tabbar=node('div');tabbar.className='admin-tabs';tabbar.setAttribute('role','tablist');tabbar.setAttribute('aria-label','Administração');
const panes={};let tabIndex=0;
for(const [key,label]of [['clients','Clientes do sistema'],['plans','Planos e teste de 7 dias'],['users','Acesso por usuário'],['backup','Cópia de segurança']]){
 const tab=node('button',label),pane=node('section');tab.type='button';tab.id='admin-tab-'+key;tab.setAttribute('role','tab');tab.setAttribute('aria-controls','admin-pane-'+key);pane.id='admin-pane-'+key;pane.setAttribute('role','tabpanel');pane.setAttribute('aria-labelledby',tab.id);panes[key]=pane;tabbar.append(tab);admin.append(pane);
 const activate=()=>{for(const b of tabbar.children){const selected=b===tab;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;panes[b.id.replace('admin-tab-','')].hidden=!selected;}};
 tab.onclick=activate;if(tabIndex++===0)activate();else{tab.setAttribute('aria-selected','false');tab.tabIndex=-1;pane.hidden=true;}
 tab.onkeydown=e=>{const buttons=[...tabbar.children],i=buttons.indexOf(tab);let next;if(e.key==='ArrowRight')next=buttons[(i+1)%buttons.length];if(e.key==='ArrowLeft')next=buttons[(i+buttons.length-1)%buttons.length];if(e.key==='Home')next=buttons[0];if(e.key==='End')next=buttons.at(-1);if(next){e.preventDefault();next.click();next.focus();}};
}
admin.prepend(tabbar);const adminSearch=document.getElementById('admin-search');if(adminSearch)adminSearch.closest('label').hidden=true;
for(const el of [...admin.children])if(el!==tabbar&&!Object.values(panes).includes(el))panes.clients.append(el);
panes.plans.append(panel);const userPanel=node('article');userPanel.className='card access-admin';panes.users.append(userPanel);
const backup=document.getElementById('backup-card');if(backup)panes.backup.append(backup);
function popupSection(section,title,buttonText){if(!section)return;const launch=node('button',buttonText),dialog=node('dialog');launch.type='button';dialog.className='fp-dialog';dialog.setAttribute('aria-label',title);section.before(launch);document.body.append(dialog);dialog.append(section);const cancel=node('button','Fechar');cancel.type='button';cancel.className='outlined';const form=section.querySelector('form'),submit=form?.querySelector('button[type=submit]');if(submit){const actions=node('div');actions.className='account-actions';actions.append(cancel,submit);form.append(actions);}else section.append(cancel);cancel.onclick=()=>dialog.close();launch.onclick=()=>dialog.showModal();return dialog;}
popupSection(document.getElementById('admin-create-form')?.closest('article'),'Cadastrar usuário','Novo usuário');
popupSection(backup,'Cópia de segurança','Abrir cópia de segurança');
`;
export const globalDialog=String.raw`
window.fpDialog=(message,initial)=>new Promise(resolve=>{
 const d=document.createElement('dialog');d.className='fp-dialog fp-confirm';d.setAttribute('aria-label','Confirmar operação');const h=document.createElement('h2');h.textContent=initial===undefined?'Confirmar operação':'Atualizar cadastro';const p=document.createElement('p');p.textContent=message;d.append(h,p);let input;
 if(initial!==undefined){const label=document.createElement('label');label.textContent='Valor';input=document.createElement('input');input.type='text';input.value=initial??'';input.maxLength=240;label.append(input);d.append(label);}
 const actions=document.createElement('div');actions.className='account-actions';let done=false;const finish=value=>{if(done)return;done=true;d.close();d.remove();resolve(value);};for(const [text,accept]of [['Cancelar',false],['Confirmar',true]]){const b=document.createElement('button');b.type='button';b.textContent=text;b.className=accept?'':'outlined';b.onclick=()=>finish(accept?(input?input.value:true):(input?null:false));actions.append(b);}d.append(actions);d.addEventListener('cancel',e=>{e.preventDefault();finish(input?null:false);});d.addEventListener('close',()=>finish(input?null:false));document.body.append(d);d.showModal();(input||actions.firstChild).focus();
});
window.fpPrompt=(message,initial='')=>window.fpDialog(message,initial);
`;

