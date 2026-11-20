import ast
import asyncio
import sys
import unittest
from pathlib import Path
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
sys.path.insert(0,str(Path(__file__).parent))
from daily_alerts import build_daily_alerts

class DailyTests(unittest.TestCase):
    def test_pending_and_isolation(self):
        row={'usuario_id':1,'telegram_id':10,'descricao':'Conta','valor':10}
        result=build_daily_alerts([row,dict(row,pago=True),dict(row,usuario_id=2,telegram_id=20)],[],[dict(row,recebido=True)],date(2026,10,16))
        self.assertEqual(len(result),2)
        self.assertIn('R$ 10,00',result[0][2])
        self.assertNotIn('Recebimentos pendentes',result[0][2])
        self.assertEqual(result[1][:2],(2,20))
    def test_empty(self):
        self.assertEqual(build_daily_alerts([],[],[],date.today()),[])
    def test_length_and_single_summary(self):
        row={'usuario_id':1,'telegram_id':10,'descricao':'x'*150,'valor':100}
        result=build_daily_alerts([row]*500,[dict(row,nome_cartao='Card')],[],date.today())
        self.assertEqual(len(result),1)
        self.assertLess(len(result[0][2]),4096)
        self.assertIn('item(ns)',result[0][2])
    def test_schedule(self):
        source=(Path(__file__).parent/'bot_telegram.py').read_text(encoding='utf-8-sig')
        tree=ast.parse(source)
        jobs=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('run_daily','run_monthly','run_repeating')]
        self.assertEqual(len(jobs),1)
        self.assertIn('hour=10',ast.unparse(jobs[0]))
        self.assertIn('America/Cuiaba',source)
    def test_claim_before_send(self):
        source=(Path(__file__).parent/'lembrete_boletos.py').read_text(encoding='utf-8-sig')
        fn=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='processar_e_enviar_alertas')
        bot=SimpleNamespace(send_message=AsyncMock())
        db=MagicMock();db.rpc.return_value.execute.return_value.data=False
        row={'usuario_id':1,'telegram_id':10,'descricao':'QA','valor':10}
        scope={'bot_global':bot,'supabase':db,'consultar_view':lambda name,**kw:[row] if name=='movimentacoes_hoje' else [],'datetime':datetime,'FUSO_BR':None,'logging':MagicMock()}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'reminder-test','exec'),scope)
        with self.assertRaises(StopIteration): scope[fn.name]().send(None)
        bot.send_message.assert_not_awaited()
        db.rpc.return_value.execute.return_value.data=True
        with self.assertRaises(StopIteration): scope[fn.name]().send(None)
        bot.send_message.assert_awaited_once()

if __name__=='__main__': unittest.main()
