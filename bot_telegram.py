import json
import logging
import asyncio
import os
import re
import calendar
import html
import httpx
import sys
import uuid
import tempfile
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta

from dotenv import load_dotenv
import pytz
from supabase import Client, create_client, ClientOptions
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
from telegram.error import TelegramError

from groq import AsyncGroq

from lembrete_boletos import processar_e_enviar_alertas, enviar_resumo_mensal_telegram

# Carrega variáveis de ambiente
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")

STREAMLIT_URL = "https://financeiro-web-2-0.streamlit.app/?uid=1"
CACHE_TTL = 600

options = ClientOptions(
    postgrest_client_timeout=30,
    storage_client_timeout=30
)

supabase: Client = None  # Inicializado no main()
groq_client: AsyncGroq = None  # Inicializado no main()

logging.basicConfig(level=logging.INFO)

CACHE_USUARIOS = {}
FUSO_BR = pytz.timezone("America/Sao_Paulo")


# =========================================================
# FUNÇÕES AUXILIARES & SUPABASE
# =========================================================

def sanitizar_valor(valor_raw: str) -> float:
    """Converte e sanitiza strings financeiras aceitando formatos PT-BR e EN."""
    v = str(valor_raw).strip()
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    elif "." in v:
        partes = v.split(".")
        if len(partes[-1]) == 3 and len(partes) > 1:
            v = v.replace(".", "")
    return float(v)


def buscar_dados_usuario(telegram_id, forcar_atualizacao=False):
    try:
        telegram_id_int = int(telegram_id)
    except (ValueError, TypeError):
        return None

    now = datetime.now()
    if not forcar_atualizacao and telegram_id_int in CACHE_USUARIOS:
        cached_data, timestamp = CACHE_USUARIOS[telegram_id_int]
        if (now - timestamp).total_seconds() < CACHE_TTL:
            return cached_data

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
                .select("id, nome")
                .eq("usuario_id", usuario_db_id)
                .execute()
            )
            lista_contas = res_contas.data if res_contas.data else []

            res_cartoes = (
                supabase.table("cartoes")
                .select("id, nome_cartao, dia_fechamento")
                .eq("usuario_id", usuario_db_id)
                .execute()
            )
            lista_cartoes = res_cartoes.data if res_cartoes.data else []

            dados = {
                "usuario_id": usuario_db_id,
                "contas": lista_contas,
                "cartoes": lista_cartoes,
            }

            CACHE_USUARIOS[telegram_id_int] = (dados, now)
            return dados

    except Exception as e:
        logging.error(f"Erro ao buscar dados do usuário: {e}")

    return None


def calcular_mes_fatura(data_compra, dia_fechamento):
    if not dia_fechamento:
        return data_compra.strftime("%m/%Y")

    dia_fechamento = int(dia_fechamento)

    if data_compra.day >= dia_fechamento:
        proximo_mes = data_compra + relativedelta(months=1)
        return proximo_mes.strftime("%m/%Y")
    
    return data_compra.strftime("%m/%Y")


# =========================================================
# MOTOR IA (GROQ + FUNCTION CALLING + AUDIO)
# =========================================================

