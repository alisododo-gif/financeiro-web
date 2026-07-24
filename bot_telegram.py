import json
import logging
import os
import re
from datetime import datetime, time

from dotenv import load_dotenv
import pytz
from supabase import Client, create_client
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Importa a função de alertas enviada pelo módulo lembrete_boletos.py
from lembrete_boletos import processar_e_enviar_alertas

# Carrega variáveis de ambiente
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Inicializa o cliente oficial do Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO)

CACHE_USUARIOS = {}


def buscar_dados_usuario(telegram_id):
    """Busca id do usuário, todas as contas e todos os cartões cadastrados."""
    try:
        telegram_id_int = int(telegram_id)
    except (ValueError, TypeError):
        return None

    if telegram_id_int in CACHE_USUARIOS:
        return CACHE_USUARIOS[telegram_id_int]

    try:
        res_user = (
            supabase.table("usuarios")
            .select("id")
            .eq("telegram_id", telegram_id_int)
            .execute()
        )

        if res_user.data:
            usuario_db_id = res_user.data[0]["id"]

            res_contas = (
                supabase.table("contas")
                .select("id, nome_conta")
                .eq("usuario_id", usuario_db_id)
                .execute()
            )
            lista_contas = res_contas.data if res_contas.data else []

            res_cartoes = (
                supabase.table("cartoes")
                .select("id, nome_cartao")
                .eq("usuario_id", usuario_db_id)
                .execute()
            )
            lista_cartoes = res_cartoes.data if res_cartoes.data else []

            dados = {
                "usuario_id": usuario_db_id,
                "contas": lista_contas,
                "cartoes": lista_cartoes,
            }

            CACHE_USUARIOS[telegram_id_int] = dados
            return dados

    except Exception as e:
        logging.error(f"Erro ao buscar dados do usuário: {e}")

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Primeiro acesso: envia botão para vincular via telefone."""
    telegram_id = update.effective_user.id
    dados_usuario = buscar_dados_usuario(telegram_id)

    if dados_usuario:
        await update.message.reply_text(
            "👋 Você já está cadastrado no **FinanceiroPro**!\n\n"
            "Pode enviar seus lançamentos diretamente (ex: `45.90 Almoço #restaurante`).",
            parse_mode="Markdown",
        )
        return

    botao_telefone = KeyboardButton(
        "📲 Vincular minha conta pelo Telefone", request_contact=True
    )
    teclado = ReplyKeyboardMarkup(
        [[botao_telefone]], resize_keyboard=True, one_time_keyboard=True
    )

    await update.message.reply_text(
        "Olá! Seja bem-vindo ao **FinanceiroPro**. 🚀\n\n"
        "Para começar a registrar seus gastos, clique no botão abaixo para confirmar seu número de telefone.",
        reply_markup=teclado,
        parse_mode="Markdown",
    )


async def receber_contato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa o telefone testando explicitamente com e sem o 9º dígito."""
    contato = update.message.contact
    telefone_telegram = re.sub(r"\D", "", contato.phone_number)
    telegram_id = int(update.effective_user.id)
    nome_telegram = update.effective_user.first_name or "Usuário"

    if len(telefone_telegram) == 13 and telefone_telegram.startswith("55"):
        telefone_sem_9 = telefone_telegram[:4] + telefone_telegram[5:]
    else:
        telefone_sem_9 = telefone_telegram

    try:
        response = (
            supabase.table("usuarios")
            .select("id, telefone")
            .or_(
                f"telefone.eq.{telefone_telegram},telefone.eq.{telefone_sem_9}"
            )
            .execute()
        )

        if response.data:
            usuario = response.data[0]
            usuario_id = usuario["id"]

            supabase.table("usuarios").update(
                {"telegram_id": telegram_id}
            ).eq("id", usuario_id).execute()

            # Limpa cache e pré-carrega os dados do usuário atualizados
            CACHE_USUARIOS.pop(telegram_id, None)
            buscar_dados_usuario(telegram_id)

            await update.message.reply_text(
                f"✅ **Conta vinculada com sucesso!**\n\n"
                f"Bem-vindo(a), **{nome_telegram}**! Sua conta foi vinculada ao Telegram.\n\n"
                f"Já pode enviar seus lançamentos (ex: `30.00 Almoço #restaurante`).",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"❌ **Não foi possível encontrar a conta.**\n\n"
                f"• **Telefones pesquisados:** `{telefone_telegram}` ou `{telefone_sem_9}`",
                parse_mode="Markdown",
            )
    except Exception as e:
        logging.error(f"Erro na vinculação de contato: {e}")
        await update.message.reply_text(
            f"⚠️ Erro no servidor: `{e}`", parse_mode="Markdown"
        )


