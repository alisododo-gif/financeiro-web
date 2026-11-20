import copy
import ast
import logging
import sys
import unittest
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import date
sys.path.insert(0,str(Path(__file__).parent))
from bot_flows import FinanceFlow, FlowError, amount, launch_rows, Session, TABLES, financial_month
from bot_repository import SupabaseRepository

class MemoryRepository:
    def __init__(self):
        self.links={100:1,200:2};self.commands=[];self.failed=False
        self.data={t:[] for t in TABLES}
        self.data['contas']=[{'id':10,'usuario_id':1,'nome':'Conta A','saldo':0,'_versao':'a'}, {'id':11,'usuario_id':1,'nome':'Conta B','saldo':1,'_versao':'b'}, {'id':12,'usuario_id':2,'nome':'Conta privada','saldo':0,'_versao':'c'}]
        self.data['cartoes']=[{'id':20,'usuario_id':1,'nome_cartao':'Cartão A','limite':1000,'dia_fechamento':31,'dia_vencimento':5,'_versao':'c'}, {'id':21,'usuario_id':2,'nome_cartao':'Outro cartão','limite':2000,'dia_fechamento':10,'dia_vencimento':15,'_versao':'x'}]
    def authorize(self,telegram_id): return self.links.get(telegram_id)
    def rows(self,owner,table): return copy.deepcopy([r for r in self.data[table] if r['usuario_id']==owner])
    def command(self,owner,command):
        self.commands.append((owner,copy.deepcopy(command)))
        if self.failed: raise FlowError('Falha de conexão')
        if command['acao']=='fatura': return {'registros':[r for r in self.rows(owner,'movimentacoes') if r.get('cartao_id')==command['id'] and r.get('mes_fatura')==command['dados']['competencia']], '_versao':'invoice-1'}
        return {'gravado':True}