async def interpretar_com_groq(texto_usuario: str) -> dict:
    """Interpreta texto livre do usuário usando Llama-3.3 da Groq para extrair parâmetros financeiros ou responder dúvidas."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "adicionar_lancamento",
                "description": "Registra uma despesa, receita ou conta a receber informada pelo usuário.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tipo": {
                            "type": "string",
                            "enum": ["Despesa", "Receita", "Receber"],
                            "description": "Tipo do lançamento financeiro."
                        },
                        "valor": {
                            "type": "number",
                            "description": "Valor numérico do lançamento."
                        },
                        "descricao": {
                            "type": "string",
                            "description": "Descrição sucinta do gasto ou receita."
                        },
                        "metodo_pagamento": {
                            "type": "string",
                            "enum": ["Pix", "Crédito", "Débito", "Fixo", "Outros"],
                            "description": "Forma ou categoria padrão de pagamento identificada."
                        },
                        "data": {
                            "type": "string",
                            "description": "Data no formato YYYY-MM-DD se mencionada."
                        }
                    },
                    "required": ["tipo", "valor", "descricao"]
                }
            }
        }
    ]

    hoje = datetime.now(FUSO_BR).strftime("%Y-%m-%d")
    system_prompt = (
        f"Você é o assistente financeiro inteligente do FinanceiroPro. Hoje é {hoje}.\n"
        "Se o usuário informar um gasto, receita ou conta a receber, chame a função 'adicionar_lancamento'.\n"
        "Se o usuário fizer perguntas gerais, conversas, saudações ou dúvidas financeiras, responda em texto normal de forma amigável, clara e prestativa."
    )

    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Modelo ativo, ultra-rápido e sem bloqueios
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": texto_usuario}
            ],
            tools=tools,
            tool_choice="auto"
        )
        

        message = response.choices[0].message

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            return {"type": "action", "function": tool_call.function.name, "args": args}
        elif message.content:
            return {"type": "reply", "text": message.content}
        else:
            return {"type": "reply", "text": "Como posso te ajudar com suas finanças hoje?"}

    except Exception as e:
        logging.error(f"Erro na chamada da Groq: {e}")
        return {"type": "error", "text": f"⚠️ Erro ao consultar IA: {e}"}


# =========================================================
# HANDLERS PRINCIPAIS DO TELEGRAM
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if dados_usuario:
        await update.message.reply_text(
            "👋 Você já está cadastrado no FinanceiroPro!\n\n"
            "• Modo Manual Rápido: `50.00 Mercado Pix` ou `/receita 2500 Salário`\n"
            "• Modo IA / Voz: Envie frases livres como *'Almoço 35 reais'* ou **grave um áudio**!\n"
            "• Para listar e editar: Digite /listar\n"
            "• Para ver o resumo: Digite `resumo` ou /resumo",
            parse_mode="Markdown"
        )
        return

    botao_telefone = KeyboardButton(
        "📲 Vincular minha conta pelo Telefone", request_contact=True
    )
    teclado = ReplyKeyboardMarkup(
        [[botao_telefone]], resize_keyboard=True, one_time_keyboard=True
    )

    await update.message.reply_text(
        "Olá! Seja bem-vindo ao FinanceiroPro. 🚀\n\n"
        "Para começar a registrar seus gastos, clique no botão abaixo para confirmar seu número de telefone.",
        reply_markup=teclado
    )


async def receber_contato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contato = update.message.contact
    telefone_telegram = re.sub(r"\D", "", contato.phone_number)
    telegram_id = int(update.effective_user.id)
    nome_telegram = update.effective_user.first_name or "Usuário"

    if len(telefone_telegram) == 13 and telefone_telegram.startswith("55"):
        telefone_sem_9 = telefone_telegram[:4] + telefone_telegram[5:]
    else:
        telefone_sem_9 = telefone_telegram

    try:
        def _get_user():
            return (
                supabase.table("usuarios")
                .select("id, telefone")
                .or_(f"telefone.eq.{telefone_telegram},telefone.eq.{telefone_sem_9}")
                .execute()
            )

        response = await asyncio.to_thread(_get_user)

        if response.data:
            usuario = response.data[0]
            usuario_id = usuario["id"]

            def _update_user():
                return (
                    supabase.table("usuarios")
                    .update({"telegram_id": telegram_id})
                    .eq("id", usuario_id)
                    .execute()
                )

            await asyncio.to_thread(_update_user)

            CACHE_USUARIOS.pop(telegram_id, None)
            await asyncio.to_thread(buscar_dados_usuario, telegram_id, True)

            await update.message.reply_text(
                f"✅ Conta vinculada com sucesso!\n\n"
                f"Bem-vindo(a), {nome_telegram}! Sua conta foi vinculada ao Telegram.\n\n"
                f"Já pode enviar seus lançamentos ou digitar /status para ver pendências."
            )
        else:
            await update.message.reply_text(
                f"❌ Não foi possível encontrar a conta.\n\n"
                f"• Telefones pesquisados: {telefone_telegram} ou {telefone_sem_9}"
            )
    except Exception as e:
        logging.error(f"Erro na vinculação de contato: {e}")
        await update.message.reply_text(f"⚠️ Erro no servidor: {e}")


async def processar_mensagem_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe mensagens de voz do Telegram, transcreve com Groq Whisper e envia para a IA."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    msg_status = await update.message.reply_text("🎙️ *Ouvindo áudio...*", parse_mode="Markdown")

    try:
        file = await context.bot.get_file(voice.file_id)
        byte_array = await file.download_as_bytearray()
        
        # Envio em memória direto para a API sem depender do ffmpeg do sistema
        transcription = await groq_client.audio.transcriptions.create(
            file=("audio.m4a", bytes(byte_array), "audio/m4a"),
            model="whisper-large-v3",
            response_format="json",
            language="pt"
        )

        texto_transcrito = transcription.text.strip()

        if not texto_transcrito:
            await msg_status.edit_text("⚠️ Não consegui entender o áudio.")
            return

        await msg_status.edit_text(f"🗣️ *Transcrição:* \"_{texto_transcrito}_\"", parse_mode="Markdown")

        update.message.text = texto_transcrito
        await registrar_gastos(update, context)

    except Exception as e:
        logging.error(f"Erro no Whisper da Groq: {e}")
        await msg_status.edit_text(f"❌ Erro ao processar áudio via Groq: `{e}`", parse_mode="Markdown")


async def registrar_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler central: tenta padrão MANUAL (Regex); se falhar, aciona a IA (Groq)."""
    telegram_id = update.effective_user.id

    try:
        await limpar_botoes_anteriores(update, context)
    except Exception as e:
        logging.error(f"Erro ao tentar limpar botões: {e}")

    # 1. Tratamento de resposta para a escolha de dia de vencimento
    if context.user_data.get("aguardando_dia_vencimento"):
        session_id = context.user_data.get("session_ativa")
        texto_dia = update.message.text.strip()
        
        if not texto_dia.isdigit() or not (1 <= int(texto_dia) <= 31):
            if session_id and "lancamentos_temp" in context.user_data:
                context.user_data["lancamentos_temp"].pop(session_id, None)
            context.user_data["aguardando_dia_vencimento"] = False
            await update.message.reply_text("⚠️ Dia inválido! Por favor, informe um dia entre 1 e 31.")
            return

        dia_escolhido = int(texto_dia)
        now = datetime.now(FUSO_BR)
        
        try:
            data_vencimento_dt = datetime(now.year, now.month, dia_escolhido)
        except ValueError:
            ultimo_dia = calendar.monthrange(now.year, now.month)[1]
            data_vencimento_dt = datetime(now.year, now.month, ultimo_dia)

        dados_temp = context.user_data.get("lancamentos_temp", {}).get(session_id)
        if dados_temp:
            dados_temp["data"] = data_vencimento_dt.strftime("%Y-%m-%d")
            dados_temp["mes_fatura"] = data_vencimento_dt.strftime("%m/%Y")
            context.user_data["aguardando_dia_vencimento"] = False
            
            await perguntar_forma_pagamento_recorrente(update, context, session_id)
            return

    # 2. Tratamento de Edição de Lançamento
    if "edit_mov_id" in context.user_data:
        mov_id = context.user_data.pop("edit_mov_id")
        texto_digitado = update.message.text.strip()
        try:
            novo_valor = sanitizar_valor(texto_digitado)

            def _update_valor():
                return supabase.table("movimentacoes").update({"valor": novo_valor}).eq("id", mov_id).execute()

            await asyncio.to_thread(_update_valor)
            await update.message.reply_text(f"✅ *Lançamento atualizado para R$ {novo_valor:.2f}!*", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Valor inválido. A edição foi cancelada. Tente usar `/listar` novamente.")
        return

    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if not dados_usuario:
        await update.message.reply_text(
            "🚫 Acesso não autorizado!\n\n"
            "Sua conta do Telegram ainda não está vinculada.\n"
            "Digite o comando /start para se identificar com o seu número de telefone."
        )
        return

    texto = update.message.text.strip()

    if texto.lower() in ["status", "receber", "pendentes", "contas"]:
        await consultar_contas_receber(update, context)
        return

    # -------------------------------------------------------------
    # TENTATIVA 1: MODO MANUAL VIA REGEX
    # -------------------------------------------------------------
    tags_encontradas = re.findall(r"#(\w+)", texto)
    tags_final = " ".join([f"#{t.lower()}" for t in tags_encontradas]) if tags_encontradas else None
    texto_sem_tags = re.sub(r"#\w+", "", texto).strip()

    match_categoria = re.search(r'@(?:"([^"]+)"|([\wÀ-ÿ]+))', texto_sem_tags)
    if match_categoria:
        categoria_bruta = match_categoria.group(1) or match_categoria.group(2)
        categoria_usuario = categoria_bruta.strip().title()
        texto_sem_tags = re.sub(r'@(?:"[^"]+"|[\wÀ-ÿ]+)', "", texto_sem_tags).strip()
    else:
        categoria_usuario = None

    match_data = re.search(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", texto_sem_tags)
    now = datetime.now(FUSO_BR)

    if match_data:
        data_str = match_data.group(1)
        partes_data = data_str.split("/")
        dia = partes_data[0].zfill(2)
        mes = partes_data[1].zfill(2)
        ano = partes_data[2] if len(partes_data) == 3 else str(now.year)
        if len(ano) == 2: ano = f"20{ano}"
        data_final = f"{ano}-{mes}-{dia}"
        texto_sem_tags = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", "", texto_sem_tags).strip()
    else:
        data_final = now.strftime("%Y-%m-%d")

    pattern = r"^(?:r\$\s*)?([\d.,]+)\s*(?:reais|reias)?\s+(.+)$"
    match = re.match(pattern, texto_sem_tags, re.IGNORECASE)

    # Se casar no padrão manual clássico, executa o fluxo manual
    if match:
        valor_raw, descricao_bruta = match.groups()
        try:
            valor = sanitizar_valor(valor_raw)
            await processar_fluxo_manual(update, context, dados_usuario, valor, descricao_bruta, data_final, categoria_usuario, tags_final)
            return
        except ValueError:
            pass

    # -------------------------------------------------------------
    # TENTATIVA 2: FALLBACK PARA IA (GROQ)
    # -------------------------------------------------------------
    res_ia = await interpretar_com_groq(texto)

    if res_ia["type"] == "reply":
        await update.message.reply_text(res_ia["text"])
        return

    if res_ia["type"] == "action" and res_ia["function"] == "adicionar_lancamento":
        args = res_ia["args"]
        tipo = args.get("tipo", "Despesa")
        valor = float(args.get("valor", 0.0))
        descricao = args.get("descricao", "Lançamento via IA")
        metodo = args.get("metodo_pagamento", "Pix")
        data_ia = args.get("data", data_final)

        # Mapeia para o fluxo interno manual reaproveitando as variáveis
        desc_sintetizada = f"{descricao} {metodo}"
        if tipo == "Receita":
            desc_sintetizada += " receita"
        elif tipo == "Receber":
            desc_sintetizada += " receber"

        await processar_fluxo_manual(update, context, dados_usuario, valor, desc_sintetizada, data_ia, categoria_usuario, tags_final)
        return

    await update.message.reply_text("⚠️ Não consegui entender o formato. Exemplo: `50.00 Mercado Pix` ou fale em áudio.")


async def processar_fluxo_manual(update, context, dados_usuario, valor, descricao_bruta, data_final, categoria_usuario, tags_final):
    """Executa a lógica padrão de inserção do bot no banco de dados."""
    usuario_id = dados_usuario["usuario_id"]
    lista_contas = dados_usuario["contas"]
    lista_cartoes = dados_usuario["cartoes"]

    palavras_chave_receita = ["receita", "prolabore", "entrada"]
    e_receita_direta = any(kw in descricao_bruta.lower() for kw in palavras_chave_receita)

    if e_receita_direta:
        descricao_limpa = re.sub(r"\b(receita|prolabore|entrada)\b", "", descricao_bruta, flags=re.IGNORECASE).strip()
        descricao_limpa = " ".join(descricao_limpa.split()) or "Receita"
        
        mes_fatura_calc = datetime.strptime(data_final, "%Y-%m-%d").strftime("%m/%Y")
        conta_id = lista_contas[0]["id"] if lista_contas else None

        payload_receita = {
            "usuario_id": usuario_id,
            "conta_id": conta_id,
            "cartao_id": None,
            "descricao": descricao_limpa.title(),
            "valor": valor,
            "tipo": "Receita",
            "categoria": categoria_usuario if categoria_usuario else "Receita",
            "forma_pagamento": "Pix" if "pix" in descricao_bruta.lower() else "Outros",
            "data": data_final,
            "mes_fatura": mes_fatura_calc,
            "pago": True,
            "tags": tags_final,
        }

        def _insert_rec_dir():
            return supabase.table("movimentacoes").insert(payload_receita).execute()

        await asyncio.to_thread(_insert_rec_dir)
        tag_str = f"\n🏷️ Tags: {tags_final}" if tags_final else ""
        data_br = datetime.strptime(data_final, "%Y-%m-%d").strftime("%d/%m/%Y")
        
        await update.message.reply_text(
            f"🟢 *Receita Registrada!*\n\n"
            f"📝 Descrição: {descricao_limpa.title()}\n"
            f"💰 Valor: R$ {valor:.2f}\n"
            f"📅 Data: {data_br}\n"
            f"🏷️ Tipo: Entrada / Receita{tag_str}",
            parse_mode="Markdown"
        )
        return

    e_recebimento = any(kw in descricao_bruta.lower() for kw in ["receber", "ganho", "venda"])

    if e_recebimento:
        descricao_limpa = re.sub(r"\b(receber|ganho|venda)\b", "", descricao_bruta, flags=re.IGNORECASE).strip()
        payload_receber = {
            "usuario_id": usuario_id,
            "descricao": descricao_limpa or "Recebimento",
            "valor": valor,
            "data_recebimento": data_final,
            "recebido": False,
        }

        def _insert_receber():
            return supabase.table("contas_receber").insert(payload_receber).execute()

        await asyncio.to_thread(_insert_receber)
        tag_str = f"\n🏷️ Tags: {tags_final}" if tags_final else ""
        await update.message.reply_text(
            f"📥 Conta a Receber Cadastrada!\n\n"
            f"📝 Descrição: {descricao_limpa or 'Recebimento'}\n"
            f"💰 Valor: R$ {valor:.2f}\n"
            f"📅 Data Recebimento: {data_final}\n"
            f"📌 Status: Pendente{tag_str}"
        )
        return

    texto_analise = descricao_bruta.lower()
    e_recorrente = bool(re.search(r"\b(fixo|fixa|recorrente)\b", texto_analise))
    e_credito = bool(re.search(r"\b(credito|crédito)\b", texto_analise))
    e_debito = bool(re.search(r"\b(debito|débito)\b", texto_analise))

    if e_credito:
        forma_pagamento, categoria_padrao = "Cartão de Crédito", "Cartão de Crédito"
    elif e_debito:
        forma_pagamento, categoria_padrao = "Cartão de Débito", "Débito"
    else:
        forma_pagamento, categoria_padrao = "Pix", "Pix"

    categoria_final = categoria_usuario if categoria_usuario else categoria_padrao

    descricao_limpa = re.sub(r"\b(pix|debito|débito|credito|crédito|fixo|fixa|recorrente)\b", "", descricao_bruta, flags=re.IGNORECASE).strip()
    descricao_limpa = " ".join(descricao_limpa.split()) or categoria_padrao

    if e_recorrente and "(Recorrente)" not in descricao_limpa:
        descricao_limpa = f"{descricao_limpa} (Recorrente)"

    mes_fatura_calc = datetime.strptime(data_final, "%Y-%m-%d").strftime("%m/%Y")
    session_id = str(uuid.uuid4())[:8]

    if "lancamentos_temp" not in context.user_data:
        context.user_data["lancamentos_temp"] = {}

    context.user_data["lancamentos_temp"][session_id] = {
        "usuario_id": usuario_id,
        "valor": valor,
        "descricao": descricao_limpa,
        "categoria": categoria_final,
        "forma_pagamento": forma_pagamento,
        "data": data_final,
        "mes_fatura": mes_fatura_calc,
        "tags": tags_final,
        "pago": not e_recorrente,
        "e_recorrente": e_recorrente
    }

    if e_recorrente:
        context.user_data["session_ativa"] = session_id
        botoes = [[
            InlineKeyboardButton("📅 Vence Hoje", callback_data=f"venc_hoje_{session_id}"),
            InlineKeyboardButton("✏️ Escolher Dia", callback_data=f"venc_mudar_{session_id}"),
        ]]
        await update.message.reply_text(
            f"🔄 *Lançamento Fixo / Recorrente*\n\n"
            f"📝 *Descrição:* {descricao_limpa}\n"
            f"💰 *Valor:* R$ {valor:.2f}\n\nQual é o dia de vencimento dessa conta?",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown"
        )
        return

    if e_credito:
        if not lista_cartoes:
            await update.message.reply_text("⚠️ Nenhum cartão de crédito cadastrado no seu banco!")
            return

        botoes = [[
            InlineKeyboardButton("💵 À Vista", callback_data=f"c_avista_{session_id}"),
            InlineKeyboardButton("📅 Parcelado (2x a 12x)", callback_data=f"c_parcelado_menu_{session_id}"),
        ]]

        await update.message.reply_text(
            f"💳 Pagamento no Crédito\n\n📝 Descrição: {descricao_limpa}\n🏷️ Categoria: {categoria_final}\n💸 Valor: R$ {valor:.2f}\n\nComo deseja registrar esse pagamento?",
            reply_markup=InlineKeyboardMarkup(botoes)
        )
    else:
        if not lista_contas:
            await update.message.reply_text("⚠️ Nenhuma conta bancária cadastrada no seu banco!")
            return

        if len(lista_contas) > 1:
            botoes = [[InlineKeyboardButton(f"🏦 {c['nome']}", callback_data=f"cnt_{c['id']}_{session_id}")] for c in lista_contas]
            await update.message.reply_text(
                f"🏦 Selecione a conta utilizada:\n\n📝 Descrição: {descricao_limpa}\n🏷️ Categoria: {categoria_final}\n💸 Valor: R$ {valor:.2f}\n⚡ Forma: {forma_pagamento}",
                reply_markup=InlineKeyboardMarkup(botoes)
            )
        else:
            conta_id = lista_contas[0]["id"]
            payload = {
                "usuario_id": usuario_id,
                "conta_id": conta_id,
                "cartao_id": None,
                "descricao": descricao_limpa,
                "valor": valor,
                "tipo": "Despesa",
                "categoria": categoria_final,
                "forma_pagamento": forma_pagamento,
                "data": data_final,
                "mes_fatura": mes_fatura_calc,
                "pago": True,
                "tags": tags_final,
            }
            def _insert_mov():
                return supabase.table("movimentacoes").insert(payload).execute()

            await asyncio.to_thread(_insert_mov)
            tag_str = f"\n🏷️ Tags: {tags_final}" if tags_final else ""
            icone = "⚡" if forma_pagamento == "Pix" else "💳"
            await update.message.reply_text(
                f"✅ Lançamento Registrado!\n\n💸 Valor: R$ {valor:.2f}\n📝 Descrição: {descricao_limpa}\n🏷️ Categoria: {categoria_final}\n{icone} Forma: {forma_pagamento}\n📅 Data: {data_final}\n📌 Status: Pago{tag_str}"
            )
            context.user_data["lancamentos_temp"].pop(session_id, None)


# =========================================================
# DEMAIS COMANDOS (RECEITA, LISTAR, STATUS, RESUMO)
# =========================================================

async def lancar_receita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)
    await limpar_botoes_anteriores(update, context)

    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular.")
        return

    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("⚠️ Formato incorreto! Use: `/receita 2800 Pagamento de Salário`", parse_mode="Markdown")
        return

    partes = texto.split(" ", 1)
    valor = sanitizar_valor(partes[0])
    descricao = partes[1] if len(partes) > 1 else "Receita"
    agora_br = datetime.now(FUSO_BR)

    payload_receita = {
        "usuario_id": dados_usuario["usuario_id"],
        "conta_id": dados_usuario.get("contas", [{}])[0].get("id"),
        "tipo": "Receita",
        "descricao": descricao,
        "valor": valor,
        "categoria": "Receita",
        "data": agora_br.strftime("%Y-%m-%d"),
        "mes_fatura": agora_br.strftime("%m/%Y"),
        "pago": True,
        "forma_pagamento": "Outros"
    }

    def _insert_receita():
        return supabase.table("movimentacoes").insert(payload_receita).execute()

    await asyncio.to_thread(_insert_receita)
    await update.message.reply_text(f"🟢 *Receita Cadastrada!*\n\n📝 Descrição: {descricao}\n💰 Valor: R$ {valor:.2f}", parse_mode="Markdown")


async def listar_lancamentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)
    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular.")
        return

    await limpar_botoes_anteriores(update, context)
    data_hoje = datetime.now(FUSO_BR).strftime("%Y-%m-%d")

    def _get_movs():
        return supabase.table("movimentacoes").select("*").eq("usuario_id", dados_usuario["usuario_id"]).eq("data", data_hoje).order("id", desc=True).execute()

    res_movs = await asyncio.to_thread(_get_movs)
    movs = res_movs.data or []

    if not movs:
        await update.message.reply_text("📂 Nenhum lançamento cadastrado no dia de hoje.")
        return

    await update.message.reply_text("📋 <b>Lançamentos de HOJE:</b>", parse_mode="HTML")
    mensagens_com_botoes = context.user_data.get("mensagens_botoes_antigas", [])

    for m in reversed(movs):
        emoji_tipo = "🟢" if m.get("tipo") == "Receita" else "🔴"
        texto_item = f"{emoji_tipo} <b>{html.escape(m.get('descricao', 'S/D'))}</b>\n💰 Valor: R$ {m.get('valor', 0.0):.2f}"
        teclado = [[InlineKeyboardButton("✏️ Editar", callback_data=f"edit_{m['id']}"), InlineKeyboardButton("🗑️ Excluir", callback_data=f"del_{m['id']}")]]
        msg = await update.message.reply_text(text=texto_item, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")
        mensagens_com_botoes.append(msg.message_id)

    context.user_data["mensagens_botoes_antigas"] = mensagens_com_botoes


async def tratar_botoes_lancamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acao, mov_id = query.data.split("_")

    if acao == "del":
        def _delete_mov():
            return supabase.table("movimentacoes").delete().eq("id", mov_id).execute()
        await asyncio.to_thread(_delete_mov)
        await query.edit_message_text(text="🗑️ *Lançamento excluído com sucesso!*", parse_mode="Markdown")

    elif acao == "edit":
        context.user_data["edit_mov_id"] = mov_id
        await query.edit_message_text(text="✏️ *Digite o novo valor para este lançamento:*", parse_mode="Markdown")


async def cancelar_edicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_mov_id" in context.user_data:
        context.user_data.pop("edit_mov_id", None)
        await update.message.reply_text("❌ Edição cancelada.")
    else:
        await update.message.reply_text("Nenhuma ação para cancelar.")


async def consultar_contas_receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)
    await limpar_botoes_anteriores(update, context)

    if not dados_usuario:
        return

    def _get_contas_receber():
        return supabase.table("contas_receber").select("*").eq("usuario_id", dados_usuario["usuario_id"]).eq("recebido", False).execute()

    res = await asyncio.to_thread(_get_contas_receber)
    pendentes = res.data or []

    if not pendentes:
        await update.message.reply_text("🎉 Você não possui nenhuma conta a receber pendente!")
        return

    total_pendente = sum(item["valor"] for item in pendentes)
    await update.message.reply_text(f"📥 Contas a Receber Pendentes\n💰 Total: **R$ {total_pendente:.2f}**\n───────────────", parse_mode="Markdown")

    mensagens_com_botoes = context.user_data.get("mensagens_botoes_antigas", [])
    for item in pendentes:
        botoes = [[InlineKeyboardButton("✅ Marcar como Pago", callback_data=f"pagar_rec_{item['id']}")]]
        msg = await update.message.reply_text(f"📝 {item['descricao']}\n💵 Valor: R$ {item['valor']:.2f}", reply_markup=InlineKeyboardMarkup(botoes))
        mensagens_com_botoes.append(msg.message_id)

    context.user_data["mensagens_botoes_antigas"] = mensagens_com_botoes


