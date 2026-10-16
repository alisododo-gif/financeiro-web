"""One plain-text daily summary per authorized owner; no network side effects."""
from collections import defaultdict
from decimal import Decimal

def build_daily_alerts(movements, invoices, receivables, day):
    grouped=defaultdict(lambda:defaultdict(list))
    for section,rows,flag in [('Boletos e fixos/recorrentes',movements,'pago'),('Faturas vencendo hoje',invoices,'pago'),('Recebimentos pendentes',receivables,'recebido')]:
        for row in rows:
            if row.get(flag) is True or not row.get('usuario_id') or not row.get('telegram_id'):
                continue
            grouped[(row['usuario_id'],row['telegram_id'])][section].append(row)
    result=[]
    for (owner,chat),sections in grouped.items():
        lines=['FinanceiroPro Web · Pendências de hoje',day.strftime('%d/%m/%Y')]
        omitted=0
        for section,rows in sections.items():
            lines.extend(['',f'{section} ({len(rows)})'])
            for row in rows:
                label=str(row.get('descricao') or row.get('nome_cartao') or 'Registro').replace('\n',' ')[:150]
                if 'valor' in row:
                    value=f'{Decimal(str(row.get("valor") or 0)):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
                    label+=' · R$ '+value
                if sum(len(line)+1 for line in lines)+len(label)>3600:
                    omitted+=1
                else:
                    lines.append('• '+label)
        if omitted: lines.extend(['',f'+ {omitted} item(ns). Consulte /vencimentos ou /menu para ver todos.'])
        lines.extend(['','Somente pendências. Registre a quitação no sistema para retirar o aviso.'])
        result.append((owner,chat,'\n'.join(lines)))
    return result
