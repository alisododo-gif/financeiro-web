"""Telegram-independent financial conversations. No credentials or network at import."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import calendar
import re
import secrets
import time
import uuid

TABLES = {'movimentacoes': 'Lançamentos', 'cartoes': 'Cartões e faturas',
          'contas_receber': 'Recebimentos', 'clientes': 'Clientes', 'contas': 'Contas',
          'metas': 'Metas', 'orcamentos': 'Orçamentos'}
CATEGORIES = ['Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação', 'Lazer',
              'Vestuário', 'Assinaturas', 'Cartão de Crédito', 'Outros']
METHODS = [('Pix', 'Pix'), ('Débito', 'Cartão de Débito'), ('Boleto', 'Boleto'),
           ('Crédito', 'Cartão de Crédito'), ('Dinheiro', 'Dinheiro')]
SCHEMAS = {
 'contas': [('nome', 'Nome da conta', 'text'), ('saldo', 'Saldo informado', 'balance')],
 'cartoes': [('nome_cartao', 'Nome do cartão', 'text'), ('limite', 'Limite total', 'money0'),
             ('dia_fechamento', 'Dia do fechamento (1 a 31)', 'day'), ('dia_vencimento', 'Dia do vencimento (1 a 31)', 'day')],
 'contas_receber': [('descricao', 'Descrição', 'text'), ('valor', 'Valor a receber', 'money'),
                    ('data_recebimento', 'Data prevista', 'date'), ('recebido', 'Já recebeu?', 'bool')],
 'clientes': [('nome', 'Nome do cliente', 'text'), ('telefone', 'Telefone com DDD', 'phone'),
              ('valor', 'Valor', 'money'), ('data_vencimento', 'Próximo vencimento', 'optional_date'), ('status', 'Situação do cliente', 'client_status'), ('conta_id','Conta bancária do cliente','account_optional')],
 'metas': [('nome_meta', 'Nome da meta', 'text'), ('valor_alvo', 'Valor do objetivo', 'money'),
           ('valor_poupado', 'Valor já poupado', 'money0'), ('prazo', 'Prazo da meta', 'date')],
 'orcamentos': [('categoria', 'Categoria (ou orçamento geral)', 'category_optional'), ('limite', 'Limite do orçamento', 'money0')],
 'movimentacoes': [('descricao', 'Descrição', 'text'), ('valor', 'Valor', 'money'),
                   ('data', 'Data do lançamento', 'date'), ('categoria', 'Categoria', 'category'),
                   ('tags', 'Tags (opcional)', 'optional_text'), ('pago', 'Está pago?', 'bool')],
}

class FlowError(Exception):
    """Safe, user-facing error; backend exceptions must not be echoed."""

def today():
    return datetime.now(ZoneInfo('America/Cuiaba')).date()

def amount(text, allow_zero=False, signed=False):
    value = str(text).strip().replace('R$', '').strip().replace(' ', '')
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', value):
        value = value.replace('.', '')
    if not re.fullmatch(r'-?\d+(\.\d{1,2})?', value):
        raise FlowError('Digite um valor com até dois centavos. Exemplo: 10,50.')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise FlowError('Valor inválido.') from None
    if abs(number) > 1000000 or (not signed and number < 0) or (not allow_zero and number == 0):
        raise FlowError('Informe um valor válido, até R$ 1.000.000,00.')
    return float(number)

def money(value):
    return 'R$ ' + f'{float(value or 0):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')

def parse_date(text):
    try:
        raw = str(text).strip()
        value = datetime.strptime(raw, '%d/%m/%Y').date() if '/' in raw else date.fromisoformat(raw)
        if not 2020 <= value.year <= 2099:
            raise ValueError()
        return value.isoformat()
    except ValueError:
        raise FlowError('Digite uma data válida: DD/MM/AAAA.') from None

def launch_rows(data):
    """Same legacy float rounding and day-28 clamp as the reviewed web flow."""
    count, mode = data.get('quantidade', 1), data.get('modalidade', 'Único')
    if mode not in ('Único', 'Parcelado', 'Fixo / Recorrente') or not isinstance(count, int) or not 1 <= count <= (1 if mode == 'Único' else 72 if mode == 'Parcelado' else 60) or (mode != 'Único' and count < 2):
        raise FlowError('Quantidade inválida.')
    value = round(float(data['valor']) / count, 2) if mode == 'Parcelado' else data['valor']
    if value <= 0:
        raise FlowError('A parcela precisa valer ao menos um centavo.')
    start = date.fromisoformat(parse_date(data['data']))
    rows = []
    for i in range(count):
        month = (start.month + i - 1) % 12 + 1
        year = start.year + (start.month + i - 1) // 12
        when = start if mode == 'Único' else date(year, month, min(start.day, 28))
        if year > 2099:
            raise FlowError('As parcelas ultrapassam o ano permitido.')
        suffix = f' ({i+1}/{count})' if mode == 'Parcelado' else ' (Recorrente)' if mode != 'Único' else ''
        row = {k: data[k] for k in ('tipo', 'categoria', 'forma_pagamento', 'conta_id', 'cartao_id') if k in data}
        row.update(descricao=data['descricao'] + suffix, valor=value, data=when.isoformat(),
                   pago=data.get('pago', False), tags=data.get('tags'))
        rows.append(row)
    return rows

def title(row):
    return str(row.get('descricao') or row.get('nome') or row.get('nome_cartao') or row.get('nome_meta') or row.get('categoria') or 'Orçamento geral')

@dataclass
class Screen:
    text: str
    buttons: list[tuple[str, str]]
    cards: list = field(default_factory=list)
    document: str | None = None

@dataclass
class Session:
    owner: int
    token: str = field(default_factory=lambda: secrets.token_hex(5))
    turn: int = 0
    touched: float = field(default_factory=time.monotonic)
    actions: list = field(default_factory=list)
    step: str = ''
    table: str = 'movimentacoes'
    draft: dict = field(default_factory=dict)
    row: dict | None = None
    fields: list = field(default_factory=list)
    field_index: int = 0
    command: dict | None = None
    month: str = ''
    page: int = 0
    card: int | None = None
    invoice_page: int = 0
    search: str = ''
    after_save: str = ''

class FinanceFlow:
    def __init__(self, repository):
        self.repo = repository
        self.sessions = {}

    def screen(self, s, text, choices=(), back=True):
        s.turn += 1
        s.actions = list(choices)
        if back:
            s.actions.append(('Menu / cancelar', ('menu',)))
        buttons = [(str(label)[:60], f'fp:{s.token}:{s.turn}:{i}') for i, (label, _) in enumerate(s.actions)]
        return Screen(str(text)[:3900], buttons)

    def session(self, telegram_id):
        owner = self.repo.authorize(telegram_id)
        if not owner:
            self.sessions.pop(telegram_id, None)
            raise FlowError('Conta sem vínculo ativo. Use /start e compartilhe seu próprio contato.')
        now = time.monotonic()
        for key in list(self.sessions):
            if now - self.sessions[key].touched >= 7200:
                self.sessions.pop(key)
        if telegram_id not in self.sessions or self.sessions[telegram_id].owner != owner:
            self.sessions[telegram_id] = Session(owner=owner, month=today().strftime('%Y-%m'))
        s = self.sessions[telegram_id]
        s.touched = now
        if hasattr(self.repo,'restore_module'): self.repo.restore_module(getattr(s,'access_module',None))
        return s

    def gate(self,s,module):
        if hasattr(self.repo,'set_module'): self.repo.set_module(s.owner,module)
        s.access_module=module

    def menu(self, s):
        self.gate(s,None)
        s.after_save=''
        s.step, s.command, s.row, s.draft = '', None, None, {}
        choices = [('Nova despesa', ('new_expense',)), ('Nova receita', ('new_income',)),
                   ('Resumo do mês', ('summary',)), ('Vencimentos', ('due',))]
        choices += [(label, ('module', table)) for table, label in TABLES.items()]
        if hasattr(self.repo,'allowed'):
            keys={'new_expense':'novo_lancamento','new_income':'novo_lancamento','summary':'visao_geral','due':'vencimentos'}
            choices=[(label,action) for label,action in choices if self.repo.allowed(s.owner,keys.get(action[0], 'recebimentos' if action[-1]=='contas_receber' else action[-1]))]
        return self.screen(s, 'FinanceiroPro Web\n\nO que deseja fazer?\nEnvie um valor, como 10, e escolha Receita ou Despesa.', choices, False)

    def help(self,s):
        return self.screen(s,'Não reconheci esse comando. Veja como usar:\n\n'
            '/menu — abrir todas as opções\n/receita — registrar uma entrada\n/despesa — registrar uma saída\n'
            '/resumo — relatório financeiro do mês\n/cartoes — cartões, faturas e vencimentos\n'
            '/clientes — ver, editar e excluir clientes\n/cadastrar — cadastrar cliente\n'
            '/listar — consultar lançamentos\n/receber — contas a receber\n/vencimentos — pendências do mês\n'
            '/contas — gerenciar contas\n/metas — objetivos\n/orcamentos — limites de gastos\n'
            '/cancelar — cancelar e voltar ao menu\n\nVocê também pode enviar 10 ou 10,50. Primeiro perguntarei se é receita ou despesa.', [('Abrir menu',('menu',))],False)

    def enter(self, telegram_id, command='menu'):
        s = self.session(telegram_id)
        aliases = {'start':'menu','cancelar':'menu','listar':'movimentacoes','lancamentos':'movimentacoes',
                   'receber':'contas_receber','status':'contas_receber','cadastrar':'clientes','data':'clientes','resumo':'summary','vencimentos':'due',
                   'receita':'new_income','entrada':'new_income','despesa':'new_expense'}
        action = aliases.get(command, command)
        if command=='cadastrar':
            self.gate(s,'clientes')
            s.table='clientes'
            return self.dispatch(s,('new',))
        if action not in TABLES and action not in ('menu','summary','due','new_income','new_expense'):
            return self.help(s)
        if action in TABLES:
            return self.module(s, action)
        return self.dispatch(s, (action,)) if action in ('summary','due','new_income','new_expense') else self.menu(s)

    def callback(self, telegram_id, raw):
        s = self.session(telegram_id)
        parts = str(raw).split(':')
        if len(parts) != 4 or parts[:2] != ['fp', s.token] or not parts[2].isdigit() or not parts[3].isdigit() or int(parts[2]) != s.turn or int(parts[3]) >= len(s.actions):
            raise FlowError('Esse botão expirou. Use /menu para continuar.')
        action = s.actions[int(parts[3])][1]
        return self.dispatch(s, action)

    def dispatch(self, s, action):
        name, *args = action
        if name in ('new_expense','new_income'): self.gate(s,'novo_lancamento')
        if name == 'menu': return self.menu(s)
        if name == 'module': return self.module(s, args[0])
        if name == 'kind':
            if s.step!='kind' or args[0] not in ('Receita','Despesa'): raise FlowError('Escolha receita ou despesa pelo menu atual.')
            s.draft['tipo']=args[0]
            return self.payment(s)
        if name == 'client_action':
            s.table='clientes'
            self.detail(s,args[0])
            return self.dispatch(s,(args[1],))
        if name == 'record_action':
            table,identifier,operation,*destination=args
            s.after_save='due' if destination==['due'] and operation in ('pay','unpay') else ''
            if table not in ('movimentacoes','cartoes'): raise FlowError('Opção inválida.')
            s.table=table
            self.detail(s,identifier)
            if operation=='unpay':
                if table!='movimentacoes' or s.row.get('tipo')!='Despesa' or not s.row.get('pago'): raise FlowError('Este registro não tem pagamento para desfazer.')
                return self.confirm(s,'editar',{'pago':False})
            if operation=='pay':
                if table=='cartoes':
                    s.card=identifier;s.invoice_page=0
                    self.invoice(s)
                    if not any(not r.get('pago') for r in s.draft['_invoice']['registros']): raise FlowError('Esta fatura já está paga ou não tem pendências.')
                    return self.dispatch(s,('settle',))
                if s.row.get('tipo')!='Despesa' or s.row.get('pago'): raise FlowError('Este lançamento não tem pagamento pendente. Atualize a lista.')
                return self.confirm(s,'editar',{'pago':True})
            if operation=='invoice': return self.dispatch(s,('invoice',identifier))
            if operation not in ('edit','delete'): raise FlowError('Opção inválida.')
            return self.dispatch(s,(operation,))
        if name == 'new_expense' or name == 'new_income':
            s.table, s.row, s.command = 'movimentacoes', None, None
            s.draft = {'tipo':'Receita' if name == 'new_income' else 'Despesa'}
            s.step = 'amount'
            return self.screen(s, 'Qual é o valor da '+s.draft['tipo'].lower()+'?\nExemplo: 10,50')
        if name=='goal_amount':
            if s.table!='metas' or not s.row or args[0] not in ('deposit','withdraw'): raise FlowError('Abra a meta novamente.')
            s.step='goal_amount';s.draft={'_goal_action':args[0]}
            return self.screen(s,'Qual valor deseja '+('depositar' if args[0]=='deposit' else 'resgatar')+'?\nIsso atualiza o progresso da meta, sem transferência bancária.')
        if name == 'method':
            if args[0] not in dict(METHODS).values() or ((s.draft.get('tipo') or (s.row or {}).get('tipo')) == 'Receita' and args[0]=='Cartão de Crédito'):
                raise FlowError('Forma de pagamento inválida.')
            s.draft['forma_pagamento'] = args[0]
            return self.references(s, 'cartoes' if args[0]=='Cartão de Crédito' else 'contas')
        if name == 'ref':
            table, identifier = args
            rows = self.repo.rows(s.owner, table)
            row = next((r for r in rows if r['id']==identifier), None)
            if row is None: raise FlowError('Esse cadastro mudou. Abra o menu novamente.')
            key = 'cartao_id' if table=='cartoes' else 'conta_id'
            s.draft[key], s.draft['conta_id' if key=='cartao_id' else 'cartao_id'] = identifier, None
            s.draft['_reference'] = title(row)
            if s.step in ('edit_ref','edit_payment'):
                payload={key:identifier}
                if s.step=='edit_payment': payload.update(forma_pagamento=s.draft['forma_pagamento'],**{'conta_id' if key=='cartao_id' else 'cartao_id':None})
                return self.confirm(s, 'editar', payload)
            return self.modes(s)
        if name == 'refpage': return self.references(s, args[0], args[1])
        if name == 'mode':
            s.draft['modalidade'] = args[0]
            if args[0]=='Único':
                s.draft['quantidade']=1
                return self.launch_fields(s)
            s.step='count'
            return self.screen(s, 'Em quantas parcelas?' if args[0]=='Parcelado' else 'Por quantos meses?', [(str(n),('count',n)) for n in (2,3,4,5,6,10,12)]+[('Outra quantidade',('type_count',))])
        if name == 'type_count':
            s.step='count'
            return self.screen(s,'Digite a quantidade (parcelas: 2 a 72; recorrência: 2 a 60).')
        if name == 'count': return self.set_count(s,args[0])
        if name == 'value': return self.field_value(s,args[0])
        if name == 'type_value':
            s.step='field'
            return self.screen(s,'Digite '+s.fields[s.field_index][1].lower()+'.')
        if name == 'new':
            if s.table=='movimentacoes': return self.dispatch(s,('new_expense',))
            s.row,s.draft,s.command=None,{},None
            s.fields=list(SCHEMAS[s.table]);s.field_index=0
            return self.prompt(s)
        if name == 'open': return self.detail(s,args[0])
        if name == 'page': s.page=args[0];return self.list_rows(s)
        if name == 'period': return self.period(s,args[0])
        if name == 'month':
            s.month=args[0];s.page=0
            return self.period_return(s,args[1])
        if name == 'type_month':
            s.step='month';s.draft={'_return':args[0]}
            return self.screen(s,'Digite o mês e ano: MM/AAAA.')
        if name == 'search':
            s.step='search';return self.screen(s,'Qual descrição ou nome deseja buscar?')
        if name == 'all': s.search='';s.page=0;return self.list_rows(s)
        if name == 'edit':
            s.fields=self.edit_fields(s);return self.screen(s,'O que deseja alterar?',[(label,('edit_field',i)) for i,(_,label,_) in enumerate(s.fields)])
        if name == 'edit_field':
            s.fields=[s.fields[args[0]]];s.field_index=0;s.draft={}
            return self.prompt(s)
        if name == 'delete': return self.confirm(s,'excluir',{})
        if name == 'toggle':
            key='pago' if s.table=='movimentacoes' else 'recebido' if s.table=='contas_receber' else 'status'
            value=not s.row.get(key) if key!='status' else 'Pendente' if s.row.get(key)=='Pago' else 'Pago'
            return self.confirm(s,'editar',{key:value})
        if name == 'commit': return self.commit(s)
        if name == 'invoice': s.card=args[0];s.invoice_page=0;return self.invoice(s)
        if name == 'invoice_page': s.invoice_page=args[0];return self.invoice(s)
        if name == 'invoice_movement': s.table='movimentacoes';return self.detail(s,args[0])
        if name == 'settle':
            snapshot=s.draft['_invoice']
            s.command={'tabela':'cartoes','acao':'quitar_fatura','id':s.card,'dados':{'competencia':self.competence(s)},'versao':snapshot['_versao'],'chave':str(uuid.uuid4())}
            s.step='confirm'
            total=sum(Decimal(str(r['valor'])) for r in snapshot['registros'] if not r.get('pago'))
            return self.screen(s,f'Confirmar baixa da fatura {self.competence(s)}?\nValor pendente: {money(total)}\nIsto registra o pagamento; não realiza transferência bancária.', [('Confirmar pagamento',('commit',))])
        if name == 'summary': return self.summary(s)
        if name == 'due': return self.due(s)
        raise FlowError('Opção inválida. Use /menu.')

    def text(self, telegram_id, text):
        s = self.session(telegram_id)
        if len(text)>1024: raise FlowError('Envie uma mensagem mais curta.')
        if text.strip().lower() in ('menu','cancelar','início','inicio'): return self.menu(s)
        if s.step=='amount':
            s.draft['valor']=amount(text);return self.payment(s)
        if s.step=='goal_amount':
            value=Decimal(str(amount(text)));saved=Decimal(str(s.row.get('valor_poupado') or 0))
            next_value=saved+value if s.draft['_goal_action']=='deposit' else saved-value
            if next_value<0: raise FlowError('O resgate é maior que o valor guardado.')
            if next_value>1000000: raise FlowError('O valor guardado excede o limite permitido.')
            return self.confirm(s,'editar',{'valor_poupado':float(next_value)})
        if s.step=='count':
            if not text.strip().isdigit(): raise FlowError('Digite apenas a quantidade, como 3.')
            return self.set_count(s,int(text.strip()))
        if s.step=='field': return self.field_value(s,text)
        if s.step=='month':
            if not re.fullmatch(r'(0[1-9]|1[0-2])/20\d{2}',text.strip()): raise FlowError('Use MM/AAAA, por exemplo 10/2026.')
            mm,yy=text.strip().split('/');s.month=yy+'-'+mm;s.page=0
            return self.period_return(s,s.draft['_return'])
        if s.step=='search': s.search=text.strip().casefold();s.page=0;s.step='';return self.list_rows(s)
        if re.fullmatch(r'(?:R\$\s*)?\d[\d., ]*',text.strip()):
            self.gate(s,'novo_lancamento')
            s.table,s.row,s.command='movimentacoes',None,None
            s.draft={'valor':amount(text)};s.step='kind'
            return self.screen(s,'Valor: '+money(s.draft['valor'])+'\nÉ uma receita ou uma despesa?', [('Receita',('kind','Receita')),('Despesa',('kind','Despesa'))])
        return self.help(s)

    def payment(self,s):
        s.step='payment'
        return self.screen(s,f'{s.draft["tipo"]}: {money(s.draft["valor"])}\nQual é o meio de pagamento?',[(label,('method',value)) for label,value in METHODS if s.draft['tipo']=='Despesa' or value!='Cartão de Crédito'])

    def references(self,s,table,page=0):
        rows=self.repo.rows(s.owner,table)
        if not rows:
            return self.screen(s,'Você ainda não tem '+('cartão' if table=='cartoes' else 'conta')+' cadastrado. Cadastre pelo menu e comece o lançamento novamente.', [('Cadastrar agora',('module',table))])
        if len(rows)==1 and table=='contas' and s.step!='edit_ref': return self.dispatch(s,('ref',table,rows[0]['id']))
        start=page*8
        choices=[(title(r),('ref',table,r['id'])) for r in rows[start:start+8]]
        if page: choices.append(('Anterior',('refpage',table,page-1)))
        if start+8<len(rows): choices.append(('Mais opções',('refpage',table,page+1)))
        return self.screen(s,'Selecione '+('o cartão de crédito:' if table=='cartoes' else 'a conta cadastrada:'),choices)

    def modes(self,s):
        s.step='mode'
        choices=[('À vista',('mode','Único'))]
        if s.draft.get('forma_pagamento')=='Cartão de Crédito': choices.append(('Parcelado',('mode','Parcelado')))
        choices.append(('Fixo / recorrente',('mode','Fixo / Recorrente')))
        return self.screen(s,'Selecionado: '+s.draft.get('_reference','')+'\nComo deseja lançar?',choices)

    def set_count(self,s,count):
        maximum=72 if s.draft.get('modalidade')=='Parcelado' else 60
        if not 2<=count<=maximum: raise FlowError(f'Escolha uma quantidade de 2 a {maximum}.')
        s.draft['quantidade']=count
        return self.launch_fields(s)

    def launch_fields(self,s):
        s.fields=[item for item in SCHEMAS['movimentacoes'] if item[0]!='valor' and (item[0]!='pago' or s.draft.get('modalidade')=='Único')]
        s.field_index=0
        return self.prompt(s)

    def prompt(self,s):
        s.step='field'
        key,label,kind=s.fields[s.field_index]
        choices=[]
        if kind in ('date','optional_date'):
            choices=[('Hoje',('value',today().isoformat())),('Amanhã',('value',(today()+timedelta(days=1)).isoformat())),('Outra data',('type_value',))]
            if kind=='optional_date': choices.append(('Sem data',('value',None)))
        elif kind=='bool': choices=[('Sim',('value',True)),('Não',('value',False))]
        elif kind=='client_status': choices=[('Pendente',('value','Pendente')),('Pago',('value','Pago'))]
        elif kind=='account_optional':
            choices=[(str(r['nome']),('value',r['id'])) for r in self.repo.rows(s.owner,'contas')]+[('Não vincular conta',('value',None))]
        elif kind.startswith('category'):
            categories=['Salário','Freelance','Investimentos','Presente/Prêmio','Outros'] if s.draft.get('tipo')=='Receita' else CATEGORIES
            choices=[(c,('value',c)) for c in categories]+[('Outra categoria',('type_value',))]
            if kind=='category_optional': choices.insert(0,('Orçamento geral',('value',None)))
        elif kind=='optional_text': choices=[('Pular',('value',None))]
        elif kind in ('account','card'):
            s.step='edit_ref'
            return self.references(s,'contas' if kind=='account' else 'cartoes')
        elif kind=='method':
            s.step='edit_payment'
            return self.screen(s,'Escolha o novo meio de pagamento.',[(label,('method',value)) for label,value in METHODS if s.row.get('tipo')!='Receita' or value!='Cartão de Crédito'])
        return self.screen(s,label+('\nDigite DD/MM/AAAA.' if kind.endswith('date') else '\nDigite a resposta ou escolha um botão.'),choices)

    def field_value(self,s,value):
        if s.step!='field': raise FlowError('Abra o menu para iniciar uma operação.')
        key,label,kind=s.fields[s.field_index]
        if kind in ('money','money0','balance'): value=amount(value,kind!='money',kind=='balance')
        elif kind=='day':
            if not str(value).isdigit() or not 1<=int(value)<=31: raise FlowError('Informe um dia entre 1 e 31.')
            value=int(value)
        elif kind in ('date','optional_date'):
            value=None if value is None and kind=='optional_date' else parse_date(value)
        elif kind=='bool':
            if not isinstance(value,bool): raise FlowError('Escolha Sim ou Não pelos botões.')
        elif kind=='client_status':
            if value not in ('Pago','Pendente'): raise FlowError('Escolha a situação pelos botões.')
        elif kind=='account_optional':
            if value is not None:
                try: value=int(value)
                except (TypeError,ValueError): raise FlowError('Escolha a conta bancária pelos botões.') from None
                if not any(r['id']==value for r in self.repo.rows(s.owner,'contas')): raise FlowError('A conta não pertence ao seu usuário.')
        elif kind=='phone':
            value=re.sub(r'\D','',str(value))
            if not 8<=len(value)<=15: raise FlowError('Informe telefone com DDD, de 8 a 15 números.')
        elif value is None and kind in ('optional_text','category_optional'): pass
        else:
            value=str(value).strip()
            if not value or len(value)>(140 if key=='descricao' and s.row is None else 240): raise FlowError('Preencha um texto mais curto (até 140 caracteres na descrição).')
            if key=='tags': value=', '.join('#'+t.strip().lstrip('#') for t in value.split(',') if t.strip().lstrip('#'))
        s.draft[key]=value
        s.field_index+=1
        if s.field_index<len(s.fields): return self.prompt(s)
        return self.confirm(s,'editar' if s.row else 'criar',s.draft)

    def confirm(self,s,action,data):
        payload={k:v for k,v in data.items() if not k.startswith('_')}
        if s.table=='movimentacoes' and action=='criar':
            payload={'registros':launch_rows(payload)};action='criar_lote'
        s.command={'tabela':s.table,'acao':action,'dados':payload,'chave':str(uuid.uuid4())}
        if s.row: s.command.update(id=s.row['id'],versao=s.row['_versao'])
        s.step='confirm'
        lines=['Confirma '+('excluir este registro?' if action=='excluir' else 'salvar esta operação?')]
        if s.row: lines.append(title(s.row))
        if action=='criar_lote':
            movements=payload['registros'];lines += [title(movements[0]),f'{len(movements)} lançamento(s) de {money(movements[0]["valor"])}',f'Total: {money(sum(Decimal(str(m["valor"])) for m in movements))}',s.draft.get('_reference',''),s.draft.get('forma_pagamento',''), 'Data inicial: '+s.draft['data']]
            if s.draft.get('modalidade')=='Parcelado': lines.append('Parcelas calculadas com o arredondamento do sistema. Confira o total acima.')
        else:
            labels={k:label for k,label,_ in SCHEMAS[s.table]}
            for k,v in payload.items():
                if s.table=='clientes' and k=='conta_id': v=self.customer_account_name(s,v)
                lines.append(labels.get(k,k)+': '+('Não informado' if v is None else 'Sim' if v is True else 'Não' if v is False else money(v) if k in ('valor','limite','saldo','valor_alvo','valor_poupado') else str(v)))
        return self.screen(s,'\n'.join(lines),[('Confirmar exclusão' if action=='excluir' else 'Confirmar e salvar',('commit',))])

    def commit(self,s):
        if s.step!='confirm' or not s.command: raise FlowError('Essa confirmação já foi usada. Abra o menu.')
        undone=s.command.get('dados',{}).get('pago') is False
        try:
            self.repo.command(s.owner,s.command)
        except FlowError as error:
            return self.screen(s,str(error)+'\nSe a falha for de conexão, tente de novo com o botão abaixo. A mesma operação não será gravada duas vezes.',[('Tentar novamente',('commit',))])
        s.command,s.step,s.row=None,'',None
        if s.after_save=='due':
            s.after_save=''
            result=self.due(s)
            result.text=('↩️ Pagamento desfeito.' if undone else '✅ Pagamento registrado.')+'\n\n'+result.text
            return result
        return self.screen(s,'Operação concluída com sucesso.',[('Ver registros',('module',s.table)),('Novo lançamento',('new_expense',))])

    def module(self,s,table):
        self.gate(s,'recebimentos' if table=='contas_receber' else table)
        s.after_save=''
        if table not in TABLES: raise FlowError('Módulo inválido.')
        s.table,s.step,s.row,s.command,s.page,s.search=table,'',None,None,0,''
        return self.list_rows(s)

    def competence(self,s): return s.month[5:7]+'/'+s.month[:4]

    def period(self,s,destination):
        year,month=map(int,s.month.split('-'));index=year*12+month-1
        options=[]
        for offset,label in [(-1,'Mês anterior'),(0,'Este mês selecionado'),(1,'Próximo mês')]:
            y,m=divmod(index+offset,12)
            if 2020<=y<=2099: options.append((label,('month',f'{y:04}-{m+1:02}',destination)))
        options.append(('Outro mês / ano',('type_month',destination)))
        return self.screen(s,'Período atual: '+self.competence(s),options)

    def period_return(self,s,destination):
        s.step=''
        return self.summary(s) if destination=='summary' else self.due(s) if destination=='due' else self.invoice(s) if destination=='invoice' else self.list_rows(s)

    def list_rows(self,s):
        rows=self.repo.rows(s.owner,s.table)
        if s.table=='movimentacoes': return self.movement_list(s,rows)
        if s.table=='movimentacoes': rows=[r for r in rows if str(r.get('data','')).startswith(s.month)]
        if s.table=='contas_receber': rows=[r for r in rows if str(r.get('data_recebimento','')).startswith(s.month)]
        if s.search: rows=[r for r in rows if s.search in title(r).casefold()]
        rows=sorted(rows,key=lambda r:(str(r.get('data') or r.get('data_recebimento') or ''),r['id']),reverse=True)
        if s.table in ('cartoes','movimentacoes'):
            choices=[('Novo cadastro' if s.table=='cartoes' else 'Nova despesa',('new',)),('Buscar',('search',)),('Alterar mês',('period','list'))]
            if s.search: choices.append(('Limpar busca',('all',)))
            result=self.screen(s,TABLES[s.table]+' · '+self.competence(s)+f'\n{len(rows)} registro(s)',choices)
            movements=self.repo.rows(s.owner,'movimentacoes') if s.table=='cartoes' else []
            for row in rows:
                if s.table=='cartoes': self.card_tile(s,result,row,movements)
                else: self.movement_tile(s,result,row)
            return result
        s.page=max(0,min(s.page,max(0,(len(rows)-1)//6)))
        choices=[];lines=[TABLES[s.table]+' · '+self.competence(s),f'{len(rows)} registro(s)']
        for r in rows[s.page*6:s.page*6+6]:
            value=r.get('valor',r.get('saldo',r.get('limite',r.get('valor_alvo',0))))
            if s.table!='cartoes': lines.append(f'{title(r)[:90]} · {money(value)}')
            choices.append((title(r)[:38] if s.table=='cartoes' else title(r)[:38]+' · '+money(value),('open',r['id'])))
        if s.table=='cartoes':
            movements=self.repo.rows(s.owner,'movimentacoes')
            for c in rows[s.page*6:s.page*6+6]:
                invoice=[m for m in movements if m.get('cartao_id')==c['id'] and m.get('tipo')=='Despesa' and m.get('forma_pagamento')=='Cartão de Crédito' and m.get('mes_fatura')==self.competence(s)]
                total=sum(Decimal(str(m['valor'])) for m in invoice)
                pending=sum(Decimal(str(m['valor'])) for m in invoice if not m.get('pago'))
                lines.append('💳 '+title(c)+'\nVencimento: '+self.card_due(s,c)+'\nFatura do mês: '+money(total)+' · A pagar: '+money(pending))
        if s.page: choices.append(('Anterior',('page',s.page-1)))
        if (s.page+1)*6<len(rows): choices.append(('Próxima',('page',s.page+1)))
        choices += [('Novo cadastro' if s.table!='movimentacoes' else 'Nova despesa',('new',)),('Buscar',('search',))]
        if s.table in ('movimentacoes','contas_receber','cartoes'): choices.append(('Alterar mês',('period','list')))
        if s.search: choices.append(('Limpar busca',('all',)))
        if s.table=='clientes':
            # One revision for all cards: each button resolves an owned row again.
            choices=[c for c in choices if c[1][0] not in ('open','page')]
            result=self.screen(s,TABLES[s.table]+f'\n{len(rows)} cliente(s)',choices)
            for r in rows:
                buttons=[]
                for label,action in [('✏️ Editar','edit'),('🗑️ Excluir','delete')]:
                    index=len(s.actions);s.actions.append((label,('client_action',r['id'],action)))
                    buttons.append((label,f'fp:{s.token}:{s.turn}:{index}'))
                due=str(r.get('data_vencimento') or 'Não informado')
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}',due): due='/'.join(reversed(due.split('-')))
                result.cards.append(('👤 '+title(r)[:200]+'\n📱 '+str(r.get('telefone') or 'Não informado')+'\n💰 '+money(r.get('valor'))+'\n📅 Vencimento: '+due+'\nSituação: '+str(r.get('status') or 'Pendente'),buttons))
            return result
        return self.screen(s,'\n'.join(lines),choices)

    def card_due(self,s,card):
        year,month=map(int,s.month.split('-'))
        day=max(1,min(int(card.get('dia_vencimento') or 1),calendar.monthrange(year,month)[1]))
        return f'{day:02}/{month:02}/{year}'

    def movement_list(self,s,rows):
        current=today()
        cards={str(c['id']):c for c in self.repo.rows(s.owner,'cartoes')}
        groups={};ordinary=[]
        def created_today(row):
            try:
                stamp=datetime.fromisoformat(str(row.get('created_at') or '').replace('Z','+00:00'))
                return stamp.tzinfo is not None and stamp.astimezone(ZoneInfo('America/Cuiaba')).date()==current
            except (ValueError,TypeError): return False
        dated=[row for row in rows if created_today(row)]
        for row in dated:
            credit=row.get('tipo')=='Despesa' and (row.get('cartao_id') is not None or str(row.get('forma_pagamento') or '').casefold() in ('cartão de crédito','cartao de credito','crédito','credito'))
            if credit:
                identifier=str(row.get('cartao_id')) if row.get('cartao_id') is not None else None
                key=('card',identifier) if identifier else ('unlinked',str(row.get('nome_cartao') or 'Cartão sem vínculo'))
                groups.setdefault(key,[]).append(row)
            elif not s.search or s.search in title(row).casefold(): ordinary.append(row)
        result=self.screen(s,'Lançamentos cadastrados hoje · '+current.strftime('%d/%m/%Y')+'\nCadastros feitos hoje, independentemente do vencimento. Crédito agrupado por cartão.', [('Nova despesa',('new',)),('Buscar',('search',))]+([('Limpar busca',('all',))] if s.search else []))
        for key,items in groups.items():
            card=cards.get(key[1]) if key[0]=='card' else None
            name=title(card) if card else key[1] if key[0]=='unlinked' else 'Cartão sem cadastro disponível'
            if s.search and s.search not in name.casefold() and not any(s.search in title(r).casefold() for r in items): continue
            total=sum(Decimal(str(r['valor'])) for r in items)
            pending=sum(Decimal(str(r['valor'])) for r in items if not r.get('pago'))
            actions=[('📋 Cartões e faturas',('module','cartoes'))] if card else []
            self.tile(s,result,'💳 '+name[:200]+'\nCadastrados hoje: '+current.strftime('%d/%m/%Y')+'\nValor: '+money(total)+'\nPendente nos registros de hoje: '+money(pending)+'\n'+str(len(items))+' lançamento(s)',actions)
        for row in sorted(ordinary,key=lambda r:(str(r.get('data')),r['id']),reverse=True): self.movement_tile(s,result,row)
        result.text+=f'\n{len(result.cards)} card(s).' if result.cards else '\nNão temos lançamentos na data de hoje.' if not dated else '\nNenhum lançamento de hoje corresponde à busca.'
        return result

    def tile(self,s,result,text,actions):
        buttons=[]
        for label,action in actions:
            index=len(s.actions);s.actions.append((label,action))
            buttons.append((label,f'fp:{s.token}:{s.turn}:{index}'))
        result.cards.append((text,buttons))

    def card_tile(self,s,result,card,movements):
        invoice=[m for m in movements if m.get('cartao_id')==card['id'] and m.get('tipo')=='Despesa' and m.get('forma_pagamento')=='Cartão de Crédito' and m.get('mes_fatura')==self.competence(s)]
        total=sum(Decimal(str(m['valor'])) for m in invoice)
        pending=sum(Decimal(str(m['valor'])) for m in invoice if not m.get('pago'))
        actions=[('📋 Ver fatura',('record_action','cartoes',card['id'],'invoice')),('✏️ Editar',('record_action','cartoes',card['id'],'edit'))]
        if pending>0: actions.insert(0,('✅ Pagar fatura',('record_action','cartoes',card['id'],'pay')))
        self.tile(s,result,'💳 '+title(card)[:200]+'\n📅 Vencimento: '+self.card_due(s,card)+'\nFatura do mês: '+money(total)+'\nA pagar: '+money(pending)+'\n'+('⏳ Pendente' if pending>0 else '✅ Sem pendências'),actions)

    def movement_tile(self,s,result,row):
        when=str(row.get('data') or '')[:10]
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',when): when='/'.join(reversed(when.split('-')))
        actions=[('✏️ Editar',('record_action','movimentacoes',row['id'],'edit')),('🗑️ Excluir',('record_action','movimentacoes',row['id'],'delete'))]
        if row.get('tipo')=='Despesa' and not row.get('pago') and row.get('forma_pagamento')!='Cartão de Crédito':
            actions.insert(0,('✅ Pagar',('record_action','movimentacoes',row['id'],'pay')))
        elif row.get('tipo')=='Despesa' and row.get('pago') and row.get('forma_pagamento')!='Cartão de Crédito':
            actions.insert(0,('↩️ Desfazer pagamento',('record_action','movimentacoes',row['id'],'unpay')))
        self.tile(s,result,'🧾 '+title(row)[:200]+'\n'+str(row.get('tipo') or '')+' · '+money(row.get('valor'))+'\n📅 '+when+'\nPagamento: '+str(row.get('forma_pagamento') or 'Não informado')+'\n'+('✅ Pago / recebido' if row.get('pago') else '⏳ Pendente'),actions)

    def customer_account_name(self,s,identifier):
        return next((r['nome'] for r in self.repo.rows(s.owner,'contas') if r['id']==identifier),'Não vinculada')

    def detail(self,s,identifier):
        row=next((r for r in self.repo.rows(s.owner,s.table) if r['id']==identifier),None)
        if not row: raise FlowError('Registro não encontrado na sua conta. Atualize a lista.')
        s.row,s.draft,s.command=row,{},None
        fields=self.edit_fields(s);lines=[title(row)]
        for key,label,kind in fields:
            value=row.get(key)
            if kind=='account_optional': value=self.customer_account_name(s,value)
            lines.append(label+': '+(money(value) if kind in ('money','money0','balance') else 'Sim' if value is True else 'Não' if value is False else str(value) if value is not None else 'Não informado'))
        choices=[('Editar',('edit',)),('Excluir',('delete',))]
        if s.table in ('movimentacoes','contas_receber','clientes'): choices.insert(0,('Alterar pagamento / recebimento',('toggle',)))
        if s.table=='cartoes':
            choices.insert(0,('Consultar fatura e limite',('invoice',row['id'])))
        if s.table=='metas':
            lines.append('Falta poupar: '+money(max(0,row['valor_alvo']-row['valor_poupado'])))
            choices[:0]=[('Depositar',('goal_amount','deposit')),('Resgatar',('goal_amount','withdraw'))]
        if s.table=='orcamentos':
            movements=self.repo.rows(s.owner,'movimentacoes')
            spent=sum(Decimal(str(m['valor'])) for m in movements if m['tipo']=='Despesa' and str(m.get('data','')).startswith(s.month) and (not row.get('categoria') or m.get('categoria')==row['categoria']))
            lines += ['Gasto em '+self.competence(s)+': '+money(spent),'Restante: '+money(Decimal(str(row['limite']))-spent)]
            choices.append(('Alterar mês',('period','list')))
        return self.screen(s,'\n'.join(lines),choices)

    def edit_fields(self,s):
        fields=list(SCHEMAS[s.table])
        if s.table=='movimentacoes':
            fields.append(('forma_pagamento','Meio de pagamento','method'))
            fields.append(('cartao_id','Cartão de crédito','card') if s.row.get('forma_pagamento')=='Cartão de Crédito' else ('conta_id','Conta','account'))
        return fields

    def invoice(self,s):
        if getattr(s,'access_module',None)!='vencimentos': self.gate(s,'cartoes')
        s.table='cartoes'
        card=next((r for r in self.repo.rows(s.owner,'cartoes') if r['id']==s.card),None)
        if not card: raise FlowError('Cartão não encontrado na sua conta.')
        snapshot=self.repo.command(s.owner,{'tabela':'cartoes','acao':'fatura','id':s.card,'dados':{'competencia':self.competence(s)}})
        all_rows=self.repo.rows(s.owner,'movimentacoes')
        pending=sum(Decimal(str(r['valor'])) for r in all_rows if r.get('cartao_id')==s.card and r['tipo']=='Despesa' and r.get('forma_pagamento')=='Cartão de Crédito' and not r.get('pago'))
        total=sum(Decimal(str(r['valor'])) for r in snapshot['registros'])
        current_pending=sum(Decimal(str(r['valor'])) for r in snapshot['registros'] if not r.get('pago'))
        s.draft={'_invoice':snapshot}
        lines=[title(card)+' · Fatura '+self.competence(s),'Gasto do mês: '+money(total),'Pendente na fatura: '+money(current_pending),'Limite total: '+money(card['limite']),'Limite disponível: '+money(Decimal(str(card['limite']))-pending),'Disponível considera todas as parcelas pendentes, inclusive futuras.']
        lines.insert(1,'Vencimento: '+self.card_due(s,card))
        choices=[('Alterar mês',('period','invoice'))]
        s.invoice_page=max(0,min(s.invoice_page,max(0,(len(snapshot['registros'])-1)//6)))
        for r in snapshot['registros'][s.invoice_page*6:s.invoice_page*6+6]:
            lines.append(title(r)[:85]+' · '+money(r['valor'])+' · '+('Pago' if r.get('pago') else 'Pendente'))
            choices.append((title(r)[:42]+' · '+money(r['valor']),('invoice_movement',r['id'])))
        if s.invoice_page: choices.append(('Compras anteriores',('invoice_page',s.invoice_page-1)))
        if (s.invoice_page+1)*6<len(snapshot['registros']): choices.append(('Mais compras',('invoice_page',s.invoice_page+1)))
        if current_pending>0: choices.insert(0,('Registrar pagamento da fatura',('settle',)))
        return self.screen(s,'\n'.join(lines),choices)

    def summary(self,s):
        self.gate(s,'visao_geral')
        rows=self.repo.rows(s.owner,'movimentacoes')
        cards={c['id']:c for c in self.repo.rows(s.owner,'cartoes')}
        def credit(r):
            method=str(r.get('forma_pagamento') or '').casefold()
            return r.get('tipo')=='Despesa' and (r.get('cartao_id') is not None or method in ('cartão de crédito','cartao de credito','crédito','credito') or (not method and bool(re.search(r'cart[aã]o|fatura|anuidade',str(r.get('descricao') or ''),re.I))))
        selected=[r for r in rows if (r.get('mes_fatura')==self.competence(s) if credit(r) else str(r.get('data','')).startswith(s.month))]
        income=sum(Decimal(str(r['valor'])) for r in selected if r['tipo']=='Receita')
        expense=sum(Decimal(str(r['valor'])) for r in selected if r['tipo']=='Despesa')
        groups={'💵 RECEITAS / ENTRADAS':[], '💸 PIX / DÉBITO / À VISTA':[], '💳 FATURAS DE CARTÃO':[], '📑 BOLETOS & CONTAS A PAGAR':[], '🔄 GASTOS FIXOS / RECORRENTES':[]}
        invoices={}
        for r in selected:
            if credit(r):
                invoices.setdefault(r.get('cartao_id'),[]).append(r);continue
            recurring=r.get('recorrente') is True or r.get('fixo') is True or bool(re.search(r'recorren|fixo',str(r.get('descricao') or '')+' '+str(r.get('tags') or ''),re.I))
            method=str(r.get('forma_pagamento') or '').casefold()
            key='💵 RECEITAS / ENTRADAS' if r['tipo']=='Receita' else '🔄 GASTOS FIXOS / RECORRENTES' if recurring else '💸 PIX / DÉBITO / À VISTA' if method in ('pix','cartão de débito','débito','debito','dinheiro','à vista','a vista') else '📑 BOLETOS & CONTAS A PAGAR'
            when=str(r.get('data') or '')[:10]
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',when): when='/'.join(reversed(when.split('-')))
            groups[key].append('• '+when+' — '+title(r)[:160]+' | '+money(r['valor'])+' — '+('✅ Pago' if r.get('pago') else '⏳ Pendente'))
        for identifier,items in invoices.items():
            c=cards.get(identifier)
            groups['💳 FATURAS DE CARTÃO'].append('• '+(self.card_due(s,c)+' — '+title(c) if c else 'Cartão de Crédito')+' | '+money(sum(Decimal(str(r['valor'])) for r in items))+' — '+('✅ Pago' if all(r.get('pago') for r in items) else '⏳ Pendente'))
        result=self.screen(s,'📊 Relatório Financeiro · '+self.competence(s)+'\n🟢 Receitas: '+money(income)+'\n🔴 Despesas: '+money(expense)+'\n🔵 Saldo do período: '+money(income-expense),[('Alterar mês',('period','summary')),('Ver lançamentos',('module','movimentacoes'))])
        # Split long reports instead of truncating financial records at Telegram's limit.
        for heading,items in groups.items():
            chunk=heading+'\n'
            for line in items or ['• Nenhum registro neste mês.']:
                if len(chunk)+len(line)+1>3500:
                    result.cards.append((chunk,[]));chunk=heading+' (continuação)\n'
                chunk+=line+'\n'
            result.cards.append((chunk,[]))
        complete=result.text+'\n\n'+'\n\n'.join(text.strip() for text,_ in result.cards)
        result.cards=[]
        if len(complete)<=3900:
            result.text=complete
        else:
            result.text='📊 Relatório Financeiro · '+self.competence(s)+'\nO relatório completo está no arquivo, pois ultrapassou o tamanho permitido pelo Telegram.'
            result.document=complete
        return result

    def due(self,s):
        self.gate(s,'vencimentos')
        rows=self.repo.rows(s.owner,'movimentacoes');cards=self.repo.rows(s.owner,'cartoes')
        result=self.screen(s,'Vencimentos · '+self.competence(s),[('Alterar mês',('period','due'))])
        entries=[]
        for c in cards:
            invoice=[r for r in rows if r.get('cartao_id')==c['id'] and r.get('mes_fatura')==self.competence(s) and r.get('tipo')=='Despesa' and r.get('forma_pagamento')=='Cartão de Crédito']
            if invoice: entries.append((all(r.get('pago') for r in invoice),self.card_due(s,c)[6:10]+self.card_due(s,c)[3:5]+self.card_due(s,c)[:2],'card',c))
        bills=sorted([r for r in rows if r.get('tipo')=='Despesa' and r.get('forma_pagamento')!='Cartão de Crédito' and str(r.get('data','')).startswith(s.month)],key=lambda r:(str(r.get('data')),r['id']))
        entries.extend((bool(r.get('pago')),str(r.get('data')).replace('-',''),'bill',r) for r in bills)
        entries.sort(key=lambda e:(e[0],e[1],e[3]['id']))
        section=None
        for paid,_,kind,row in entries:
            if section is None or section!=paid:
                section=paid
                count=sum(item[0]==paid for item in entries)
                result.cards.append((('✅ PAGOS' if paid else '⏳ PENDENTES')+f' · {count}',[]))
            start=len(s.actions)
            if kind=='card': self.card_tile(s,result,row,rows)
            else: self.movement_tile(s,result,row)
            for index in range(start,len(s.actions)):
                label,action=s.actions[index]
                if action[0]=='record_action' and action[3] in ('pay','unpay'): s.actions[index]=(label,action+('due',))
        result.text+=f'\n{len(entries)} vencimento(s).' if entries else '\nNenhum vencimento neste mês.'
        return result