async def perguntar_forma_pagamento_recorrente(update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str):
    botoes = [[
        InlineKeyboardButton("💵 À Vista", callback_data=f"c_avista_{session_id}"),
        InlineKeyboardButton("📅 Parcelado (2x a 12x)", callback_data=f"c_parcelado_menu_{session_id}"),
    ]]
    texto_msg = "💳 *Como deseja registrar esse gasto fixo?*"
    if update.callback_query:
        await update.callback_query.edit_message_text(texto_msg, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
    else:
        await update.message.reply_text(texto_msg, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")


async def processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id):
    num_parcelas = dados_temp.get("parcelas", 1)
    valor_total = dados_temp["valor"]
    valor_parcela = round(valor_total / num_parcelas, 2)
    cartao_info = next((c for c in lista_cartoes if c["id"] == cartao_id), None)
    dia_fechamento = cartao_info.get("dia_fechamento") if cartao_info else None
    data_compra = datetime.strptime(dados_temp["data"], "%Y-%m-%d")

    fatura_inicial_dt = datetime.strptime(calcular_mes_fatura(data_compra, dia_fechamento), "%m/%Y")

    payloads = []
    for i in range(num_parcelas):
        fatura_parcela_dt = fatura_inicial_dt + relativedelta(months=i)
        data_parcela_dt = data_compra + relativedelta(months=i)
        desc_final = f"{dados_temp['descricao']} ({i+1}/{num_parcelas})" if num_parcelas > 1 else dados_temp['descricao']

        payloads.append({
            "usuario_id": dados_temp["usuario_id"],
            "conta_id": None,
            "cartao_id": cartao_id,
            "descricao": desc_final,
            "valor": valor_parcela,
            "tipo": "Despesa",
            "categoria": dados_temp.get("categoria", "Outros"),
            "forma_pagamento": "Cartão de Crédito",
            "data": data_parcela_dt.strftime("%Y-%m-%d"),
            "mes_fatura": fatura_parcela_dt.strftime("%m/%Y"),
            "pago": False,
            "tags": dados_temp.get("tags"),
        })

    def _insert_cartao():
        return supabase.table("movimentacoes").insert(payloads).execute()

    await asyncio.to_thread(_insert_cartao)
    await query.edit_message_text(f"✅ Lançamento no Crédito Registrado!\n💸 Valor Total: R$ {valor_total:.2f}\n📝 Descrição: {dados_temp['descricao']}")
    context.user_data.get("lancamentos_temp", {}).pop(session_id, None)


async def callback_geral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action.startswith("venc_hoje_"):
        await perguntar_forma_pagamento_recorrente(update, context, action.replace("venc_hoje_", ""))
        return

    if action.startswith("venc_mudar_"):
        session_id = action.replace("venc_mudar_", "")
        context.user_data["session_ativa"] = session_id
        context.user_data["aguardando_dia_vencimento"] = True
        await query.edit_message_text("✍️ *Digite o dia de vencimento dessa conta (1-31):*", parse_mode="Markdown")
        return

    if action.startswith("pagar_rec_"):
        receber_id = int(action.replace("pagar_rec_", ""))
        def _update_rec():
            return supabase.table("contas_receber").update({"recebido": True}).eq("id", receber_id).execute()
        await asyncio.to_thread(_update_rec)
        await query.edit_message_text(f"{query.message.text}\n\n✅ **STATUS ATUALIZADO: PAGO!**", parse_mode="Markdown")
        return

    partes = action.split("_")
    session_id = partes[-1]
    dados_temp = context.user_data.get("lancamentos_temp", {}).get(session_id)

    if not dados_temp:
        await query.edit_message_text("⚠️ Sessão expirada.")
        return

    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, query.from_user.id)
    lista_cartoes = dados_usuario["cartoes"] if dados_usuario else []

    if action.startswith("c_parcelado_menu_"):
        botoes = []
        val_base = dados_temp["valor"]
        for i in range(2, 13, 2):
            row = [InlineKeyboardButton(f"{i}x (R$ {(val_base/i):.2f})", callback_data=f"parc_{i}_{session_id}")]
            if (i + 1) <= 12:
                row.append(InlineKeyboardButton(f"{i+1}x (R$ {(val_base/(i+1)):.2f})", callback_data=f"parc_{i+1}_{session_id}"))
            botoes.append(row)
        await query.edit_message_text("📅 Selecione a quantidade de parcelas:", reply_markup=InlineKeyboardMarkup(botoes))
        return

    if action.startswith("parc_"):
        dados_temp["parcelas"] = int(partes[1])
        cartao_id = lista_cartoes[0]["id"] if lista_cartoes else None
        await processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id)
        return

    if action.startswith("c_avista_"):
        cartao_id = lista_cartoes[0]["id"] if lista_cartoes else None
        await processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id)
        return

    if action.startswith("cnt_"):
        conta_id = int(partes[1])
        payload = {
            "usuario_id": dados_temp["usuario_id"],
            "conta_id": conta_id,
            "cartao_id": None,
            "descricao": dados_temp["descricao"],
            "valor": dados_temp["valor"],
            "tipo": "Despesa",
            "categoria": dados_temp.get("categoria", "Outros"),
            "forma_pagamento": dados_temp.get("forma_pagamento", "Pix/Débito"),
            "data": dados_temp["data"],
            "mes_fatura": datetime.strptime(dados_temp["data"], "%Y-%m-%d").strftime("%m/%Y"),
            "pago": True,
            "tags": dados_temp.get("tags"),
        }
        def _insert_cnt():
            return supabase.table("movimentacoes").insert(payload).execute()
        await asyncio.to_thread(_insert_cnt)
        await query.edit_message_text(f"✅ Lançamento Registrado!\n💸 Valor: R$ {dados_temp['valor']:.2f}\n📝 Descrição: {dados_temp['descricao']}")
        context.user_data.get("lancamentos_temp", {}).pop(session_id, None)


