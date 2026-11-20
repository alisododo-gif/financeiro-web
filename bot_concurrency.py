"""Parallel users, FIFO updates within each user, bounded lock lifetime."""
import asyncio
from telegram.ext import BaseUpdateProcessor

class PerUserProcessor(BaseUpdateProcessor):
    def __init__(self, maximum=16):
        super().__init__(maximum)
        self._users={}
    async def initialize(self):
        pass
    async def shutdown(self):
        self._users.clear()
    async def do_process_update(self,update,coroutine):
        user=getattr(getattr(update,'effective_user',None),'id',None)
        if user is None:
            await coroutine
            return
        entry=self._users.setdefault(user,[asyncio.Lock(),0])
        entry[1]+=1
        try:
            async with entry[0]:
                await coroutine
        finally:
            entry[1]-=1
            if not entry[1]:
                self._users.pop(user,None)
