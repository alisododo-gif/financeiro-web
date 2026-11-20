// Shared by the standalone financial page and the embedded shadow panel.
export const modalHelpers=String.raw`
async function ask(message,title='Confirmar operação'){
 const dialog=node('dialog');dialog.className='fp-dialog fp-confirm';dialog.setAttribute('aria-label',title);
 const heading=node('h2',title),text=node('p',message),actions=node('div');actions.className='account-actions';
 const cancel=node('button','Cancelar'),accept=node('button','Confirmar');cancel.type=accept.type='button';cancel.className='outlined';
 actions.append(cancel,accept);dialog.append(heading,text,actions);$('form').closest('main').append(dialog);
 return new Promise(resolve=>{let settled=false;const done=value=>{if(settled)return;settled=true;dialog.close();dialog.remove();resolve(value);};cancel.onclick=()=>done(false);accept.onclick=()=>done(true);dialog.addEventListener('cancel',e=>{e.preventDefault();done(false);});dialog.addEventListener('close',()=>done(false));dialog.showModal();cancel.focus();});
}
async function askAmount(title){
 const d=node('dialog');d.className='fp-dialog fp-confirm';d.setAttribute('aria-label',title);const f=node('form'),label=node('label','Valor'),input=node('input'),actions=node('div');input.type='number';input.min='0.01';input.max='1000000';input.step='0.01';input.required=true;input.value='100';label.append(input);actions.className='account-actions';const cancel=node('button','Cancelar'),save=node('button','Confirmar');cancel.type='button';save.type='submit';actions.append(cancel,save);f.append(node('h2',title),node('p','Atualiza o progresso da meta, sem transferência bancária.'),label,actions);d.append(f);$('form').closest('main').append(d);
 return new Promise(resolve=>{let settled=false;const done=value=>{if(settled)return;settled=true;d.close();d.remove();resolve(value);};cancel.onclick=()=>done(null);f.onsubmit=e=>{e.preventDefault();if(f.reportValidity())done(input.value);};d.addEventListener('cancel',e=>{e.preventDefault();done(null);});d.addEventListener('close',()=>done(null));d.showModal();input.focus();});
}
`;

