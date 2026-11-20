"""Persist delivery outcomes; retry only known, explicit rate-limit rejections."""
import asyncio
import logging

async def deliver_daily(db,bot,messages,sleep=asyncio.sleep):
    async def rpc(name,payload):
        return await asyncio.to_thread(lambda:db.rpc(name,payload).execute().data)
    for owner,chat,message in messages:
        for attempt in range(3):
            base={'p_usuario':owner,'p_telegram':chat}
            if await rpc('fp_telegram_daily_claim_v2',base) is not True:
                break
            try:
                result=await bot.send_message(chat_id=chat,text=message)
            except Exception as error:
                retry=getattr(error,'retry_after',None)
                if retry is not None:
                    seconds=retry.total_seconds() if hasattr(retry,'total_seconds') else float(retry)
                    seconds=min(3600,max(1,int(seconds)+1))
                    await rpc('fp_telegram_daily_finish_v2',{**base,'p_estado':'retry' if attempt<2 else 'failed','p_retry_seconds':seconds})
                    if attempt<2:
                        await sleep(seconds)
                        continue
                else:
                    known=type(error).__name__ in ('BadRequest','Forbidden')
                    await rpc('fp_telegram_daily_finish_v2',{**base,'p_estado':'failed' if known else 'uncertain'})
                logging.error('Alerta diário não confirmado; consulte o estado de entrega. Tipo: %s',type(error).__name__)
                break
            else:
                await rpc('fp_telegram_daily_finish_v2',{**base,'p_estado':'sent','p_message_id':getattr(result,'message_id',None)})
                logging.info('Resumo diário confirmado e registrado.')
                break