async def registrar_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = buscar_dados_usuario(telegram_id)

    if not dados_usuario:
        await update.message.reply_text(
            "🚫 **Acesso não autorizado!**\n\n"
            "Sua conta do Telegram ainda não está vinculada.\n"
            "Digite o comando /start para se identificar com o seu número de telefone.",
            parse_mode="Markdown",
        )
        return

    usuario_id = dados_usuario["usuario_id"]
    lista_contas = dados_usuario["contas"]
    lista_cartoes = dados_usuario["cartoes"]

    texto = update.message.text.strip()

    # 1. Extrai hashtags
    tags_encontradas = re.findall(r"#(\w+)", texto)
    tags_final = (
        " ".join([f"#{t.lower()}" for t in tags_encontradas])
        if tags_encontradas
        else None
    )

    # 2. Limpa hashtags
    texto_sem_tags = re.sub(r"#\w+", "", texto).strip()

    # 3. Captura <valor> e <descrição>
    pattern = r"^([\d.,]+)\s+(.+)$"
    match = re.match(pattern, texto_sem_tags)

    if not match:
        await update.message.reply_text(
            "⚠️ **Formato inválido!**\n\n"
            "Exemplos aceitos:\n"
            "`50,00 Comida pix`\n"
            "`50,00 Comida debito`\n"
            "`50,00 Comida credito`",
            parse_mode="Markdown",
        )
        return

    valor_raw, descricao_bruta = match.groups()

    try:
        valor = float(valor_raw.replace(".", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Valor numérico inválido.")
        return

    texto_lower = descricao_bruta.lower()

    # Identificação da Forma de Pagamento
    e_credito = any(kw in texto_lower for kw in ["credito", "crédito", "cartao", "cartão"])
    e_debito = any(kw in texto_lower for kw in ["debito", "débito"])
    forma_pagamento = "Cartão de Crédito" if e_credito else ("Cartão de Débito" if e_debito else "Pix")

    # Limpeza da descrição
    palavras_remover = r"\b(pix|debito|débito|credito|crédito|cartao|cartão)\b"
    descricao_limpa = re.sub(palavras_remover, "", descricao_bruta, flags=re.IGNORECASE).strip()

    now = datetime.now()
    data_atual = now.strftime("%Y-%m-%d")
    mes_fatura_atual = now.strftime("%Y-%m")

    # BASE DOS DADOS PARA CALLBACKS
    dados_base = {
        "u": usuario_id,
        "v": valor,
        "d": descricao_limpa,
        "forma": forma_pagamento,
        "dt": data_atual,
        "mf": mes_fatura_atual,
        "t": tags_final,
    }

    # ==========================================
    # FLUXO 1: CRÉDITO -> USA A TABELA 'CARTOES'
    # ==========================================
    if e_credito:
        if not lista_cartoes:
            await update.message.reply_text("⚠️ **Nenhum cartão de crédito cadastrado!**")
            return

        # Pergunta primeiro: À vista ou Parcelado?
        botoes = [
            [
                InlineKeyboardButton("💵 À Vista", callback_data=json.dumps({**dados_base, "tipo_c": "avista"})),
                InlineKeyboardButton("📅 Parcelado", callback_data=json.dumps({**dados_base, "tipo_c": "parcelado"})),
            ]
        ]
        await update.message.reply_text(
            f"💳 **Pagamento no Crédito**\n\n"
            f"📝 **Descrição:** {descricao_limpa}\n"
            f"💸 **Valor:** R$ {valor:.2f}\n\n"
            f"Como deseja registrar esse pagamento?",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown",
        )
        return

    # ==========================================
    # FLUXO 2: PIX OU DÉBITO -> USA A TABELA 'CONTAS'
    # ==========================================
    else:
        if not lista_contas:
            await update.message.reply_text("⚠️ **Nenhuma conta bancária cadastrada!**")
            return

        # Se tiver MAIS DE 1 CONTA -> Exibe Botões de escolha de Conta
        if len(lista_contas) > 1:
            botoes = []
            for c in lista_contas:
                dados_cb = json.dumps({**dados_base, "cnt": c["id"], "tipo_action": "salvar_conta"})
                botoes.append([InlineKeyboardButton(f"🏦 {c['nome_conta']}", callback_data=dados_cb)])

            await update.message.reply_text(
                f"🏦 **Selecione a conta utilizada:**\n\n"
                f"📝 **Descrição:** {descricao_limpa}\n"
                f"💸 **Valor:** R$ {valor:.2f}\n"
                f"⚡ **Forma:** {forma_pagamento}",
                reply_markup=InlineKeyboardMarkup(botoes),
                parse_mode="Markdown",
            )
        # Se tiver APENAS 1 CONTA -> Salva Direto
        else:
            conta_id = lista_contas[0]["id"]
            payload = {
                "usuario_id": usuario_id,
                "conta_id": conta_id,
                "cartao_id": None,
                "descricao": descricao_limpa,
                "valor": valor,
                "tipo": "Despesa",
                "categoria": "Outros",
                "forma_pagamento": forma_pagamento,
                "data": data_atual,
                "mes_fatura": mes_fatura_atual,
                "pago": True,
                "tags": tags_final,
            }
            try:
                supabase.table("movimentacoes").insert(payload).execute()
                tag_str = f"\n🏷️ **Tags:** `{tags_final}`" if tags_final else ""
                icone = "⚡" if forma_pagamento == "Pix" else "💳"
                await update.message.reply_text(
                    f"✅ **Lançamento Registrado!**\n\n"
                    f"💸 **Valor:** R$ {valor:.2f}\n"
                    f"📝 **Descrição:** {descricao_limpa}\n"
                    f"{icone} **Forma:** {forma_pagamento}\n"
                    f"📅 **Data:** {data_atual}{tag_str}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                await update.message.reply_text(f"⚠️ Erro ao salvar: `{e}`")


async def callback_geral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia as seleções via botões (Contas, Cartões, À Vista / Parcelado)."""
    query = update.callback_query
    await query.answer()

    data = json.loads(query.data)
    action = data.get("tipo_action")
    tipo_credito = data.get("tipo_c")

    dados_usuario = buscar_dados_usuario(query.from_user.id)
    lista_cartoes = dados_usuario["cartoes"] if dados_usuario else []

    # TRATAMENTO DE CRÉDITO: Após escolher À vista / Parcelado, seleciona o CARTÃO
    if tipo_credito:
        if len(lista_cartoes) > 1:
            botoes = []
            for c in lista_cartoes:
                data_proximo = {**data, "crt": c["id"], "tipo_action": "salvar_cartao", "tipo_c": None}
                botoes.append([InlineKeyboardButton(f"💳 {c['nome_cartao']}", callback_data=json.dumps(data_proximo))])

            await query.edit_message_text(
                f"💳 **Selecione qual CARTÃO foi utilizado:**\n\n"
                f"📝 **Descrição:** {data['d']}\n"
                f"💸 **Valor:** R$ {data['v']:.2f}\n"
                f"📌 **Opção:** {'À Vista' if tipo_credito == 'avista' else 'Parcelado'}",
                reply_markup=InlineKeyboardMarkup(botoes),
                parse_mode="Markdown",
            )
            return
        else:
            cartao_id = lista_cartoes[0]["id"] if lista_cartoes else None
            data["crt"] = cartao_id
            action = "salvar_cartao"

    # SALVAMENTO 1: PIX / DÉBITO (USA CONTA_ID)
    if action == "salvar_conta":
        payload = {
            "usuario_id": data["u"],
            "conta_id": data["cnt"],
            "cartao_id": None,
            "descricao": data["d"],
            "valor": data["v"],
            "tipo": "Despesa",
            "categoria": "Outros",
            "forma_pagamento": data["forma"],
            "data": data["dt"],
            "mes_fatura": data["mf"],
            "pago": True,
            "tags": data["t"],
        }
        try:
            supabase.table("movimentacoes").insert(payload).execute()
            tag_str = f"\n🏷️ **Tags:** `{data['t']}`" if data["t"] else ""
            await query.edit_message_text(
                f"✅ **Lançamento Registrado!**\n\n"
                f"💸 **Valor:** R$ {data['v']:.2f}\n"
                f"📝 **Descrição:** {data['d']}\n"
                f"⚡ **Forma:** {data['forma']}\n"
                f"📅 **Data:** {data['dt']}{tag_str}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(f"⚠️ Erro ao salvar no Supabase: `{e}`")

    # SALVAMENTO 2: CRÉDITO (USA CARTAO_ID)
    elif action == "salvar_cartao":
        payload = {
            "usuario_id": data["u"],
            "conta_id": None,
            "cartao_id": data["crt"],
            "descricao": data["d"],
            "valor": data["v"],
            "tipo": "Despesa",
            "categoria": "Outros",
            "forma_pagamento": "Cartão de Crédito",
            "data": data["dt"],
            "mes_fatura": data["mf"],
            "pago": False,
            "tags": data["t"],
        }
        try:
            supabase.table("movimentacoes").insert(payload).execute()
            tag_str = f"\n🏷️ **Tags:** `{data['t']}`" if data["t"] else ""
            await query.edit_message_text(
                f"✅ **Lançamento no Crédito Registrado!**\n\n"
                f"💸 **Valor:** R$ {data['v']:.2f}\n"
                f"📝 **Descrição:** {data['d']}\n"
                f"💳 **Forma:** Cartão de Crédito\n"
                f"📅 **Data:** {data['dt']}{tag_str}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(f"⚠️ Erro ao salvar no Supabase: `{e}`")


def main():
    print("🤖 Bot de Finanças iniciado e escutando mensagens...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    fuso_brasilia = pytz.timezone("America/Sao_Paulo")

    app.job_queue.run_daily(
        processar_e_enviar_alertas,
        time=time(hour=8, minute=0, second=0, tzinfo=fuso_brasilia),
    )
    
    app.job_queue.run_daily(
        processar_e_enviar_alertas,
        time=time(hour=14, minute=0, second=0, tzinfo=fuso_brasilia),
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, receber_contato))
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_gastos)
    )
    app.add_handler(CallbackQueryHandler(callback_geral))

    app.run_polling()


if __name__ == "__main__":
    main()