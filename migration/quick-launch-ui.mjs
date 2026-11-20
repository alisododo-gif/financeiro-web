// Progressive disclosure over the existing financial form and validated save path.
export const quickLaunchUI=String.raw`
function simplifyLaunch(form,actions,submit,fixedLabel,fixedChoice,hint){
 const get=name=>form.elements.namedItem(name),wrap=name=>get(name).closest('label');
 form.classList.add('quick-launch');form.noValidate=true;let step=0;
 const heading=node('p'),pages=[node('section'),node('section'),node('section')];heading.className='quick-progress';heading.setAttribute('role','status');
 pages.forEach(p=>p.className='quick-page');const summary=node('div');summary.className='quick-review';pages[2].append(summary);
 function choices(name,options){const input=get(name),box=node('div');box.className='quick-choices';box.setAttribute('role','group');box.setAttribute('aria-label',wrap(name).firstChild.textContent);input.hidden=true;
  for(const [value,label]of options){const b=node('button',label);b.type='button';b.dataset.value=String(value);b.onclick=()=>{input.value=String(value);input.dispatchEvent(new Event('change',{bubbles:true}));};box.append(b);}
  wrap(name).append(box);input.addEventListener('change',()=>{for(const b of box.children)b.setAttribute('aria-pressed',String(b.dataset.value===input.value));});return box;
 }
 get('tipo').value='';get('valor').value='';get('valor').min='0.01';get('valor').inputMode='decimal';get('descricao').maxLength=140;get('descricao').placeholder='Ex.: mercado, salário, aluguel';get('categoria').value='Outros';
 wrap('valor').firstChild.textContent='Valor (R$)';get('valor').placeholder='10 = R$ 10,00';
 const valueActions=node('div');valueActions.className='quick-value-actions';
 const changeValue=direction=>{const field=get('valor'),cents=Math.round((Number(field.value)||0)*100);field.value=(Math.min(100000000,Math.max(0,cents+direction*1000))/100).toFixed(2);field.dispatchEvent(new Event('input',{bubbles:true}));};
 for(const [text,direction]of [['− R$ 10',-1],['+ R$ 10',1]]){const b=node('button',text);b.type='button';b.className='outlined';b.onclick=()=>changeValue(direction);valueActions.append(b);}wrap('valor').append(valueActions);
 get('valor').addEventListener('keydown',e=>{if(e.key==='ArrowUp'||e.key==='ArrowDown'){e.preventDefault();changeValue(e.key==='ArrowUp'?1:-1);}});
 const categoryOptions=node('div');categoryOptions.className='quick-category-options';
 for(const text of ['Outros','Cartão de Crédito','Moradia','Outra categoria']){const b=node('button',text);b.type='button';b.className='outlined';b.onclick=()=>{get('categoria').value=text==='Outra categoria'?'':text;get('categoria').dispatchEvent(new Event('input',{bubbles:true}));if(text==='Outra categoria')get('categoria').focus();};categoryOptions.append(b);}wrap('categoria').append(categoryOptions);get('categoria').placeholder='Ou escreva sua categoria';
 const kinds=choices('tipo',[['Despesa','↓ Despesa'],['Receita','↑ Receita']]);
 const methods=choices('forma_pagamento',[['Pix','Pix'],['Cartão de Débito','Débito'],['Boleto','Boleto'],['Cartão de Crédito','Crédito'],['Dinheiro','Dinheiro']]);
 choices('modalidade',[['Único','Uma vez'],['Parcelado','Parcelado'],['Fixo / Recorrente','Fixo / recorrente']]);wrap('modalidade').firstChild.textContent='Repetição';
 for(const name of ['conta_id','cartao_id']){const input=get(name),options=[...input.options].filter(o=>o.value);choices(name,options.map(o=>[o.value,o.text]));if(options.length===1)input.value=options[0].value;}
 pages[0].append(wrap('tipo'),wrap('valor'),wrap('descricao'));
 pages[1].append(wrap('forma_pagamento'),wrap('conta_id'),wrap('cartao_id'),wrap('modalidade'),fixedLabel,wrap('quantidade'),hint);
 pages[1].append(wrap('categoria'));const details=node('details'),caption=node('summary','Data e tags');details.className='quick-details';details.append(caption,wrap('data'),wrap('tags'));pages[1].append(details);
 const back=node('button','Voltar'),next=node('button','Continuar');back.type=next.type='button';back.className='outlined';actions.prepend(back);actions.append(next);submit.textContent='Confirmar e salvar';
 form.prepend(heading,...pages);
 function sync(){const income=get('tipo').value==='Receita',credit=get('forma_pagamento').value==='Cartão de Crédito';
  const creditButton=[...methods.children].find(b=>b.dataset.value==='Cartão de Crédito');creditButton.hidden=income;
  if(income&&credit){get('forma_pagamento').value='Pix';get('forma_pagamento').dispatchEvent(new Event('change',{bubbles:true}));return;}
  const modeButtons=wrap('modalidade').querySelector('.quick-choices');modeButtons.children[1].hidden=!credit;
  if(!credit&&get('modalidade').value==='Parcelado'){get('modalidade').value='Único';get('modalidade').dispatchEvent(new Event('change',{bubbles:true}));return;}
  for(const name of ['tipo','forma_pagamento','modalidade','conta_id','cartao_id']){const input=get(name);for(const b of wrap(name).querySelector('.quick-choices').children)b.setAttribute('aria-pressed',String(b.dataset.value===input.value));}
 }
 function check(names){for(const name of names){const field=get(name);if(!field.checkValidity()){notify('Confira '+wrap(name).firstChild.textContent.trim()+'.');if(!field.hidden)field.focus();return false;}}return true;}
 function render(){formDialog.querySelector('.modal-status')?.remove();sync();pages.forEach((p,i)=>p.hidden=i!==step);heading.textContent=['1 de 3 · O que você quer lançar?','2 de 3 · Como será o pagamento?','3 de 3 · Confira e confirme'][step];back.hidden=step===0;next.hidden=step===2;submit.hidden=step!==2;
  if(step===2){summary.replaceChildren();const credit=get('forma_pagamento').value==='Cartão de Crédito',ref=get(credit?'cartao_id':'conta_id'),count=Number(get('quantidade').value),value=Number(get('valor').value),each=get('modalidade').value==='Parcelado'?roundInstallment(value,count):value;
   for(const [label,value]of [['Tipo',get('tipo').value],['Descrição',get('descricao').value],['Valor',money(Number(get('valor').value))],['Pagamento',get('forma_pagamento').value],['Destino',ref.selectedOptions[0]?.text],['Data',get('data').value.split('-').reverse().join('/')],['Categoria',get('categoria').value],['Repetição',count+' lançamento(s) de '+money(each)],['Situação','Pendente']]){const p=node('p');p.append(node('span',label),node('strong',value));summary.append(p);}
   if(count>1){const total=node('p');total.append(node('span','Total dos lançamentos'),node('strong',money(Math.round(each*100)*count/100)));summary.append(total);}
  }
 }
 function advance(){if(step===0&&!check(['tipo','valor','descricao']))return;if(step===1&&!check(['forma_pagamento',get('forma_pagamento').value==='Cartão de Crédito'?'cartao_id':'conta_id','modalidade','quantidade','data','categoria']))return;step=Math.min(2,step+1);render();formDialog.scrollTop=0;}
 next.onclick=advance;back.onclick=()=>{step=Math.max(0,step-1);render();formDialog.scrollTop=0;};
 form.addEventListener('submit',event=>{if(step<2){event.preventDefault();event.stopImmediatePropagation();advance();}},{capture:true,signal:quickLaunchAbort.signal});
 form.addEventListener('change',sync,{signal:quickLaunchAbort.signal});sync();render();
}
let quickLaunchAbort=new AbortController();
`;

