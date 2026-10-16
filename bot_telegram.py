"""FinanceiroPro Web — private Telegram financial assistant."""
import logging
import os
from datetime import time
from dotenv import load_dotenv
import pytz
from supabase import create_client, ClientOptions
from telegram import BotCommand
from telegram.ext import ApplicationBuilder
from bot_ui import install

load_dotenv()
logging.basicConfig(level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

async def setup(application):
    await application.bot.set_my_commands([
        BotCommand('menu','Abrir o menu financeiro'),BotCommand('despesa','Nova despesa'),
        BotCommand('receita','Nova receita'),BotCommand('resumo','Resumo do mês'),
        BotCommand('vencimentos','Contas e faturas pendentes'),BotCommand('cancelar','Cancelar e voltar ao menu')])

async def on_error(update, context):
    logging.error('Erro no bot: %s',type(context.error).__name__)

def main():
    required=['TELEGRAM_TOKEN','SUPABASE_URL','SUPABASE_KEY']
    if not all(os.getenv(key) for key in required):
        raise RuntimeError('Configure as variáveis obrigatórias do bot no Discloud.')
    if not os.environ['SUPABASE_KEY'].startswith('sb_secret_'):
        raise RuntimeError('SUPABASE_KEY ainda usa formato legado. Importe a nova chave secreta nas variáveis protegidas do Discloud e republique o bot.')
    logging.info('Supabase: chave secreta moderna configurada; valor protegido.')
    client=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_KEY'],
                         options=ClientOptions(postgrest_client_timeout=30,storage_client_timeout=30))
    from bot_repository import SupabaseRepository
    active=client.table('usuarios').select('id').eq('status','ativo').limit(1).execute().data
    if active:
        client.rpc('fp_access_v1',{'p_usuario':active[0]['id']}).execute()
        logging.info('Controle de acesso validado em leitura; nenhum registro alterado.')
    app=ApplicationBuilder().token(os.environ['TELEGRAM_TOKEN']).concurrent_updates(False).post_init(setup).build()
    install(app,client)
    app.add_error_handler(on_error)
    from lembrete_boletos import processar_e_enviar_alertas, enviar_resumo_mensal_telegram
    zone=pytz.timezone('America/Sao_Paulo')
    for hour in (9,15):
        app.job_queue.run_daily(processar_e_enviar_alertas,time=time(hour=hour,tzinfo=zone))
    async def monthly(context):
        await enviar_resumo_mensal_telegram(None,context)
    app.job_queue.run_monthly(monthly,when=time(hour=8,tzinfo=zone),day=1)
    logging.info('FinanceiroPro Web: menu financeiro v2 iniciado; aguardando mensagens privadas.')
    app.run_polling(allowed_updates=['message','callback_query'],drop_pending_updates=False)

if __name__=='__main__':
    main()