class FlowTests(unittest.TestCase):
    def test_financial_month_uses_invoice_only_for_credit(self):
        row={'data':'2026-10-18','mes_fatura':'11/2026','forma_pagamento':'Cartão de Crédito'}
        self.assertEqual(financial_month(row),'2026-11')
        for method in ('Pix','Boleto','Cartão de Débito','Dinheiro','Fixo Recorrente'):
            self.assertEqual(financial_month(dict(row,forma_pagamento=method)),'2026-10')
        self.assertEqual(financial_month(dict(row,mes_fatura='invalid')),'2026-10')
    def test_customer_card_omits_bank_name(self):
        self.repo.data['clientes']=[{'id':90,'usuario_id':1,'nome':'Synthetic client','telefone':'11900000000','valor':10,'status':'Pendente','conta_id':10}]
        screen=self.flow.enter(100,'clientes')
        self.assertNotIn('Conta:',screen.cards[0][0]);self.assertNotIn('Conta A',screen.cards[0][0]);self.assertNotIn('Conta privada',screen.cards[0][0])
    def test_customer_bank_selection_rejects_foreign_owner(self):
        s=self.flow.session(100);s.table='clientes';s.fields=[('conta_id','Conta bancária','account_optional')];s.field_index=0
        self.flow.prompt(s)
        with self.assertRaises(FlowError): self.flow.field_value(s,12)
        self.assertEqual(self.repo.commands,[])
    def test_menu_hides_blocked_modules(self):
        self.repo.allowed=lambda owner,module: module=='clientes'
        screen=self.flow.enter(100,'menu')
        self.assertEqual([label for label,_ in screen.buttons],['Clientes'])
    def test_raw_amount_cannot_bypass_new_launch_permission(self):
        def blocked(owner,module):
            if module=='novo_lancamento': raise FlowError('Módulo bloqueado.')
        self.repo.set_module=blocked
        with self.assertRaises(FlowError): self.flow.text(100,'10')
        self.assertEqual(self.repo.commands,[])
    def setUp(self):
        clock=patch('bot_flows.today',return_value=date(2026,10,10));clock.start();self.addCleanup(clock.stop)
        self.repo=MemoryRepository();self.flow=FinanceFlow(self.repo);self.screen=self.flow.enter(100)
    def click(self,label):
        raw=next(value for text,value in self.screen.buttons if text==label)
        self.screen=self.flow.callback(100,raw);return self.screen
    def say(self,text): self.screen=self.flow.text(100,text);return self.screen
    def expense(self,method='Crédito',mode='À vista'):
        self.say('10');self.click('Despesa');self.click(method)
        self.click('Cartão A' if method=='Crédito' else 'Conta A')
        self.click(mode)
        if mode=='Fixo / recorrente': self.click('Parcelado / mensal')
        if mode!='À vista': self.click('3')
        self.say('Mercado')
    def test_amount_can_become_income_without_credit(self):
        self.say('10');self.click('Receita')
        self.assertEqual(self.flow.session(100).draft['valor'],10)
        self.assertNotIn('Crédito',[label for label,_ in self.screen.buttons])
        self.assertEqual(self.repo.commands,[])
    def test_quick_launch_goes_from_description_to_review_with_safe_defaults(self):
        self.expense('Pix')
        s=self.flow.session(100)
        self.assertEqual(s.step,'confirm');self.assertEqual(s.draft['data'],'2026-10-10')
        self.assertEqual(s.draft['categoria'],'Outros');self.assertIsNone(s.draft['tags'])
        self.assertFalse(s.draft['pago']);self.assertEqual(self.repo.commands,[])
        old_confirm=self.screen.buttons[0][1]
        self.click('Data');self.click('Amanhã')
        self.assertEqual(self.flow.session(100).command['dados']['registros'][0]['data'],'2026-10-11')
        with self.assertRaises(FlowError): self.flow.callback(100,old_confirm)
        self.click('Categoria');self.click('Outra categoria');self.say('Alimentação');self.click('Confirmar e salvar')
        row=self.repo.commands[-1][1]['dados']['registros'][0]
        self.assertEqual(row['categoria'],'Alimentação');self.assertEqual(row['data'],'2026-10-11')
    def test_quick_credit_review_does_not_offer_direct_paid_status(self):
        self.expense('Crédito')
        self.assertNotIn('Pago / recebido?',[t for t,_ in self.screen.buttons])
        with self.assertRaises(FlowError): self.flow.dispatch(self.flow.session(100),('quick_field','pago'))
        self.assertEqual(self.repo.commands,[])
    def test_launch_category_choices_match_budget_names_and_amount_is_reais(self):
        self.assertEqual(amount('10'),10)
        self.expense('Pix');self.click('Categoria')
        labels=[t for t,_ in self.screen.buttons]
        self.assertEqual(labels[:4],['Outros','Cartão de Crédito','Moradia','Outra categoria'])
        self.click('Moradia');self.click('Confirmar e salvar')
        self.assertEqual(self.repo.commands[-1][1]['dados']['registros'][0]['categoria'],'Moradia')
    def test_fixed_single_keeps_full_value_and_original_date(self):
        self.say('10');self.click('Despesa');self.click('Boleto');self.click('Conta A');self.click('Fixo / recorrente');self.click('Único')
        self.assertEqual(self.flow.session(100).draft['quantidade'],1)
        rows=launch_rows({'valor':10,'quantidade':1,'modalidade':'Fixo / Recorrente','data':'2026-10-31','descricao':'Fixo'})
        self.assertEqual([(r['valor'],r['data']) for r in rows],[(10,'2026-10-31')])
        self.assertEqual(self.repo.commands,[])
    def test_client_cards_resolve_owner_and_confirm_delete(self):
        self.repo.data['clientes']=[{'id':8,'usuario_id':1,'nome':'Ana','telefone':'65999990000','valor':50,'status':'Pendente','data_vencimento':'2026-10-20','_versao':'v'}, {'id':9,'usuario_id':2,'nome':'Privado','valor':99}]
        self.screen=self.flow.enter(100,'clientes')
        self.assertEqual(len(self.screen.cards),1);self.assertIn('20/10/2026',self.screen.cards[0][0])
        raw=self.screen.cards[0][1][1][1]
        with self.assertRaises(FlowError): self.flow.callback(200,raw)
        self.screen=self.flow.callback(100,raw)
        self.assertEqual(self.repo.commands,[]);self.click('Confirmar exclusão')
        self.assertEqual(self.repo.commands[-1][1]['id'],8)
    def test_card_list_shows_selected_month_total_and_due(self):
        self.repo.data['movimentacoes']=[{'id':1,'usuario_id':1,'tipo':'Despesa','valor':40,'cartao_id':20,'forma_pagamento':'Cartão de Crédito','mes_fatura':'02/2027','pago':False}]
        self.flow.session(100).month='2027-02';self.repo.data['cartoes'][0]['dia_vencimento']=31
        screen=self.flow.enter(100,'cartoes')
        self.assertIn('28/02/2027',screen.cards[0][0]);self.assertIn('Fatura do mês: R$ 40,00',screen.cards[0][0])
    def test_summary_groups_and_splits_without_losing_records(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['movimentacoes']=[{'id':i,'usuario_id':1,'tipo':'Despesa','valor':1,'data':'2026-10-10','forma_pagamento':'Cartão de Débito','descricao':f'Compra {i} '+('x'*120)} for i in range(80)]
        self.repo.data['movimentacoes'] += [{'id':90,'usuario_id':1,'tipo':'Despesa','valor':20,'data':'2026-09-01','mes_fatura':'10/2026','cartao_id':20,'forma_pagamento':'Cartão de Crédito','pago':False}]
        screen=self.flow.enter(100,'resumo');report=screen.document or screen.text
        self.assertIn('Despesas: R$ 100,00',report)
        for i in range(80): self.assertIn(f'Compra {i} ',report)
        self.assertIn('05/10/2026 — Cartão A | R$ 20,00',report)
        self.assertTrue(all(len(text)<=3500 for text,_ in screen.cards))
        self.assertTrue(screen.document);self.assertEqual(screen.cards,[])
    def test_small_summary_is_one_complete_message(self):
        screen=self.flow.enter(100,'resumo')
        self.assertIn('RECEITAS / ENTRADAS',screen.text);self.assertIn('GASTOS FIXOS / RECORRENTES',screen.text)
        self.assertFalse(screen.document);self.assertEqual(screen.cards,[])
    def test_all_clients_and_no_limit_beside_card_name(self):
        self.repo.data['clientes']=[{'id':i,'usuario_id':1,'nome':f'Cliente {i}','valor':1,'_versao':'v'} for i in range(15)]
        screen=self.flow.enter(100,'clientes')
        self.assertEqual(len(screen.cards),15);self.assertNotIn('Próxima',[t for t,_ in screen.buttons])
        screen=self.flow.enter(100,'cartoes')
        self.assertIn('Cartão A',screen.cards[0][0]);self.assertNotIn('1.000,00',screen.cards[0][0])
    def test_all_month_movements_are_cards_and_edit_uses_owned_snapshot(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['movimentacoes']=[{'id':i,'usuario_id':1,'tipo':'Despesa','valor':1,'data':'2026-10-10','descricao':f'Item {i}','forma_pagamento':'Pix','_versao':'v'} for i in range(25)]
        self.repo.data['movimentacoes'] += [{'id':99,'usuario_id':2,'tipo':'Despesa','valor':9,'data':'2026-10-10'}, {'id':100,'usuario_id':1,'tipo':'Despesa','valor':9,'data':'2026-11-10'}]
        for row in self.repo.data['movimentacoes'][:25]: row['created_at']='2026-10-10T12:00:00Z'
        screen=self.flow.enter(100,'listar');self.assertEqual(len(screen.cards),25)
        raw=next(v for label,v in screen.cards[0][1] if 'Editar' in label)
        with self.assertRaises(FlowError): self.flow.callback(200,raw)
        screen=self.flow.callback(100,raw);self.assertIn('O que deseja alterar',screen.text)
        self.assertEqual(self.repo.commands,[])
    def test_due_cards_include_entire_month_and_payment_is_confirmed(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['movimentacoes']=[{'id':i,'usuario_id':1,'tipo':'Despesa','valor':5,'data':'2026-10-10','descricao':f'Boleto {i}','forma_pagamento':'Boleto','pago':i==0,'_versao':'v'} for i in range(20)]
        self.repo.data['movimentacoes'] += [{'id':99,'usuario_id':1,'tipo':'Despesa','valor':9,'data':'2026-11-10','forma_pagamento':'Boleto'}, {'id':100,'usuario_id':1,'tipo':'Receita','valor':9,'data':'2026-10-10'}]
        screen=self.flow.enter(100,'vencimentos');self.assertEqual(len(screen.cards),22)
        paid=next(card for card in screen.cards if 'Boleto 0\n' in card[0]);self.assertFalse(any('Pagar' in label for label,_ in paid[1]))
        raw=next(v for label,v in screen.cards[1][1] if 'Pagar' in label)
        self.screen=self.flow.callback(100,raw);self.assertEqual(self.repo.commands,[])
        self.click('Confirmar e salvar');self.assertEqual(self.repo.commands[-1][1]['dados'],{'pago':True})
    def test_due_pending_first_and_paid_section_only_when_populated(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['movimentacoes']=[{'id':1,'usuario_id':1,'tipo':'Despesa','valor':5,'data':'2026-10-15','descricao':'Conta pendente','forma_pagamento':'Boleto','pago':False,'_versao':'v'}]
        screen=self.flow.enter(100,'vencimentos')
        self.assertTrue(screen.cards[0][0].startswith('⏳ PENDENTES'))
        self.assertFalse(any(text.startswith('✅ PAGOS') for text,_ in screen.cards))
        raw=next(v for label,v in screen.cards[1][1] if 'Pagar' in label)
        self.screen=self.flow.callback(100,raw);self.assertEqual(self.repo.commands,[])
        original=self.repo.command
        def save(owner,command):
            result=original(owner,command)
            if command['acao']=='editar': self.repo.data['movimentacoes'][0].update(command['dados'])
            return result
        self.repo.command=save
        self.click('Confirmar e salvar')
        self.assertIn('Pagamento registrado',self.screen.text)
        self.assertTrue(self.screen.cards[0][0].startswith('✅ PAGOS'))
        self.assertFalse(any('Pagar' in label for _,buttons in self.screen.cards for label,_ in buttons))
        self.assertFalse(any(text.startswith('⏳ PENDENTES') for text,_ in self.screen.cards))
    def test_card_pay_uses_selected_invoice_and_requires_confirmation(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['movimentacoes']=[{'id':1,'usuario_id':1,'tipo':'Despesa','valor':45,'mes_fatura':'10/2026','cartao_id':20,'forma_pagamento':'Cartão de Crédito','pago':False}]
        screen=self.flow.enter(100,'cartoes');self.assertEqual(len(screen.cards),1)
        raw=next(v for label,v in screen.cards[0][1] if 'Pagar fatura' in label)
        self.screen=self.flow.callback(100,raw);self.assertIn('R$ 45,00',self.screen.text)
        self.assertTrue(all(c['acao']=='fatura' for _,c in self.repo.commands))
        self.click('Confirmar pagamento');self.assertEqual(self.repo.commands[-1][1]['acao'],'quitar_fatura')
        self.assertEqual(self.repo.commands[-1][1]['dados'],{'competencia':'10/2026'})
    def test_movements_group_credit_by_owned_card_and_today_even_for_next_invoice(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['cartoes'][0]['nome_cartao']='Mercado Pago'
        self.repo.data['cartoes'].append({'id':22,'usuario_id':1,'nome_cartao':'Outro banco','dia_vencimento':12,'limite':1000})
        self.repo.data['movimentacoes']=[{'id':i,'usuario_id':1,'tipo':'Despesa','valor':value,'data':when,'mes_fatura':month,'cartao_id':card,'forma_pagamento':'Cartão de Crédito','descricao':'Compra','pago':paid} for i,value,when,month,card,paid in [(1,10,'2026-09-25','10/2026',20,False),(2,20,'2026-10-01','10/2026',20,True),(3,99,'2026-10-25','11/2026',20,False),(4,5,'2026-10-01','10/2026',22,False)]]
        for row in self.repo.data['movimentacoes']:
            if row['id']!=3: row['created_at']='2026-10-10T12:00:00Z'
        self.repo.data['movimentacoes'][0]['mes_fatura']='11/2026'
        screen=self.flow.enter(100,'listar');self.assertEqual(len(screen.cards),2)
        mercado=next(c for c in screen.cards if 'Mercado Pago' in c[0]);self.assertIn('Valor: R$ 30,00',mercado[0]);self.assertIn('Pendente nos registros de hoje: R$ 10,00',mercado[0]);self.assertIn('2 lançamento(s)',mercado[0])
        self.assertNotIn('R$ 99,00','\n'.join(t for t,_ in screen.cards))
        self.flow.session(100).search='mercado';screen=self.flow.list_rows(self.flow.session(100));self.assertEqual(len(screen.cards),1)
        self.assertIn('R$ 30,00',screen.cards[0][0]);self.assertEqual(self.repo.commands,[])
    def test_today_empty_does_not_show_yesterday_future_or_other_owner(self):
        self.repo.data['movimentacoes']=[{'id':1,'usuario_id':1,'data':'2026-10-09','tipo':'Receita','valor':5},{'id':2,'usuario_id':1,'data':'2026-10-11','tipo':'Despesa','valor':5},{'id':3,'usuario_id':2,'data':'2026-10-10','tipo':'Despesa','valor':5}]
        screen=self.flow.enter(100,'listar');self.assertEqual(screen.cards,[])
        self.assertIn('Não temos lançamentos na data de hoje.',screen.text)
        with patch('bot_flows.today',return_value=date(2026,10,11)):
            self.repo.data['movimentacoes'][1]['created_at']='2026-10-11T12:00:00Z'
            screen=self.flow.enter(100,'listar');self.assertEqual(len(screen.cards),1)
            self.assertIn('11/10/2026',screen.text)
    def test_actual_creation_time_is_independent_from_due_date_and_uses_cuiaba(self):
        self.repo.data['movimentacoes']=[{'id':i,'usuario_id':1,'tipo':'Despesa','valor':1,'data':due,'created_at':created,'descricao':f'Item {i}'} for i,due,created in [(1,'2026-12-10','2026-10-10T04:00:00Z'),(2,'2026-10-10','2026-10-10T03:59:59Z'),(3,'2026-10-10',None),(4,'2026-10-09','2026-10-10T22:00:00Z')]]
        screen=self.flow.enter(100,'listar');self.assertEqual(len(screen.cards),2)
        text='\n'.join(t for t,_ in screen.cards)
        self.assertIn('Item 1',text);self.assertIn('Item 4',text);self.assertNotIn('Item 2',text);self.assertNotIn('Item 3',text)
    def test_unknown_command_explains_commands_without_writes(self):
        screen=self.flow.enter(100,'errado')
        for command in ('/menu','/clientes','/cartoes','/cancelar'): self.assertIn(command,screen.text)
        self.assertEqual(self.repo.commands,[])
    def test_goal_deposit_and_withdraw_use_version_and_confirmation(self):
        self.record('metas',{'nome_meta':'Reserva','valor_alvo':100,'valor_poupado':70})
        self.click('Depositar');self.say('10');self.assertEqual(self.repo.commands,[])
        self.click('Confirmar e salvar');self.assertEqual(self.repo.commands[-1][1]['dados'],{'valor_poupado':80});self.assertEqual(self.repo.commands[-1][1]['versao'],'original-version')
        self.record('metas',{'nome_meta':'Reserva','valor_alvo':100,'valor_poupado':70})
        self.click('Resgatar')
        with self.assertRaises(FlowError): self.say('71')
        self.say('20');self.click('Confirmar e salvar');self.assertEqual(self.repo.commands[-1][1]['dados'],{'valor_poupado':50})
    def test_due_undo_payment_is_confirmed_and_returns_to_pending(self):
        self.flow.session(100).month='2026-10'
        self.repo.data['movimentacoes']=[{'id':1,'usuario_id':1,'descricao':'Boleto pago','tipo':'Despesa','valor':20,'data':'2026-10-20','forma_pagamento':'Boleto','pago':True,'_versao':'v'}]
        screen=self.flow.enter(100,'vencimentos');raw=next(value for text,buttons in screen.cards for label,value in buttons if 'Desfazer pagamento' in label)
        self.screen=self.flow.callback(100,raw);self.assertEqual(self.repo.commands,[])
        original=self.repo.command
        def save(owner,command):
            result=original(owner,command)
            if command['acao']=='editar': self.repo.data['movimentacoes'][0].update(command['dados'])
            return result
        self.repo.command=save;self.click('Confirmar e salvar');self.assertIn('Pagamento desfeito',self.screen.text);self.assertTrue(self.screen.cards[0][0].startswith('⏳ PENDENTES'))
    def test_value_only_asks_payment_first_and_shows_only_owned_accounts(self):
        self.say('10');self.assertIn('receita ou uma despesa',self.screen.text);self.click('Despesa');self.assertIn('meio de pagamento',self.screen.text)
        self.click('Pix');labels=[t for t,_ in self.screen.buttons]
        self.assertIn('Conta A',labels);self.assertIn('Conta B',labels);self.assertNotIn('Conta privada',labels)
        self.assertEqual(self.repo.commands,[])
    def test_credit_cards_and_installments_are_confirmed_before_write(self):
        self.expense(mode='Parcelado');self.assertEqual(self.repo.commands,[])
        self.assertIn('3 lançamento(s)',self.screen.text);self.assertIn('10,00',self.screen.text)
        self.click('Confirmar e salvar');owner,command=self.repo.commands[-1]
        self.assertEqual(owner,1);self.assertEqual(command['acao'],'criar_lote')
        rows=command['dados']['registros'];self.assertEqual(len(rows),3)
        self.assertTrue(all(r['cartao_id']==20 and r['conta_id'] is None and not r['pago'] for r in rows))
        self.assertTrue(all('usuario_id' not in r for r in rows))
    def test_pix_debit_boleto_and_cash_link_account_not_card(self):
        for method in ('Pix','Débito','Boleto','Dinheiro'):
            with self.subTest(method=method):
                self.screen=self.flow.enter(100);self.expense(method)
                self.click('Confirmar e salvar');row=self.repo.commands[-1][1]['dados']['registros'][0]
                self.assertEqual(row['conta_id'],10);self.assertIsNone(row['cartao_id'])
    def test_single_account_auto_selects_but_single_card_is_a_button(self):
        self.repo.data['contas']=[self.repo.data['contas'][0]]
        self.say('10');self.click('Despesa');self.click('Pix');self.assertIn('Selecionado: Conta A',self.screen.text)
        self.screen=self.flow.enter(100);self.say('10');self.click('Despesa');self.click('Crédito');self.assertIn('Cartão A',[t for t,_ in self.screen.buttons])
    def test_recurring_uses_full_amount_and_pending_future_entries(self):
        self.expense('Boleto','Fixo / recorrente');self.click('Confirmar e salvar')
        rows=self.repo.commands[-1][1]['dados']['registros'];self.assertEqual([r['valor'] for r in rows],[10]*3)
        self.assertTrue(all(not r['pago'] for r in rows))
    def test_income_uses_account_and_never_offers_credit(self):
        self.click('Nova receita');self.say('2500');self.assertNotIn('Crédito',[t for t,_ in self.screen.buttons])
        self.click('Pix');self.click('Conta A');self.click('À vista');self.say('Salário');self.click('Categoria');self.click('Outra categoria');self.say('Salário');self.click('Pago / recebido?');self.click('Sim');self.click('Confirmar e salvar')
        self.assertEqual(self.repo.commands[-1][1]['dados']['registros'][0]['tipo'],'Receita')
    def test_old_foreign_and_double_confirmation_callbacks_rejected(self):
        self.expense();raw=self.screen.buttons[0][1]
        with self.assertRaises(FlowError): self.flow.callback(200,raw)
        self.click('Confirmar e salvar')
        with self.assertRaises(FlowError): self.flow.callback(100,raw)
        self.assertEqual(len(self.repo.commands),1)
    def test_changed_or_inactive_link_invalidates_draft(self):
        self.expense();raw=self.screen.buttons[0][1];self.repo.links[100]=2
        with self.assertRaises(FlowError): self.flow.callback(100,raw)
        self.repo.links.pop(100)
        with self.assertRaises(FlowError): self.flow.text(100,'10')
        self.assertEqual(self.repo.commands,[])
    def test_ambiguous_network_retry_reuses_same_idempotency_key_and_payload(self):
        self.expense();self.repo.failed=True;self.click('Confirmar e salvar');self.repo.failed=False;self.click('Tentar novamente')
        self.assertEqual(self.repo.commands[0],self.repo.commands[1])
    def test_cancel_never_writes(self):
        self.expense();self.click('Menu / cancelar');self.assertEqual(self.repo.commands,[])
    def test_edit_payment_selects_owned_reference_and_clears_opposite_reference(self):
        self.record('movimentacoes');self.click('Editar');self.click('Meio de pagamento');self.click('Crédito');self.click('Cartão A');self.click('Confirmar e salvar')
        self.assertEqual(self.repo.commands[-1][1]['dados'],{'forma_pagamento':'Cartão de Crédito','cartao_id':20,'conta_id':None})
    def test_invoice_all_purchases_are_accessible_by_pages(self):
        self.repo.data['movimentacoes']=[{'id':i,'usuario_id':1,'descricao':f'Compra {i}','valor':1,'tipo':'Despesa','pago':False,'cartao_id':20,'forma_pagamento':'Cartão de Crédito','mes_fatura':'10/2026','_versao':'v'} for i in range(30,45)]
        s=self.flow.session(100);s.table='cartoes';s.card=20;s.month='2026-10';self.screen=self.flow.invoice(s);self.click('Mais compras');self.click('Mais compras');self.assertIn('Compra 44',self.screen.text)
        self.click('Compra 44 · R$ 1,00');self.assertEqual(self.flow.session(100).row['id'],44)
    def test_generic_create_all_resource_types(self):
        scenarios={
            'Contas':['Minha conta','100,50'],
            'Cartões e faturas':['Meu cartão','1000','31','10'],
            'Recebimentos':['Cliente pagará','30','@Hoje','@Não'],
            'Clientes':['Cliente exemplo','65999990000','50','@Sem data','@Pendente','@Não vincular conta'],
            'Metas':['Reserva','10000','300','@Amanhã'],
            'Orçamentos':['@Orçamento geral','1000']}
        for module,answers in scenarios.items():
            with self.subTest(module=module):
                self.screen=self.flow.enter(100);self.click(module);self.click('Novo cadastro')
                for answer in answers: self.click(answer[1:]) if answer.startswith('@') else self.say(answer)
                self.click('Confirmar e salvar');self.assertEqual(self.repo.commands[-1][1]['acao'],'criar')
    def record(self,table,extra=None):
        row={'id':88,'usuario_id':1,'_versao':'original-version','descricao':'Registro','valor':30,'data':'2026-10-10','categoria':'Outros','pago':False,'forma_pagamento':'Pix','conta_id':10}
        row.update(extra or {});self.repo.data[table].append(row);s=self.flow.session(100);s.table=table
        self.screen=self.flow.detail(s,88)
    def test_edit_delete_and_toggle_use_snapshot_version(self):
        self.record('movimentacoes');self.click('Editar');self.click('Valor');self.say('42,10');self.click('Confirmar e salvar')
        command=self.repo.commands[-1][1];self.assertEqual(command['dados'],{'valor':42.1});self.assertEqual(command['versao'],'original-version')
        self.record('clientes',{'nome':'Cliente','telefone':'6599999999','status':'Pendente'})
        self.click('Alterar pagamento / recebimento');self.click('Confirmar e salvar');self.assertEqual(self.repo.commands[-1][1]['dados'],{'status':'Pago'})
        self.record('contas_receber',{'recebido':False});self.click('Alterar pagamento / recebimento');self.click('Confirmar e salvar');self.assertEqual(self.repo.commands[-1][1]['dados'],{'recebido':True})
        self.record('metas',{'nome_meta':'Meta','valor_alvo':100,'valor_poupado':0});self.click('Excluir');self.assertIn('excluir',self.screen.text);self.click('Confirmar exclusão');self.assertEqual(self.repo.commands[-1][1]['acao'],'excluir')
    def test_invoice_uses_month_and_pending_future_credit_for_available_limit(self):
        self.record('movimentacoes',{'cartao_id':20,'forma_pagamento':'Cartão de Crédito','mes_fatura':'10/2026'})
        self.repo.data['movimentacoes'].append({'id':89,'usuario_id':1,'descricao':'Parcela futura','valor':100,'tipo':'Despesa','pago':False,'cartao_id':20,'forma_pagamento':'Cartão de Crédito','mes_fatura':'11/2026'})
        self.repo.data['movimentacoes'][0]['tipo']='Despesa'
        s=self.flow.session(100);s.table='cartoes';s.card=20;s.month='2026-10';self.screen=self.flow.invoice(s)
        self.assertIn('Gasto do mês: R$ 30,00',self.screen.text);self.assertIn('Limite disponível: R$ 870,00',self.screen.text)
        self.click('Registrar pagamento da fatura');self.click('Confirmar e salvar') if any(t=='Confirmar e salvar' for t,_ in self.screen.buttons) else self.click('Confirmar pagamento')
        command=self.repo.commands[-1][1];self.assertEqual(command['acao'],'quitar_fatura');self.assertEqual(command['dados'],{'competencia':'10/2026'});self.assertEqual(command['versao'],'invoice-1')
    def test_pagination_and_month_change(self):
        for i in range(15): self.repo.data['contas_receber'].append({'id':100+i,'usuario_id':1,'descricao':f'Previsto {i}','valor':1,'data_recebimento':'2026-10-20','_versao':'v'})
        self.flow.session(100).month='2026-10';self.screen=self.flow.enter(100,'receber');self.click('Próxima');self.assertEqual(self.flow.session(100).page,1)
        self.click('Alterar mês');self.click('Outro mês / ano');self.say('11/2026');self.assertIn('0 registro(s)',self.screen.text)
    def test_date_and_amount_validation_do_not_advance_or_write(self):
        for raw in ('nan','-10','10.0001','1e10','0','1000001'):
            with self.assertRaises(FlowError): amount(raw)
        self.assertEqual(amount('1.234,56'),1234.56);self.assertEqual(amount('10.50'),10.5)
        with self.assertRaises(FlowError): launch_rows({'valor':10,'quantidade':73,'modalidade':'Parcelado','data':'2026-10-15','descricao':'x'})
    def test_callbacks_are_small_and_expire_after_restart_or_timeout(self):
        self.assertTrue(all(len(raw.encode())<=64 for _,raw in self.screen.buttons));raw=self.screen.buttons[0][1]
        self.flow.sessions[100].touched-=7201
        with self.assertRaises(FlowError): self.flow.callback(100,raw)

class RepositoryTests(unittest.TestCase):
    def test_trial_expiry_blocks_authorization_and_explains_contract(self):
        db=MagicMock();query=db.table.return_value.select.return_value;query.eq.return_value=query;query.limit.return_value=query;query.execute.return_value.data=[{'id':7}]
        db.rpc.return_value.execute.return_value.data={'allowed':False,'message':'Seu teste de 7 dias terminou.','contact':'5565992361636'}
        with self.assertRaises(FlowError) as caught: SupabaseRepository(db).authorize(100)
        self.assertIn('7 dias',str(caught.exception));self.assertIn('wa.me/5565992361636',str(caught.exception))
    def test_blocked_module_is_not_selected_and_context_is_sent_to_rpc(self):
        db=MagicMock();repo=SupabaseRepository(db);repo.context.owner=7;repo.context.access={'allowed':True,'modules':{'clientes':False,'contas':True}}
        with self.assertRaises(FlowError): repo.set_module(7,'clientes')
        repo.set_module(7,'contas');db.rpc.return_value.execute.return_value.data={'registros':[]};repo.rows(7,'contas')
        self.assertEqual(db.rpc.call_args.args[1]['p_modulo'],'contas')
    def test_licensed_user_does_not_keep_trial_expiry(self):
        db=MagicMock();query=db.table.return_value.select.return_value;query.eq.return_value=query;query.limit.return_value=query;query.execute.return_value.data=[{'id':7}]
        db.rpc.return_value.execute.return_value.data={'allowed':True,'mode':'licensed','expires_at':None,'modules':{'clientes':True}}
        repo=SupabaseRepository(db);self.assertEqual(repo.authorize(100),7);self.assertTrue(repo.allowed(7,'clientes'))
    def test_authorization_requires_unique_active_link(self):
        db=MagicMock();query=db.table.return_value.select.return_value;query.eq.return_value=query;query.limit.return_value=query;query.execute.return_value.data=[{'id':1},{'id':2}]
        repo=SupabaseRepository(db);self.assertIsNone(repo.authorize(100));query.eq.assert_any_call('status','ativo');query.eq.assert_any_call('telegram_id',100)
        query.execute.return_value.data=[{'id':1}];db.rpc.return_value.execute.return_value.data={'allowed':True,'modules':{}};self.assertEqual(repo.authorize(100),1)
    def test_binding_rejects_ambiguous_phone_and_already_linked_other_telegram(self):
        for rows in [[{'id':1,'telefone':'65999990000','telegram_id':None},{'id':2,'telefone':'65999990000','telegram_id':None}],[{'id':1,'telefone':'65999990000','telegram_id':200}]]:
            db=MagicMock();query=db.table.return_value.select.return_value;query.eq.return_value=query;query.limit.return_value=query;query.execute.return_value.data=rows
            repo=SupabaseRepository(db);repo.authorize=lambda _:None
            with self.assertRaises(FlowError): repo.bind_contact(100,'5565999990000')
            db.table.return_value.update.assert_not_called()
    def test_fixed_rpc_and_owner_not_client_controlled(self):
        db=MagicMock();db.rpc.return_value.execute.return_value.data={'registros':[]};repo=SupabaseRepository(db)
        repo.rows(7,'contas');name,payload=db.rpc.call_args.args;self.assertEqual(name,'fp_financeiro_modulo_v1');self.assertEqual(payload['p_usuario'],7)
        with self.assertRaises(FlowError): repo.command(7,{'tabela':'contas','acao':'listar','usuario_id':8})
        with self.assertRaises(FlowError): repo.rows(7,'usuarios')
    def test_error_never_exposes_backend_details(self):
        db=MagicMock();db.rpc.return_value.execute.side_effect=Exception('SECRET data token');repo=SupabaseRepository(db)
        with self.assertRaises(FlowError) as caught: repo.rows(1,'contas')
        self.assertNotIn('SECRET',str(caught.exception))
    def test_phone_variants(self): self.assertTrue(SupabaseRepository.phone_variants('(65) 99999-0000') & SupabaseRepository.phone_variants('5565999990000'))
    def test_reminders_filter_active_owner_current_telegram_and_ambiguous_links(self):
        source=ast.parse((Path(__file__).parent/'lembrete_boletos.py').read_text(encoding='utf-8-sig'))
        node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='consultar_view')
        db=MagicMock();view=MagicMock();view.select.return_value=view;view.eq.return_value=view;view.execute.return_value.data=[{'usuario_id':1,'telegram_id':100},{'usuario_id':2,'telegram_id':200},{'usuario_id':3,'telegram_id':999}]
        users=MagicMock();users.select.return_value=users;users.eq.return_value=users;users.execute.return_value.data=[{'id':1,'telegram_id':100},{'id':3,'telegram_id':300}]
        db.table.side_effect=lambda table:users if table=='usuarios' else view
        namespace={'supabase':db,'logging':logging};exec(compile(ast.Module(body=[node],type_ignores=[]),'<reminder-auth>','exec'),namespace)
        self.assertEqual(namespace['consultar_view']('lancamentos_hoje'),[{'usuario_id':1,'telegram_id':100}]);users.eq.assert_any_call('status','ativo')

class AdapterTests(unittest.TestCase):
    def setUp(self):
        telegram=types.ModuleType('telegram');ext=types.ModuleType('telegram.ext')
        for name in ('InlineKeyboardButton','InlineKeyboardMarkup','KeyboardButton','ReplyKeyboardMarkup'): setattr(telegram,name,lambda *a,**k:(a,k))
        for name in ('CommandHandler','CallbackQueryHandler','MessageHandler'): setattr(ext,name,lambda *a,**k:(a,k))
        ext.filters=MagicMock()
        self.old={k:sys.modules.get(k) for k in ('telegram','telegram.ext')};sys.modules.update({'telegram':telegram,'telegram.ext':ext})
        spec=importlib.util.spec_from_file_location('tested_bot_ui',Path(__file__).parent/'bot_ui.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        async def inline(function,*args): return function(*args)
        self.module=module;self.old_thread=module.asyncio.to_thread;module.asyncio.to_thread=inline
        self.adapter=module.TelegramFinance(MagicMock());self.repo=MemoryRepository();self.adapter.repository=self.repo;self.adapter.flow=FinanceFlow(self.repo)
    def tearDown(self):
        self.module.asyncio.to_thread=self.old_thread
        for key,value in self.old.items():
            if value is None: sys.modules.pop(key,None)
            else: sys.modules[key]=value
    def run_coro(self,coro):
        try: coro.send(None)
        except StopIteration as done: return done.value
        self.fail('Unexpected external asynchronous operation')
    def update(self,kind='private',contact=None,forward=None):
        sent=[]
        async def reply(text,**kwargs): sent.append((text,kwargs))
        message=types.SimpleNamespace(text='10',contact=contact,forward_origin=forward,reply_text=reply)
        return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=100),effective_chat=types.SimpleNamespace(type=kind),effective_message=message,callback_query=None),sent
    def test_group_never_authorizes_or_replies_with_data(self):
        update,sent=self.update('group');self.repo.authorize=MagicMock(side_effect=Exception('must not run'))
        self.run_coro(self.adapter.text(update,None));self.assertEqual(sent,[]);self.repo.authorize.assert_not_called()
    def test_foreign_and_forwarded_contacts_never_bind(self):
        for contact,forward in [(types.SimpleNamespace(user_id=200,phone_number='12345678'),None),(types.SimpleNamespace(user_id=100,phone_number='12345678'),object())]:
            update,sent=self.update(contact=contact,forward=forward);self.repo.bind_contact=MagicMock()
            self.run_coro(self.adapter.contact(update,None));self.repo.bind_contact.assert_not_called();self.assertTrue(sent)
    def test_private_amount_renders_inline_payment_buttons(self):
        update,sent=self.update();self.run_coro(self.adapter.text(update,None));self.assertIn('receita ou uma despesa',sent[-1][0]);self.assertIn('reply_markup',sent[-1][1]);self.assertEqual(self.repo.commands,[])
    def test_unlinked_user_cannot_start_financial_operation(self):
        self.repo.links.clear();update,sent=self.update();self.run_coro(self.adapter.text(update,None));self.assertIn('sem vínculo',sent[-1][0]);self.assertEqual(self.repo.commands,[])
    def test_new_result_deletes_old_messages_with_keyboard_fallback(self):
        events=[]
        async def delete_ok(): events.append('deleted')
        async def delete_fail(): raise RuntimeError('too old')
        async def clear(**kwargs): events.append(('cleared',kwargs))
        self.adapter.results[100]=[types.SimpleNamespace(delete=delete_ok),types.SimpleNamespace(delete=delete_fail,edit_reply_markup=clear)]
        update,sent=self.update();self.run_coro(self.adapter.text(update,None))
        self.assertEqual(events,['deleted',('cleared',{'reply_markup':None})]);self.assertEqual(len(sent),1)

if __name__=='__main__': unittest.main()