async def testar_alertas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Verificando e enviando alertas de boletos do dia...")
    await processar_e_enviar_alertas(context)
    await limpar_botoes_anteriores(update, context)


async def ping_streamlit(context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient() as client:
            await client.get(STREAMLIT_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    except Exception as e:
        logging.error(f"⚠️ Erro no ping Streamlit: {e}")


async def limpar_botoes_anteriores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    mensagens_antigas = context.user_data.get("mensagens_botoes_antigas", [])
    if not mensagens_antigas:
        return

    context.user_data["mensagens_botoes_antigas"] = []
    for msg_id in mensagens_antigas:
        try:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
        except TelegramError:
            pass


async def handler_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await limpar_botoes_anteriores(update, context)
    await enviar_resumo_mensal_telegram(update, context)        


async def job_resumo_mensal(context: ContextTypes.DEFAULT_TYPE):
    await enviar_resumo_mensal_telegram(None, context)


# =========================================================
# MAIN / EXECUÇÃO DO BOT
# =========================================================

def main():
    global supabase, groq_client

    if not TELEGRAM_TOKEN or not SUPABASE_URL or not SUPABASE_KEY or not GROQ_API_KEY:
        logging.critical("❌ Erro: Verifique as variáveis no arquivo .env (TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY, GROQ_API_KEY)!")
        sys.exit(1)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY, options=options)
    groq_client = AsyncGroq(api_key=GROQ_API_KEY)

    print("🤖 Bot de Finanças Híbrido (Manual + IA) iniciado...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    fuso_br = pytz.timezone("America/Sao_Paulo")

    # Agendamentos automatizados
    app.job_queue.run_daily(processar_e_enviar_alertas, time=time(hour=9, minute=0, tzinfo=fuso_br))
    app.job_queue.run_daily(processar_e_enviar_alertas, time=time(hour=15, minute=0, tzinfo=fuso_br))
    app.job_queue.run_repeating(ping_streamlit, interval=18000, first=18000)
    app.job_queue.run_monthly(job_resumo_mensal, when=time(hour=8, minute=0, tzinfo=fuso_br), day=1)

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", consultar_contas_receber))
    app.add_handler(CommandHandler("receber", consultar_contas_receber))
    app.add_handler(CommandHandler("cancelar", cancelar_edicao))
    app.add_handler(CommandHandler(["listar", "lancamentos"], listar_lancamentos))
    app.add_handler(CommandHandler("receita", lancar_receita))
    app.add_handler(CommandHandler("entrada", lancar_receita))
    app.add_handler(CommandHandler("testar_alertas", testar_alertas_cmd))
    app.add_handler(CommandHandler("resumo", handler_resumo))

    app.add_handler(CallbackQueryHandler(tratar_botoes_lancamento, pattern="^(del_|edit_)"))
    app.add_handler(MessageHandler(filters.Regex(re.compile(r"^resumo$", re.IGNORECASE)), handler_resumo))
    app.add_handler(MessageHandler(filters.CONTACT, receber_contato))
    
    # Handler de Áudio (Transcreve via Whisper Groq)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, processar_mensagem_audio))
    
    # Handler de Texto Livre (Manual + IA Fallback)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_gastos))
    
    app.add_handler(CallbackQueryHandler(callback_geral))

    app.run_polling()


if __name__ == "__main__":
    main()