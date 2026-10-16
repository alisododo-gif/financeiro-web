"""All bot financial writes reuse the same scoped, idempotent RPC as the web."""
import re
import threading
from bot_flows import FlowError, TABLES

class SupabaseRepository:
    def __init__(self, client):
        self.db = client
        self.context = threading.local()

    def authorize(self, telegram_id):
        rows = (self.db.table('usuarios').select('id').eq('telegram_id',int(telegram_id))
                .eq('status','ativo').limit(2).execute()).data
        if len(rows)!=1: return None
        owner=rows[0]['id']
        access=self.access(owner)
        self.context.owner=owner
        self.context.access=access
        self.context.module=None
        if not access.get('allowed'):
            raise FlowError(access.get('message','Acesso bloqueado.')+'\nContratar: https://wa.me/'+str(access.get('contact') or '5511934974963'))
        return owner

    def access(self, owner):
        try:
            return self.db.rpc('fp_access_v1',{'p_usuario':owner}).execute().data
        except Exception:
            raise FlowError('Não consegui verificar seu acesso agora. Tente novamente.') from None

    def allowed(self, owner, module):
        access=getattr(self.context,'access',None) if getattr(self.context,'owner',None)==owner else None
        if access is None: access=self.access(owner)
        return bool(access.get('allowed') and access.get('modules',{}).get(module))

    def set_module(self, owner, module):
        if module and not self.allowed(owner,module):
            raise FlowError('Este módulo não está liberado para sua conta. Fale com o administrador: https://wa.me/5511934974963')
        self.context.module=module

    def restore_module(self, module):
        self.context.module=module

    def rows(self, owner, table):
        if table not in TABLES:
            raise FlowError('Módulo inválido.')
        return self.command(owner, {'tabela':table,'acao':'listar'})['registros']

    def command(self, owner, command):
        if not isinstance(owner,int) or owner<=0 or command.get('tabela') not in TABLES or set(command)-{'tabela','acao','id','dados','versao','chave'}:
            raise FlowError('Operação inválida.')
        payload={'p_usuario':owner,'p_tabela':command['tabela'],'p_acao':command['acao'],
                 'p_id':command.get('id'),'p_dados':command.get('dados',{}),
                 'p_versao':command.get('versao'),'p_chave':command.get('chave'),'p_modulo':getattr(self.context,'module',None)}
        try:
            return self.db.rpc('fp_financeiro_modulo_v1',payload).execute().data
        except Exception as error:
            code=str(getattr(error,'code',''))
            messages={'40001':'O registro mudou. Abra o menu e consulte novamente antes de alterar.',
                      '23503':'Esse cadastro tem lançamentos vinculados. Preserve o histórico.',
                      '42501':'Seu acesso ou este módulo está bloqueado. Entre em contato: https://wa.me/5511934974963',
                      'P0002':'Registro não encontrado na sua conta. Atualize a lista.',
                      '22023':'Confira os dados. Datas, valores e campos precisam seguir as regras do sistema.',
                      '23505':'Já existe um cadastro com esses dados.'}
            raise FlowError(messages.get(code,'Não foi possível confirmar a gravação por uma falha de conexão.')) from None

    @staticmethod
    def phone_variants(raw):
        number=re.sub(r'\D','',str(raw or ''))
        if len(number) in (10,11): number='55'+number
        variants={number}
        if len(number)==13 and number.startswith('55') and number[4]=='9': variants.add(number[:4]+number[5:])
        return variants

    def bind_contact(self, telegram_id, phone):
        existing=self.authorize(telegram_id)
        if existing: return existing
        variants=self.phone_variants(phone)
        rows=self.db.table('usuarios').select('id,telefone,telegram_id').eq('status','ativo').limit(1000).execute().data
        matches=[r for r in rows if self.phone_variants(r.get('telefone')) & variants]
        if len(matches)!=1 or matches[0].get('telegram_id') not in (None,int(telegram_id)):
            raise FlowError('Não foi possível vincular automaticamente. Confira o telefone cadastrado com o administrador.')
        row=matches[0]
        query=self.db.table('usuarios').update({'telegram_id':int(telegram_id)}).eq('id',row['id']).eq('status','ativo')
        query=query.is_('telegram_id','null') if row.get('telegram_id') is None else query.eq('telegram_id',int(telegram_id))
        result=query.execute().data
        if len(result)!=1 or self.authorize(telegram_id)!=row['id']:
            raise FlowError('O vínculo mudou. Peça ao administrador para conferir sua conta.')
        return row['id']
