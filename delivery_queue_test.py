import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,MagicMock
from delivery_queue import deliver_daily

class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def db(self):
        db=MagicMock();db.rpc.return_value.execute.return_value.data=True
        return db
    async def test_success_is_persisted_after_single_send(self):
        db=self.db();bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=12)))
        await deliver_daily(db,bot,[(1,10,'synthetic')])
        self.assertEqual(bot.send_message.await_count,1)
        self.assertEqual(db.rpc.call_args_list[-1].args[1]['p_estado'],'sent')
    async def test_uncertain_network_error_is_not_repeated(self):
        db=self.db();bot=SimpleNamespace(send_message=AsyncMock(side_effect=TimeoutError()))
        await deliver_daily(db,bot,[(1,10,'synthetic')])
        self.assertEqual(bot.send_message.await_count,1)
        self.assertEqual(db.rpc.call_args_list[-1].args[1]['p_estado'],'uncertain')
    async def test_known_rate_rejection_retries_then_records_success(self):
        class RateError(Exception):retry_after=0
        db=self.db();sleep=AsyncMock();bot=SimpleNamespace(send_message=AsyncMock(side_effect=[RateError(),SimpleNamespace(message_id=12)]))
        await deliver_daily(db,bot,[(1,10,'synthetic')],sleep=sleep)
        self.assertEqual(bot.send_message.await_count,2)
        self.assertEqual(db.rpc.call_args_list[-1].args[1]['p_estado'],'sent')
        sleep.assert_awaited_once()
    async def test_reserved_or_sent_alert_cannot_send_twice(self):
        db=self.db();db.rpc.return_value.execute.return_value.data=False;bot=SimpleNamespace(send_message=AsyncMock())
        await deliver_daily(db,bot,[(1,10,'synthetic')]);bot.send_message.assert_not_awaited()

class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_users_keep_same_user_fifo_and_release_locks(self):
        source=ast.parse((Path(__file__).parent/'bot_concurrency.py').read_text(encoding='utf-8'))
        node=next(n for n in source.body if isinstance(n,ast.ClassDef))
        class Base:
            def __init__(self,maximum):self.maximum=maximum
        ns={'BaseUpdateProcessor':Base,'asyncio':asyncio};exec(compile(ast.Module(body=[node],type_ignores=[]),'concurrency-test','exec'),ns)
        processor=ns['PerUserProcessor']();release=asyncio.Event();first_started=asyncio.Event();second_user=asyncio.Event();events=[]
        async def first():events.append('a1');first_started.set();await release.wait();events.append('a1-end')
        async def second():events.append('a2')
        async def other():events.append('b1');second_user.set()
        update=lambda user:SimpleNamespace(effective_user=SimpleNamespace(id=user))
        one=asyncio.create_task(processor.do_process_update(update(1),first()));await first_started.wait()
        two=asyncio.create_task(processor.do_process_update(update(1),second()));three=asyncio.create_task(processor.do_process_update(update(2),other()))
        await asyncio.wait_for(second_user.wait(),1);self.assertNotIn('a2',events);release.set();await asyncio.gather(one,two,three)
        self.assertLess(events.index('a1-end'),events.index('a2'));self.assertEqual(processor._users,{})
