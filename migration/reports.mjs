// Local downloads only: consume the already authenticated owner's records.
import {financialMonth} from './monthly.mjs';
export function reportData(rows,month){
 if(!/^20\d{2}-(0[1-9]|1[0-2])$/.test(month))throw Error('Selecione o mês do relatório.');
 const selected=rows.filter(r=>financialMonth(r)===month).sort((a,b)=>String(a.data).localeCompare(String(b.data))||Number(a.id)-Number(b.id));
 const sum=type=>selected.filter(r=>r.tipo===type).reduce((n,r)=>n+Math.round(Number(r.valor||0)*100),0)/100;
 return {month,rows:selected,income:sum('Receita'),expense:sum('Despesa'),balance:(Math.round(sum('Receita')*100)-Math.round(sum('Despesa')*100))/100};
}
export function reportXML(value){return String(value??'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
export function zipStore(files){
 const enc=new TextEncoder(),u16=n=>[n&255,(n>>>8)&255],u32=n=>[n&255,(n>>>8)&255,(n>>>16)&255,(n>>>24)&255];
 const crc=bytes=>{let c=0xffffffff;for(const b of bytes){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;};
 const chunks=[],central=[];let offset=0;
 for(const [name,text]of Object.entries(files)){const n=enc.encode(name),data=enc.encode(text),check=crc(data);const local=new Uint8Array([80,75,3,4,...u16(20),...u16(0x800),...u16(0),...u16(0),...u16(33),...u32(check),...u32(data.length),...u32(data.length),...u16(n.length),...u16(0),...n,...data]);chunks.push(local);central.push(new Uint8Array([80,75,1,2,...u16(20),...u16(20),...u16(0x800),...u16(0),...u16(0),...u16(33),...u32(check),...u32(data.length),...u32(data.length),...u16(n.length),...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(offset),...n]));offset+=local.length;}
 const size=central.reduce((s,c)=>s+c.length,0),end=new Uint8Array([80,75,5,6,...u16(0),...u16(0),...u16(central.length),...u16(central.length),...u32(size),...u32(offset),...u16(0)]);
 const out=new Uint8Array(offset+size+end.length);let pos=0;for(const c of [...chunks,...central,end]){out.set(c,pos);pos+=c.length;}return out;
}
export function reportMetrics(rows,month){
 const data=reportData(rows,month),categories=new Map();let paid=0,pending=0;
 for(const r of data.rows)if(r.tipo==='Despesa'){const cents=Math.round(Number(r.valor||0)*100),key=String(r.categoria||'Sem categoria');categories.set(key,(categories.get(key)||0)+cents);if(r.pago)paid+=cents;else pending+=cents;}
 return {...data,paid:paid/100,pending:pending/100,categories:[...categories].map(([name,cents])=>({name,value:cents/100})).sort((a,b)=>b.value-a.value||a.name.localeCompare(b.name))};
}
export function reportPeriod(month){return new Intl.DateTimeFormat('pt-BR',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(month+'-15T12:00:00Z'));}
export function reportAccount(row,refs){return (row.cartao_id?(refs.cards||[]).find(c=>Number(c.id)===Number(row.cartao_id))?.nome_cartao:(refs.accounts||[]).find(c=>Number(c.id)===Number(row.conta_id))?.nome)||'Não informado';}
export function reportColumn(i){let out='';for(i++;i;i=Math.floor((i-1)/26))out=String.fromCharCode(65+(i-1)%26)+out;return out;}
export function reportCell(ref,value,style=0,formula=null){const base='<c r="'+ref+'" s="'+style+'"';if(formula)return base+'><f>'+reportXML(formula)+'</f><v>'+Number(value||0)+'</v></c>';return typeof value==='number'&&Number.isFinite(value)?base+'><v>'+value+'</v></c>':base+' t="inlineStr"><is><t xml:space="preserve">'+reportXML(value)+'</t></is></c>';}
export function reportExcelDate(value){if(!/^20\d{2}-\d{2}-\d{2}$/.test(String(value)))return String(value||'');return Math.round((Date.parse(value+'T00:00:00Z')-Date.UTC(1899,11,30))/86400000);}
export function reportStyles(){
 const font=(size,color,bold=false)=>'<font><sz val="'+size+'"/><color rgb="FF'+color+'"/><name val="Aptos"/>'+(bold?'<b/>':'')+'</font>';
 const fonts=[font(10,'334155'),font(22,'FFFFFF',true),font(10,'B9D6DF'),font(16,'13253B',true),font(9,'64748B'),font(10,'52647A',true),font(24,'087F68',true),font(24,'BA4055',true),font(24,'163653',true),font(10,'FFFFFF',true),font(10,'087F68',true),font(10,'BA4055',true),font(11,'13253B',true)];
 const fills=['<fill><patternFill patternType="none"/></fill>','<fill><patternFill patternType="gray125"/></fill>',...['13253B','EFF9F5','FFF1F3','EEF4FB','F0F4F8'].map(c=>'<fill><patternFill patternType="solid"><fgColor rgb="FF'+c+'"/><bgColor indexed="64"/></patternFill></fill>')];
 const specs=[[0,0,0],[1,2,0],[2,2,0],[3,0,0],[4,0,0],[5,6,0],[6,3,164],[7,4,164],[8,5,164],[9,2,0],[0,0,164],[0,0,165],[10,0,0],[11,0,0],[12,6,164],[12,6,0]];
 const xfs=specs.map(([f,fill,num],i)=>'<xf numFmtId="'+num+'" fontId="'+f+'" fillId="'+fill+'" borderId="0" xfId="0" applyFont="1" applyFill="1" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center" wrapText="1" horizontal="'+([6,7,8,10,14].includes(i)?'right':'left')+'"/></xf>');
 return '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;R$&quot; #,##0.00;[Red](&quot;R$&quot; #,##0.00);&quot;R$&quot; 0.00"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy"/></numFmts><fonts count="'+fonts.length+'">'+fonts.join('')+'</fonts><fills count="'+fills.length+'">'+fills.join('')+'</fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="'+xfs.length+'">'+xfs.join('')+'</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
}
export function createMonthlyXLSX(rows,month,refs={}){
 const d=reportMetrics(rows,month),generated=new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Cuiaba'}).format(refs.generatedAt?new Date(refs.generatedAt):new Date()),last=Math.max(8,d.rows.length+7);
 const headers=['ID','Data financeira','Descrição','Tipo','Valor','Pagamento','Categoria','Situação','Mês da fatura','Cadastrado em','Conta / cartão','Tags'],details=[];
 const row=(index,cells,height=22)=>'<row r="'+index+'" ht="'+height+'" customHeight="1">'+cells.join('')+'</row>';
 details.push(row(1,[reportCell('A1','FinanceiroPro Web',1)],30),row(2,[reportCell('A2','EXTRATO DE MOVIMENTAÇÕES',2)],22),row(4,[reportCell('A4',reportPeriod(month),3)],28),row(5,[reportCell('A5','Crédito por fatura; demais por data. A competência do crédito consta em coluna própria.',4)],24),row(7,headers.map((v,j)=>reportCell(reportColumn(j)+'7',v,9)),32));
 for(let i=0;i<d.rows.length;i++){const r=d.rows[i],n=i+8,values=[r.id,reportExcelDate(r.data),r.descricao,r.tipo,Number(r.valor||0),r.forma_pagamento,r.categoria||'Sem categoria',r.pago?'Pago':'Pendente',r.mes_fatura||'',r.created_at?new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Cuiaba'}).format(new Date(r.created_at)):'Não informado no histórico',reportAccount(r,refs),r.tags||''];const height=Math.min(150,Math.max(36,Math.ceil(String(r.descricao||'').length/48)*14+12,Math.ceil(String(r.tags||'').length/28)*14+12,Math.ceil(String(r.categoria||'').length/24)*14+12));details.push(row(n,values.map((v,j)=>reportCell(reportColumn(j)+n,v,j===1?11:j===4?10:j===7?r.pago?12:13:0)),height));}
 if(!d.rows.length)details.push(row(8,[reportCell('C8','Nenhum lançamento no período.',4)],32));
 const ranges={value:"'Lançamentos'!$E$8:$E$"+last,type:"'Lançamentos'!$D$8:$D$"+last,category:"'Lançamentos'!$G$8:$G$"+last,status:"'Lançamentos'!$H$8:$H$"+last};
 const summary=[],merges=['A1:L2','A4:L4','A5:L5','A7:D7','E7:H7','I7:L7','A8:D10','E8:H10','I8:L10','A12:F12','G12:L12','A14:F14','G14:L14','A16:D16','G16:L16','G18:J18','K18:L18'];
 const add=(n,cells,h)=>summary.push(row(n,cells,h));
 add(1,[reportCell('A1','FinanceiroPro Web',1)],32);add(2,[],20);add(4,[reportCell('A4','Relatório mensal · '+reportPeriod(month),3)],30);add(5,[reportCell('A5','Emitido em '+generated+' · Valores em reais (BRL)',4)],24);
 add(7,[reportCell('A7','RECEITAS',5),reportCell('E7','DESPESAS',5),reportCell('I7','SALDO DO PERÍODO',5)],24);
 add(8,[reportCell('A8',d.income,6,'SUMIF('+ranges.type+',"Receita",'+ranges.value+')'),reportCell('E8',d.expense,7,'SUMIF('+ranges.type+',"Despesa",'+ranges.value+')'),reportCell('I8',d.balance,8,'A8-E8')],24);add(9,[],20);add(10,[],20);
 add(12,[reportCell('A12',d.rows.length+' lançamentos no período',4),reportCell('G12','Crédito: mês da fatura; demais: data',4)],24);
 add(14,[reportCell('A14','DESPESAS POR CATEGORIA',15),reportCell('G14','SITUAÇÃO DAS DESPESAS',15)],28);
 add(16,[reportCell('A16','Categoria',9),reportCell('E16','Valor',9),reportCell('G16','Resumo de pagamento',9)],26);
 const categoryStart=18,categoryEnd=categoryStart+Math.max(1,d.categories.length)-1;
 for(let i=0;i<Math.max(3,d.categories.length);i++){const n=categoryStart+i,c=d.categories[i],cells=[];if(c){merges.push('A'+n+':D'+n);cells.push(reportCell('A'+n,c.name),reportCell('E'+n,c.value,10,'SUMIFS('+ranges.value+','+ranges.type+',"Despesa",'+ranges.category+',SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(A'+n+',"~","~~"),"*","~*"),"?","~?"))'));}else if(!d.categories.length&&i===0){cells.push(reportCell('A'+n,'Sem despesas no período.',4));}
 if(i===0)cells.push(reportCell('G'+n,'Quitadas',12),reportCell('K'+n,d.paid,10,'SUMIFS('+ranges.value+','+ranges.type+',"Despesa",'+ranges.status+',"Pago")'));
 if(i===1)cells.push(reportCell('G'+n,'Pendentes',13),reportCell('K'+n,d.pending,10,'SUMIFS('+ranges.value+','+ranges.type+',"Despesa",'+ranges.status+',"Pendente")'));
 if(i===2)cells.push(reportCell('G'+n,'Total de despesas',15),reportCell('K'+n,d.expense,14,'E8'));
 if(i<3){if(i>0)merges.push('G'+n+':J'+n,'K'+n+':L'+n);}add(n,cells,c?Math.max(28,Math.ceil(c.name.length/42)*15+10):28);}
 const note=categoryStart+Math.max(3,d.categories.length)+3;merges.push('A'+note+':L'+note,'A'+(note+1)+':L'+(note+1));
 add(note,[reportCell('A'+note,'Consulte a aba Lançamentos para o extrato completo. Use os filtros e mantenha o cabeçalho fixo durante a leitura.',4)],28);add(note+1,[reportCell('A'+(note+1),'Compras no crédito seguem a data financeira neste relatório. O mês da fatura é apresentado separadamente.',4)],28);
 const worksheet=(body,columns,extra='')=>'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'+body+extra+'</worksheet>';
 const view='<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews><sheetFormatPr defaultRowHeight="22"/>';
 const footer='<headerFooter><oddFooter>&amp;LFinanceiroPro Web&amp;C'+reportXML(reportPeriod(month))+'&amp;RPágina &amp;P de &amp;N</oddFooter></headerFooter>';
 const margins='<pageMargins left="0.3" right="0.3" top="0.4" bottom="0.4" header="0.15" footer="0.2"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>';
 const sumSheet=worksheet('<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:L'+(note+1)+'"/>'+view+'<cols><col min="1" max="4" width="12" customWidth="1"/><col min="5" max="5" width="22" customWidth="1"/><col min="6" max="6" width="4" customWidth="1"/><col min="7" max="10" width="11" customWidth="1"/><col min="11" max="12" width="12" customWidth="1"/></cols><sheetData>'+summary.join('')+'</sheetData><mergeCells count="'+merges.length+'">'+merges.map(r=>'<mergeCell ref="'+r+'"/>').join('')+'</mergeCells>'+(d.categories.length?'<conditionalFormatting sqref="E'+categoryStart+':E'+categoryEnd+'"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FF38C6A3"/></dataBar></cfRule></conditionalFormatting>':'')+margins+footer);
 const widths=[9,16,48,14,19,22,26,16,18,25,26,30],dataSheet=worksheet('<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:L'+last+'"/><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="7" topLeftCell="A8" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="36"/><cols>'+widths.map((w,i)=>'<col min="'+(i+1)+'" max="'+(i+1)+'" width="'+w+'" customWidth="1"/>').join('')+'</cols><sheetData>'+details.join('')+'</sheetData><mergeCells count="4"><mergeCell ref="A1:L1"/><mergeCell ref="A2:L2"/><mergeCell ref="A4:L4"/><mergeCell ref="A5:L5"/></mergeCells>'+margins+footer+'<tableParts count="1"><tablePart r:id="rId1"/></tableParts>');
 const mainNS='http://schemas.openxmlformats.org',ct='application/vnd.openxmlformats-officedocument.spreadsheetml.';
 return zipStore({
 '[Content_Types].xml':'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="'+ct+'sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="'+ct+'worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="'+ct+'worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="'+ct+'styles+xml"/><Override PartName="/xl/tables/table1.xml" ContentType="'+ct+'table+xml"/></Types>',
 '_rels/.rels':'<?xml version="1.0"?><Relationships xmlns="'+mainNS+'/package/2006/relationships"><Relationship Id="rId1" Type="'+mainNS+'/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
 'xl/workbook.xml':'<?xml version="1.0"?><workbook xmlns="'+mainNS+'/spreadsheetml/2006/main" xmlns:r="'+mainNS+'/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets><sheet name="Resumo" sheetId="1" r:id="rId1"/><sheet name="Lançamentos" sheetId="2" r:id="rId2"/></sheets><definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Resumo!$A$1:$L$'+(note+1)+'</definedName><definedName name="_xlnm.Print_Area" localSheetId="1">\'Lançamentos\'!$A$1:$L$'+last+'</definedName><definedName name="_xlnm.Print_Titles" localSheetId="1">\'Lançamentos\'!$1:$7</definedName></definedNames><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>',
 'xl/_rels/workbook.xml.rels':'<?xml version="1.0"?><Relationships xmlns="'+mainNS+'/package/2006/relationships"><Relationship Id="rId1" Type="'+mainNS+'/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="'+mainNS+'/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="'+mainNS+'/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
 'xl/styles.xml':reportStyles(),'xl/worksheets/sheet1.xml':sumSheet,'xl/worksheets/sheet2.xml':dataSheet,
 'xl/worksheets/_rels/sheet2.xml.rels':'<?xml version="1.0"?><Relationships xmlns="'+mainNS+'/package/2006/relationships"><Relationship Id="rId1" Type="'+mainNS+'/officeDocument/2006/relationships/table" Target="../tables/table1.xml"/></Relationships>',
 'xl/tables/table1.xml':'<?xml version="1.0"?><table xmlns="'+mainNS+'/spreadsheetml/2006/main" id="1" name="Lancamentos" displayName="Lancamentos" ref="A7:L'+last+'" totalsRowShown="0"><autoFilter ref="A7:L'+last+'"/><tableColumns count="12">'+headers.map((v,i)=>'<tableColumn id="'+(i+1)+'" name="'+reportXML(v)+'"/>').join('')+'</tableColumns><tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>'
 });
}
export function reportTextWidth(value,size){return [...String(value)].reduce((sum,c)=>sum+(/[ilI.,:;'!|]/.test(c)?.25:/[MW@%]/.test(c)?.88:/\s/.test(c)?.28:/[A-ZÀ-Ý0-9]/.test(c)?.6:.53)*size,0);}
export function reportWrap(value,width,size){const words=String(value??'').replace(/\s+/g,' ').trim().split(' '),lines=[];let line='';for(let word of words){if(!word)continue;while(reportTextWidth(word,size)>width){let part='';while(word.length&&reportTextWidth(part+word[0],size)<=width){part+=word[0];word=word.slice(1);}if(line){lines.push(line);line='';}lines.push(part||word.slice(0,1));if(!part)word=word.slice(1);}if(reportTextWidth(line+(line?' ':'')+word,size)>width){lines.push(line);line=word;}else line+=(line?' ':'')+word;}if(line)lines.push(line);return lines.length?lines:[''];}
export function createMonthlyPDF(rows,month,refs={}){
 const d=reportMetrics(rows,month),br=n=>Number(n).toLocaleString('pt-BR',{style:'currency',currency:'BRL'}),period=reportPeriod(month),generated=new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Cuiaba'}).format(refs.generatedAt?new Date(refs.generatedAt):new Date());
 const colors={navy:[.074,.145,.231],ink:[.14,.21,.3],muted:[.39,.46,.55],teal:[.03,.5,.41],red:[.73,.25,.33],line:[.86,.9,.93],light:[.96,.974,.985]},pages=[];let ops=[];
 const clean=s=>String(s).replace(/[–—]/g,'-').replace(/[‘’]/g,"'").replace(/[“”]/g,'"').replace(/[^\x20-\xff]/g,' ').replace(/([\\()])/g,'\\$1');
 const color=(c,stroke=false)=>(Array.isArray(c)?c:colors[c]).join(' ')+(stroke?' RG':' rg');
 const rect=(x,y,w,h,c)=>ops.push(color(c)+' '+x+' '+y+' '+w+' '+h+' re f');
 const text=(value,x,y,size=10,c='ink',bold=false,align='left')=>{if(align==='right')x-=reportTextWidth(value,size);ops.push(color(c)+' BT /'+(bold?'F2':'F1')+' '+size+' Tf 1 0 0 1 '+x.toFixed(2)+' '+y.toFixed(2)+' Tm ('+clean(value)+') Tj ET');};
 const line=(x,y,x2,y2)=>ops.push(color('line',true)+' 0.6 w '+x+' '+y+' m '+x2+' '+y2+' l S');
 const header=(label)=>{ops=[];rect(0,537,842,58,'navy');rect(34,553,5,14,'teal');rect(42,553,5,21,'teal');rect(50,553,5,29,'teal');text('FinanceiroPro Web',66,559,18,[1,1,1],true);text(label,808,562,9,[.68,.87,.85],true,'right');text(period.charAt(0).toUpperCase()+period.slice(1),34,509,22,'navy',true);text('Emitido em '+generated,808,510,8,'muted',false,'right');};
 const finish=()=>{line(34,39,808,39);text('FinanceiroPro Web · Relatório mensal',34,24,8,'muted');pages.push(ops);};
 header('RELATÓRIO MENSAL');
 const kpis=[['RECEITAS',d.income,'teal',[.93,.98,.96]],['DESPESAS',d.expense,'red',[1,.945,.95]],['SALDO DO PERÍODO',d.balance,'navy',[.93,.96,.99]]];
 kpis.forEach(([label,value,c,bg],i)=>{const x=34+i*262;rect(x,408,250,68,bg);text(label,x+16,453,9,'muted',true);text(br(value),x+16,425,24,c,true);});
 text(d.rows.length+' lançamentos no período',34,388,9,'muted');text('Crédito por fatura; demais por data',808,388,9,'muted',false,'right');
 rect(34,132,456,230,'light');text('Despesas por categoria',50,338,13,'navy',true);
 const top=d.categories.slice(0,5);if(d.categories.length>5)top.push({name:'Demais categorias',value:d.categories.slice(5).reduce((s,c)=>s+Math.round(c.value*100),0)/100});
 if(!top.length)text('Nenhuma despesa neste período.',50,303,10,'muted');
 top.forEach((c,i)=>{const y=310-i*29,label=c.name.length>64?c.name.slice(0,61)+'...':c.name;text(label,50,y,8.5,'ink');text(br(c.value),474,y,8.5,'ink',true,'right');rect(50,y-13,424,5,[.86,.91,.94]);rect(50,y-13,424*(d.expense?c.value/d.expense:0),5,'teal');});
 rect(510,132,298,230,'light');text('Situação das despesas',526,338,13,'navy',true);
 text('Quitadas',526,305,10,'muted');text(br(d.paid),792,305,13,'teal',true,'right');line(526,289,792,289);
 text('Pendentes',526,265,10,'muted');text(br(d.pending),792,265,13,'red',true,'right');line(526,249,792,249);
 text('Total de despesas',526,225,10,'muted');text(br(d.expense),792,225,13,'navy',true,'right');
 text('Receitas e despesas incluem os registros',526,180,8.5,'muted');text('pagos e pendentes do mês selecionado.',526,167,8.5,'muted');
 text('Crédito segue o mês da fatura; Pix, débito, boleto e dinheiro seguem a data do lançamento.',34,101,9,'muted');
 text(d.rows.length?'O extrato completo está nas páginas seguintes.':'Nenhum lançamento neste mês.',34,83,10,'navy',true);finish();
 const xs=[34,92,392,454,560,660,726,808];
 const tableHeader=()=>{rect(34,457,774,25,'navy');['Data','Descrição / detalhes','Tipo','Categoria','Conta / cartão','Situação','Valor'].forEach((v,i)=>text(v,i===6?800:xs[i]+8,466,8,[1,1,1],true,i===6?'right':'left'));};
 let y=457,index=0;
 if(d.rows.length){header('EXTRATO FINANCEIRO');text('Movimentações do período',34,490,9,'muted');tableHeader();}
 for(const r of d.rows){
  const primary=reportWrap(r.descricao||'Sem descrição',284,8.5),meta=['#'+r.id,r.forma_pagamento,r.mes_fatura?'Fatura '+r.mes_fatura:null,r.tags?'Tags: '+r.tags:null].filter(Boolean).join(' · '),secondary=reportWrap(meta,284,7.2),cat=reportWrap(r.categoria||'Sem categoria',90,8),account=reportWrap(reportAccount(r,refs),84,8);
  const height=Math.max(36,(primary.length+secondary.length)*11+12,cat.length*11+14,account.length*11+14);
  if(y-height<58){finish();header('EXTRATO FINANCEIRO');text('Movimentações do período · continuação',34,490,9,'muted');tableHeader();y=457;}
  if(index++%2===0)rect(34,y-height,774,height,'light');line(34,y-height,808,y-height);
  text(String(r.data||'').split('-').reverse().join('/'),42,y-16,8);
  primary.forEach((v,i)=>text(v,100,y-15-i*11,8.5,'ink',true));secondary.forEach((v,i)=>text(v,100,y-15-(primary.length+i)*11,7.2,'muted'));
  text(r.tipo,xs[2]+8,y-16,8,r.tipo==='Receita'?'teal':'red');cat.forEach((v,i)=>text(v,xs[3]+8,y-16-i*11,8));account.forEach((v,i)=>text(v,xs[4]+8,y-16-i*11,8));
  text(r.pago?'Pago':'Pendente',xs[5]+8,y-16,8,r.pago?'teal':'red');text(br(r.valor),800,y-16,8.5,'ink',true,'right');y-=height;
 }
 if(d.rows.length){if(y<118){finish();header('EXTRATO FINANCEIRO');y=475;}rect(34,y-49,774,34,'navy');text('Saldo do período',50,y-36,10,[1,1,1],true);text(br(d.balance),792,y-36,12,[1,1,1],true,'right');finish();}
 pages.forEach((p,i)=>p.push(color('muted')+' BT /F1 8 Tf 1 0 0 1 740 24 Tm (Página '+(i+1)+' de '+pages.length+') Tj ET'));
 const objects=['<< /Type /Catalog /Pages 2 0 R >>','','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>'];
 for(let i=0;i<pages.length;i++){const stream=pages[i].join('\n');objects.push('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents '+(6+i*2)+' 0 R >>','<< /Length '+stream.length+' >>\nstream\n'+stream+'\nendstream');}
 objects[1]='<< /Type /Pages /Count '+pages.length+' /Kids ['+pages.map((_,i)=>(5+i*2)+' 0 R').join(' ')+'] >>';let pdf='%PDF-1.4\n',offsets=[0];for(let i=0;i<objects.length;i++){offsets.push(pdf.length);pdf+=(i+1)+' 0 obj\n'+objects[i]+'\nendobj\n';}const xref=pdf.length;pdf+='xref\n0 '+(objects.length+1)+'\n0000000000 65535 f \n'+offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+'trailer\n<< /Size '+(objects.length+1)+' /Root 1 0 R >>\nstartxref\n'+xref+'\n%%EOF';return Uint8Array.from(pdf,c=>c.charCodeAt(0)&255);
}

export const reportBrowser=[financialMonth,reportData,reportXML,zipStore,reportMetrics,reportPeriod,reportAccount,reportColumn,reportCell,reportExcelDate,reportStyles,createMonthlyXLSX,reportTextWidth,reportWrap,createMonthlyPDF].map(fn=>'const '+fn.name+'='+fn.toString()+';').join('\n');

