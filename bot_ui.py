"""Small python-telegram-bot adapter. Only private, verified Telegram identities."""
import asyncio
import logging
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot_flows import FinanceFlow, FlowError
from bot_repository import SupabaseRepository

class TelegramFinance:
    def __init__(self, client):
        self.repository=SupabaseRepository(client)
        self.flow=FinanceFlow(self.repository)
        self.results={}

    async def close_results(self, update):
        previous=self.results.pop(update.effective_user.id,[])
        if update.callback_query and getattr(update.callback_query,'message',None):
            current=update.callback_query.message
            if all(getattr(m,'message_id',None)!=current.message_id for m in previous): previous.append(current)
        for message in previous:
            try:
                await message.delete()
            except Exception:
                try: await message.edit_reply_markup(reply_markup=None)
                except Exception: pass

    async def private(self, update):
        if not update.effective_user or not update.effective_chat or update.effective_chat.type!='private':
            if update.callback_query: await update.callback_query.answer('Use o bot na conversa privada.',show_alert=True)
            return False
        return True

    async def send(self, update, screen):
        await self.close_results(update)
        sent=[]
        keyboard=InlineKeyboardMarkup([[InlineKeyboardButton(label,callback_data=value)] for label,value in screen.buttons])
        # Send via the bot-bound Message helper even when the triggering message was deleted.
        if screen.document:
            report=BytesIO(screen.document.encode('utf-8'));report.name='resumo-financeiro.txt'
            sent.append(await update.effective_message.reply_document(document=report,caption=screen.text,reply_markup=keyboard,do_quote=False))
        else:
            sent.append(await update.effective_message.reply_text(screen.text,reply_markup=keyboard,do_quote=False))
        self.results[update.effective_user.id]=sent
        for text,buttons in screen.cards:
            markup=InlineKeyboardMarkup([[InlineKeyboardButton(label,callback_data=value) for label,value in buttons]]) if buttons else None
            # Long lists must respect Telegram flood control without dropping cards.
            for attempt in range(3):
                try:
                    sent.append(await update.effective_message.reply_text(text,reply_markup=markup,do_quote=False))
                    break
                except Exception as error:
                    delay=getattr(error,'retry_after',None)
                    if delay is None or attempt==2: raise
                    seconds=delay.total_seconds() if hasattr(delay,'total_seconds') else float(delay)
                    await asyncio.sleep(seconds+0.5)

    async def unlinked(self, update):
        await update.effective_message.reply_text('FinanceiroPro Web\nCompartilhe seu próprio contato pelo botão para vincular a conta ativa. Você não precisa enviar senha.',reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Vincular minha conta',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True))

    async def run(self, update, function, *args):
        if not await self.private(update): return
        try:
            screen=await asyncio.to_thread(function,update.effective_user.id,*args)
            await self.send(update,screen)
        except FlowError as error:
            await update.effective_message.reply_text(str(error))
        except Exception as error:
            # Never log an Update, DB response, contact, URL, token or message body.
            logging.error('Falha no fluxo financeiro: %s',type(error).__name__)
            await update.effective_message.reply_text('Não consegui concluir agora. Use /menu para consultar. Se estava confirmando uma gravação, tente o mesmo botão novamente para evitar duplicar.')

    async def command(self, update, context):
        if not await self.private(update): return
        command=update.effective_message.text.split()[0].split('@')[0].lstrip('/')
        try:
            owner=await asyncio.to_thread(self.repository.authorize,update.effective_user.id)
        except Exception:
            await update.effective_message.reply_text('Não consegui verificar a conta agora. Tente novamente em instantes.')
            return
        if not owner:
            await self.unlinked(update)
            return
        if command in ('start','menu'):
            await update.effective_message.reply_text('Use os botões abaixo ou envie só um valor, como 10.',reply_markup=ReplyKeyboardMarkup([['Menu','Nova despesa','Nova receita'],['Resumo','Vencimentos']],resize_keyboard=True))
        await self.run(update,self.flow.enter,command)

    async def callback(self, update, context):
        if not await self.private(update): return
        await update.callback_query.answer()
        if not str(update.callback_query.data).startswith('fp:'):
            await update.effective_message.reply_text('Esse botão é da versão anterior. Use /menu para continuar com os botões novos.')
            return
        await self.run(update,self.flow.callback,update.callback_query.data)

    async def text(self, update, context):
        text=update.effective_message.text.strip()
        shortcuts={'menu':'menu','nova despesa':'despesa','nova receita':'receita','resumo':'resumo','vencimentos':'vencimentos','cancelar':'cancelar','receber':'receber','pendentes':'receber'}
        if text.casefold() in shortcuts:
            await self.run(update,self.flow.enter,shortcuts[text.casefold()])
        else:
            await self.run(update,self.flow.text,text)

    async def contact(self, update, context):
        if not await self.private(update): return
        contact=update.effective_message.contact
        if not contact or contact.user_id!=update.effective_user.id or getattr(update.effective_message,'forward_origin',None):
            await update.effective_message.reply_text('Use o botão para compartilhar seu próprio contato. Contatos encaminhados não são aceitos.')
            return
        try:
            await asyncio.to_thread(self.repository.bind_contact,update.effective_user.id,contact.phone_number)
        except FlowError as error:
            await update.effective_message.reply_text(str(error));return
        except Exception:
            await update.effective_message.reply_text('Não consegui validar o vínculo agora. Tente novamente.');return
        await self.run(update,self.flow.enter,'menu')

def install(application, client):
    adapter=TelegramFinance(client)
    commands=['start','menu','cancelar','despesa','receita','entrada','resumo','listar','lancamentos','receber','status','clientes','cadastrar','contas','cartoes','metas','orcamentos','vencimentos','data']
    application.add_handler(CommandHandler(commands,adapter.command))
    application.add_handler(MessageHandler(filters.COMMAND,adapter.command))
    application.add_handler(CallbackQueryHandler(adapter.callback))
    application.add_handler(MessageHandler(filters.CONTACT,adapter.contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,adapter.text))
    return adapter
