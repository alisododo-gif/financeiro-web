const dateValid=value=>typeof value==='string'&&/^20\d{2}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(value+'T00:00:00Z'))&&new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;
// Match round(float(valor) / parcelas, 2), including binary float ties.
export function roundInstallment(amount,count){
 const buffer=new ArrayBuffer(8),view=new DataView(buffer);view.setFloat64(0,amount/count);
 const bits=view.getBigUint64(0),exponent=Number((bits>>52n)&2047n)-1023-52;
 let numerator=((bits&((1n<<52n)-1n))|(1n<<52n))*100n,denominator=1n;
 if(exponent<0)denominator<<=BigInt(-exponent);else numerator<<=BigInt(exponent);
 let quotient=numerator/denominator;const twice=(numerator%denominator)*2n;
 if(twice>denominator||(twice===denominator&&quotient%2n===1n))quotient++;
 return Number(quotient)/100;
}
export function launchRows(d){
 if(!d||typeof d!=='object'||Array.isArray(d)||Object.keys(d).some(k=>!['descricao','valor','tipo','data','categoria','forma_pagamento','conta_id','cartao_id','tags','modalidade','quantidade'].includes(k)))throw Error('Campos de lançamento inválidos');
 if(!['Único','Parcelado','Fixo / Recorrente'].includes(d.modalidade)||!dateValid(d.data))throw Error('Modalidade ou data inválida');
 const count=Number(d.quantidade);if(!Number.isInteger(count)||count<1||count>(d.modalidade==='Único'?1:d.modalidade==='Parcelado'?72:60)||d.modalidade==='Parcelado'&&count<2)throw Error('Quantidade inválida');
 if(typeof d.valor!=='number'||!Number.isFinite(d.valor)||d.valor<=0||d.valor>1000000||Math.abs(d.valor*100-Math.round(d.valor*100))>0.00001)throw Error('Valor inválido');
 const totalCents=Math.round(d.valor*100),baseCents=Math.floor(totalCents/count),remainder=totalCents%count;const value=d.modalidade==='Parcelado'?baseCents/100:d.valor;if(value<=0)throw Error('Valor da parcela menor que um centavo');
 if(typeof d.descricao!=='string'||!d.descricao.trim()||d.descricao.length>140)throw Error('Descrição inválida');
 const [year,month,day]=d.data.split('-').map(Number);
 return Array.from({length:count},(_,i)=>{
  const m=(month+i-1)%12+1,y=year+Math.floor((month+i-1)/12);
  const data=count===1?d.data:y+'-'+String(m).padStart(2,'0')+'-'+String(Math.min(day,new Date(Date.UTC(y,m,0)).getUTCDate())).padStart(2,'0');
  return {descricao:d.descricao.trim()+(d.modalidade==='Parcelado'?' ('+(i+1)+'/'+count+')':d.modalidade==='Fixo / Recorrente'?' (Recorrente)':''),valor:d.modalidade==='Parcelado'?(baseCents+(i<remainder?1:0))/100:value,tipo:d.tipo,data,categoria:d.categoria,forma_pagamento:d.forma_pagamento,conta_id:d.conta_id??null,cartao_id:d.cartao_id??null,tags:d.tags?String(d.tags).split(',').map(s=>s.trim().replace(/^#+/,'')).filter(Boolean).map(s=>'#'+s).join(', '):null,pago:false};
 });
}

