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
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    Application
)

from telegram.error import TelegramError
from lembrete_boletos import processar_e_enviar_alertas, enviar_resumo_mensal_telegram

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

STREAMLIT_URL = "https://financeiro-web-2-0.streamlit.app/?uid=1"

# Cache TTL em segundos (ex: 600 segundos = 10 minutos)
CACHE_TTL = 600

options = ClientOptions(
    postgrest_client_timeout=30,
    storage_client_timeout=30
)

supabase: Client = None  # Inicializado no main()
logging.basicConfig(level=logging.INFO)

CACHE_USUARIOS = {}
FUSO_BR = pytz.timezone("America/Sao_Paulo")


def sanitizar_valor(valor_raw: str) -> float:
    """Converte e sanitiza strings financeiras aceitando formatos PT-BR e EN de forma consistente."""
    v = valor_raw.strip()
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await limpar_botoes_anteriores(update, context)
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if dados_usuario:
        await update.message.reply_text(
            "👋 Você já está cadastrado no FinanceiroPro!\n\n"
            "• Para lançar despesa Pix: `50.00 Mercado Pix`\n\n"
            "• Para lançar despesa Débito: `50.00 Mercado Débito`\n\n"
            "• Para lançar despesa Fixo: `50.00 Mercado Fixo`\n\n"
            "• Para lançar receita: `10 salario receita` ou `/receita 2500 Salário`\n\n"
            "• Para lançar receber: `50.00 João receber`\n\n"
            "• Consultar Pendentes a Receber: Digite `receber ou pendentes`\n\n"
            "• Para listar e editar: Digite /listar\n\n"
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
    await limpar_botoes_anteriores(update, context)
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


async def lancar_receita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    await limpar_botoes_anteriores(update, context)

    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular.")
        return

    usuario_id = dados_usuario["usuario_id"]
    texto = " ".join(context.args).strip()

    if not texto:
        await update.message.reply_text(
            "⚠️ *Formato incorreto!*\n\n"
            "Use o comando assim:\n"
            "`/receita [VALOR] [DESCRIÇÃO]`\n\n"
            "*Exemplos:*\n"
            "• `/receita 2800 Pagamento de Salário`\n"
            "• `/receita 1000.00 Pix Recebido`",
            parse_mode="Markdown"
        )
        return

    try:
        partes = texto.split(" ", 1)
        valor_raw = partes[0]
        descricao = partes[1] if len(partes) > 1 else "Receita"

        try:
            valor = sanitizar_valor(valor_raw)
            if valor <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Valor inválido! Exemplo correto: `/receita 1500 Salário`", 
                parse_mode="Markdown"
            )
            return

        agora_br = datetime.now(FUSO_BR)
        data_hoje = agora_br.strftime("%Y-%m-%d")
        mes_fatura = agora_br.strftime("%m/%Y")

        lista_contas = dados_usuario.get("contas", [])
        conta_id = lista_contas[0]["id"] if lista_contas else None

        payload_receita = {
            "usuario_id": usuario_id,
            "conta_id": conta_id,
            "tipo": "Receita",
            "descricao": descricao,
            "valor": valor,
            "categoria": "Receita",
            "data": data_hoje,
            "mes_fatura": mes_fatura,
            "pago": True,
            "forma_pagamento": "Outros"
        }

        def _insert_receita():
            return supabase.table("movimentacoes").insert(payload_receita).execute()

        res_insert = await asyncio.to_thread(_insert_receita)

        if res_insert.data:
            data_br = agora_br.strftime("%d/%m/%Y")
            await update.message.reply_text(
                f"🟢 *Receita Cadastrada com Sucesso!*\n\n"
                f"📝 *Descrição:* {descricao}\n"
                f"💰 *Valor:* R$ {valor:.2f}\n"
                f"📅 *Data:* {data_br}\n"
                f"🏷️ *Tipo:* Entrada",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Erro ao salvar receita no banco de dados.")

    except Exception as e:
        logging.error(f"Erro ao lançar receita: {e}")
        await update.message.reply_text(f"⚠️ Erro ao processar o lançamento: {e}")


async def listar_lancamentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular.")
        return

    usuario_id = dados_usuario["usuario_id"]
    await limpar_botoes_anteriores(update, context)

    try:
        data_hoje = datetime.now(FUSO_BR).strftime("%Y-%m-%d")

        def _get_movs():
            return (
                supabase.table("movimentacoes")
                .select("*")
                .eq("usuario_id", usuario_id)
                .eq("data", data_hoje)
                .order("id", desc=True)
                .execute()
            )

        res_movs = await asyncio.to_thread(_get_movs)
        movs = res_movs.data or []

        if not movs:
            await update.message.reply_text("📂 Nenhum lançamento cadastrado no dia de hoje.")
            return

        movs.reverse()
        await update.message.reply_text("📋 <b>Lançamentos cadastrados HOJE:</b>", parse_mode="HTML")

        mensagens_com_botoes = context.user_data.get("mensagens_botoes_antigas", [])

        for m in movs:
            mov_id = m["id"]
            desc = html.escape(m.get("descricao", "Sem descrição"))
            valor = m.get("valor", 0.0)
            tipo = m.get("tipo", "Despesa")
            
            data_raw = m.get("data")
            data_br = datetime.strptime(data_raw, "%Y-%m-%d").strftime("%d/%m/%Y") if data_raw else "N/I"

            emoji_tipo = "🟢" if tipo == "Receita" else "🔴"
            texto_item = (
                f"{emoji_tipo} <b>{desc}</b>\n"
                f"💰 Valor: R$ {valor:.2f}\n"
                f"📅 Data: <code>{data_br}</code>"
            )

            teclado = [
                [
                    InlineKeyboardButton("✏️ Editar", callback_data=f"edit_{mov_id}"),
                    InlineKeyboardButton("🗑️ Excluir", callback_data=f"del_{mov_id}")
                ]
            ]

            msg = await update.message.reply_text(
                text=texto_item,
                reply_markup=InlineKeyboardMarkup(teclado),
                parse_mode="HTML"
            )
            mensagens_com_botoes.append(msg.message_id)

        context.user_data["mensagens_botoes_antigas"] = mensagens_com_botoes

    except Exception as e:
        logging.error(f"Erro ao listar lançamentos: {e}")
        await update.message.reply_text("❌ Erro ao buscar os lançamentos no banco.")


async def tratar_botoes_lancamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dados = query.data
    acao, mov_id = dados.split("_")

    if acao == "del":
        try:
            def _delete_mov():
                return supabase.table("movimentacoes").delete().eq("id", mov_id).execute()

            await asyncio.to_thread(_delete_mov)
            await query.edit_message_text(text="🗑️ *Lançamento excluído com sucesso!*", parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Erro ao excluir lançamento {mov_id}: {e}")
            await query.edit_message_text(text="❌ Erro ao tentar excluir o lançamento.")

    elif acao == "edit":
        context.user_data["edit_mov_id"] = mov_id
        await query.edit_message_text(
            text="✏️ *Modo de Edição*\n\nDigite o novo valor para este lançamento (ex: `45.50`):\n_(Ou envie /cancelar para desistir)_",
            parse_mode="Markdown"
        )


async def cancelar_edicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await limpar_botoes_anteriores(update, context)
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
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular.")
        return

    usuario_id = dados_usuario["usuario_id"]

    try:
        def _get_contas_receber():
            return (
                supabase.table("contas_receber")
                .select("*")
                .eq("usuario_id", usuario_id)
                .eq("recebido", False)
                .order("data_recebimento", desc=False)
                .execute()
            )

        res = await asyncio.to_thread(_get_contas_receber)
        pendentes = res.data if res.data else []

        if not pendentes:
            await update.message.reply_text("🎉 Você não possui nenhuma conta a receber pendente!")
            return

        total_pendente = sum(item["valor"] for item in pendentes)

        await update.message.reply_text(
            f"📥 Contas a Receber Pendentes\n"
            f"💰 Total a receber: **R$ {total_pendente:.2f}**\n"
            f"───────────────",
            parse_mode="Markdown"
        )

        mensagens_com_botoes = context.user_data.get("mensagens_botoes_antigas", [])

        for item in pendentes:
            data_formatada = datetime.strptime(item["data_recebimento"], "%Y-%m-%d").strftime("%d/%m/%Y")
            botoes = [[InlineKeyboardButton("✅ Marcar como Pago", callback_data=f"pagar_rec_{item['id']}")]]
            
            msg = await update.message.reply_text(
                f"📝 {item['descricao']}\n"
                f"💵 Valor: R$ {item['valor']:.2f}\n"
                f"📅 Previsão: {data_formatada}",
                reply_markup=InlineKeyboardMarkup(botoes)
            )
            mensagens_com_botoes.append(msg.message_id)

        context.user_data["mensagens_botoes_antigas"] = mensagens_com_botoes

    except Exception as e:
        logging.error(f"Erro ao consultar contas a receber: {e}")
        await update.message.reply_text(f"⚠️ Erro ao consultar banco de dados: {e}")


async def registrar_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id

    try:
        await limpar_botoes_anteriores(update, context)
    except Exception as e:
        logging.error(f"Erro ao tentar limpar botões: {e}")

    # Tratamento de resposta para a escolha de dia de vencimento
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

    # Tratamento de Edição
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

    usuario_id = dados_usuario["usuario_id"]
    lista_contas = dados_usuario["contas"]
    lista_cartoes = dados_usuario["cartoes"]

    texto = update.message.text.strip()

    if texto.lower() in ["status", "receber", "pendentes", "contas"]:
        await consultar_contas_receber(update, context)
        return

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

        if len(partes_data) == 3:
            ano = partes_data[2]
            if len(ano) == 2:
                ano = f"20{ano}"
        else:
            ano = str(now.year)

        data_final = f"{ano}-{mes}-{dia}"
        texto_sem_tags = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", "", texto_sem_tags).strip()
    else:
        data_final = now.strftime("%Y-%m-%d")

    pattern = r"^(?:r\$\s*)?([\d.,]+)\s*(?:reais|reias)?\s+(.+)$"
    match = re.match(pattern, texto_sem_tags, re.IGNORECASE)

    if not match:
        await update.message.reply_text(
            "⚠️ Formatos Aceitos!\n\n"
            "Exemplos aceitos:\n\n"
            "• `10 salario receita` (Lança uma Receita)\n\n"
            "• `120 Internet fixo` (Despesa Recorrente)\n\n"
            "• `50 Comida Crédito` (Despesa via Crédito)\n\n"
            "• `50 Comida Débito` (Despesa via Débito)\n\n"
            "• `290 Alison receber 15/08` (Cria Conta a Receber)\n\n"
            "• `50 Comida Pix` (Despesa via Pix)\n\n"
            "• Consultar Pendentes a Receber: Digite: `receber ou pendentes`\n\n"
            "• `/clientes` (Visualizar, Editar ou Excluir Lançamentos de Clientes)\n\n"
            "• `/cadastrar` (Cadastrar Clientes)\n\n"
            "• `/listar` (Visualizar, Editar ou Excluir Lançamentos)\n\n"
            "• `resumo` (Exibe o Resumo Geral)",
            parse_mode="Markdown"
        )
        return

    valor_raw, descricao_bruta = match.groups()

    try:
        valor = sanitizar_valor(valor_raw)
    except ValueError:
        await update.message.reply_text("❌ Valor numérico inválido.")
        return

    palavras_chave_receita = ["receita", "prolabore", "entrada"]
    e_receita_direta = any(kw in descricao_bruta.lower() for kw in palavras_chave_receita)

    if e_receita_direta:
        palavras_remover = r"\b(receita|prolabore|entrada)\b"
        descricao_limpa = re.sub(palavras_remover, "", descricao_bruta, flags=re.IGNORECASE).strip()
        descricao_limpa = re.sub(r"^[\s,.-]+|[\s,.-]+$", "", descricao_limpa)
        descricao_limpa = " ".join(descricao_limpa.split())
        nome_descricao = descricao_limpa if descricao_limpa else "Receita"
        
        mes_fatura_calc = datetime.strptime(data_final, "%Y-%m-%d").strftime("%m/%Y")
        conta_id = lista_contas[0]["id"] if lista_contas else None

        payload_receita = {
            "usuario_id": usuario_id,
            "conta_id": conta_id,
            "cartao_id": None,
            "descricao": nome_descricao.title(),
            "valor": valor,
            "tipo": "Receita",
            "categoria": categoria_usuario if categoria_usuario else "Receita",
            "forma_pagamento": "Pix" if "pix" in descricao_bruta.lower() else "Outros",
            "data": data_final,
            "mes_fatura": mes_fatura_calc,
            "pago": True,
            "tags": tags_final,
        }

        try:
            def _insert_rec_dir():
                return supabase.table("movimentacoes").insert(payload_receita).execute()

            await asyncio.to_thread(_insert_rec_dir)
            tag_str = f"\n🏷️ Tags: {tags_final}" if tags_final else ""
            data_br = datetime.strptime(data_final, "%Y-%m-%d").strftime("%d/%m/%Y")
            
            await update.message.reply_text(
                f"🟢 *Receita Registrada!*\n\n"
                f"📝 Descrição: {nome_descricao.title()}\n"
                f"💰 Valor: R$ {valor:.2f}\n"
                f"📅 Data: {data_br}\n"
                f"🏷️ Tipo: Entrada / Receita{tag_str}",
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            logging.error(f"Erro ao salvar receita direta: {e}")
            await update.message.reply_text(f"⚠️ Erro ao salvar receita no Supabase: {e}")
            return

    e_recebimento = any(kw in descricao_bruta.lower() for kw in ["receber", "ganho", "venda"])

    if e_recebimento:
        palavras_remover = r"\b(receber|ganho|venda)\b"
        descricao_limpa = re.sub(palavras_remover, "", descricao_bruta, flags=re.IGNORECASE).strip()
        descricao_limpa = re.sub(r"^[\s,.-]+|[\s,.-]+$", "", descricao_limpa)

        payload_receber = {
            "usuario_id": usuario_id,
            "descricao": descricao_limpa or "Recebimento",
            "valor": valor,
            "data_recebimento": data_final,
            "recebido": False,
        }

        try:
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
        except Exception as e:
            logging.error(f"Erro ao salvar em contas_receber: {e}")
            await update.message.reply_text(f"⚠️ Erro ao salvar no Supabase: {e}")
            return

    texto_analise = descricao_bruta.lower()
    e_recorrente = bool(re.search(r"\b(fixo|fixa|recorrente)\b", texto_analise))

    e_credito = bool(re.search(r"\b(credito|crédito)\b", texto_analise))
    e_debito = bool(re.search(r"\b(debito|débito)\b", texto_analise))

    if e_credito:
        forma_pagamento = "Cartão de Crédito"
        categoria_padrao = "Cartão de Crédito"
    elif e_debito:
        forma_pagamento = "Cartão de Débito"
        categoria_padrao = "Débito"
    else:
        forma_pagamento = "Pix"
        categoria_padrao = "Pix"

    categoria_final = categoria_usuario if categoria_usuario else categoria_padrao

    descricao_limpa = re.sub(
        r"\b(pix|debito|débito|credito|crédito|fixo|fixa|recorrente)\b",
        "",
        descricao_bruta,
        count=1,
        flags=re.IGNORECASE
    ).strip()

    descricao_limpa = re.sub(r"^[\s,.-]+|[\s,.-]+$", "", descricao_limpa)
    descricao_limpa = " ".join(descricao_limpa.split())

    if not descricao_limpa:
        if e_credito:
            descricao_limpa = "Cartão de Crédito"
        elif e_debito:
            descricao_limpa = "Cartão de Débito"
        elif e_recorrente:
            descricao_limpa = "Gasto Fixo"
        else:
            descricao_limpa = "Pix"

    if e_recorrente and "(Recorrente)" not in descricao_limpa:
        descricao_limpa = f"{descricao_limpa} (Recorrente)"

    mes_fatura_calc = datetime.strptime(data_final, "%Y-%m-%d").strftime("%m/%Y")

    # Utiliza um ID único para cada sessão de lançamento evitado sobrescritas concorrentes
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
        botoes = [
            [
                InlineKeyboardButton("📅 Vence Hoje", callback_data=f"venc_hoje_{session_id}"),
                InlineKeyboardButton("✏️ Escolher Dia", callback_data=f"venc_mudar_{session_id}"),
            ]
        ]
        await update.message.reply_text(
            f"🔄 *Lançamento Fixo / Recorrente*\n\n"
            f"📝 *Descrição:* {descricao_limpa}\n"
            f"💰 *Valor:* R$ {valor:.2f}\n\n"
            f"Qual é o dia de vencimento dessa conta?",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown"
        )
        return

    if e_credito:
        if not lista_cartoes:
            await update.message.reply_text("⚠️ Nenhum cartão de crédito cadastrado no seu banco!")
            return

        botoes = [
            [
                InlineKeyboardButton("💵 À Vista", callback_data=f"c_avista_{session_id}"),
                InlineKeyboardButton("📅 Parcelado (2x a 12x)", callback_data=f"c_parcelado_menu_{session_id}"),
            ]
        ]

        await update.message.reply_text(
            f"💳 Pagamento no Crédito\n\n"
            f"📝 Descrição: {descricao_limpa}\n"
            f"🏷️ Categoria: {categoria_final}\n"
            f"💸 Valor: R$ {valor:.2f}\n\n"
            f"Como deseja registrar esse pagamento?",
            reply_markup=InlineKeyboardMarkup(botoes)
        )

    else:
        if not lista_contas:
            await update.message.reply_text("⚠️ Nenhuma conta bancária cadastrada no seu banco!")
            return

        if len(lista_contas) > 1:
            botoes = []
            for c in lista_contas:
                botoes.append([InlineKeyboardButton(f"🏦 {c['nome']}", callback_data=f"cnt_{c['id']}_{session_id}")])

            await update.message.reply_text(
                f"🏦 Selecione a conta utilizada:\n\n"
                f"📝 Descrição: {descricao_limpa}\n"
                f"🏷️ Categoria: {categoria_final}\n"
                f"💸 Valor: R$ {valor:.2f}\n"
                f"⚡ Forma: {forma_pagamento}",
                reply_markup=InlineKeyboardMarkup(botoes)
            )
        else:
            conta_id = lista_contas[0]["id"]
            status_pago = False if e_recorrente else True

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
                "pago": status_pago,
                "tags": tags_final,
            }
            try:
                def _insert_mov():
                    return supabase.table("movimentacoes").insert(payload).execute()

                await asyncio.to_thread(_insert_mov)
                tag_str = f"\n🏷️ Tags: {tags_final}" if tags_final else ""
                icone = "⚡" if forma_pagamento == "Pix" else "💳"
                status_txt = "Pendente (Recorrente)" if e_recorrente else "Pago"
                
                await update.message.reply_text(
                    f"✅ Lançamento Registrado!\n\n"
                    f"💸 Valor: R$ {valor:.2f}\n"
                    f"📝 Descrição: {descricao_limpa}\n"
                    f"🏷️ Categoria: {categoria_final}\n"
                    f"{icone} Forma: {forma_pagamento}\n"
                    f"📅 Data: {data_final}\n"
                    f"📌 Status: {status_txt}{tag_str}"
                )
                context.user_data["lancamentos_temp"].pop(session_id, None)
            except Exception as e:
                await update.message.reply_text(f"⚠️ Erro ao salvar no Supabase: {e}")

async def perguntar_forma_pagamento_recorrente(update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str):
    botoes = [
        [
            InlineKeyboardButton("💵 À Vista", callback_data=f"c_avista_{session_id}"),
            InlineKeyboardButton("📅 Parcelado (2x a 12x)", callback_data=f"c_parcelado_menu_{session_id}"),
        ]
    ]

    texto_msg = "💳 *Como deseja registrar esse gasto fixo?*\n\nEscolha se será À Vista ou Parcelado:"

    if update.callback_query:
        await update.callback_query.edit_message_text(texto_msg, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
    else:
        await update.message.reply_text(texto_msg, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")


async def processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id):
    num_parcelas = dados_temp.get("parcelas", 1)
    valor_total = dados_temp["valor"]
    valor_parcela = round(valor_total / num_parcelas, 2)
    categoria_salvar = dados_temp.get("categoria", "Outros")

    cartao_info = next((c for c in lista_cartoes if c["id"] == cartao_id), None)
    dia_fechamento = cartao_info.get("dia_fechamento") if cartao_info else None

    data_compra = datetime.strptime(dados_temp["data"], "%Y-%m-%d")

    fatura_inicial_str = calcular_mes_fatura(data_compra, dia_fechamento)
    fatura_inicial_dt = datetime.strptime(fatura_inicial_str, "%m/%Y")

    payloads = []
    for i in range(num_parcelas):
        fatura_parcela_dt = fatura_inicial_dt + relativedelta(months=i)
        str_mes_fatura = fatura_parcela_dt.strftime("%m/%Y")

        data_parcela_dt = data_compra + relativedelta(months=i)
        str_data_parcela = data_parcela_dt.strftime("%Y-%m-%d")

        desc_final = dados_temp["descricao"]
        if num_parcelas > 1:
            desc_final = f"{dados_temp['descricao']} ({i+1}/{num_parcelas})"

        payloads.append({
            "usuario_id": dados_temp["usuario_id"],
            "conta_id": None,
            "cartao_id": cartao_id,
            "descricao": desc_final,
            "valor": valor_parcela,
            "tipo": "Despesa",
            "categoria": categoria_salvar,
            "forma_pagamento": "Cartão de Crédito",
            "data": str_data_parcela,
            "mes_fatura": str_mes_fatura,
            "pago": False,
            "tags": dados_temp.get("tags"),
        })

    try:
        def _insert_cartao():
            return supabase.table("movimentacoes").insert(payloads).execute()

        await asyncio.to_thread(_insert_cartao)

        tag_str = f"\n🏷️ Tags: {dados_temp.get('tags')}" if dados_temp.get("tags") else ""
        detalhe_parc = f" em {num_parcelas}x de R$ {valor_parcela:.2f}" if num_parcelas > 1 else ""

        await query.edit_message_text(
            f"✅ Lançamento no Crédito Registrado!\n\n"
            f"💸 Valor Total: R$ {valor_total:.2f}{detalhe_parc}\n"
            f"📝 Descrição: {dados_temp['descricao']}\n"
            f"🏷️ Categoria: {categoria_salvar}\n"
            f"💳 Forma: Cartão de Crédito\n"
            f"📌 Primeiros Vencimentos/Fatura: {payloads[0]['mes_fatura']}{tag_str}"
        )
        context.user_data.get("lancamentos_temp", {}).pop(session_id, None)
    except Exception as e:
        logging.error(f"Erro ao salvar crédito: {e}")
        await query.edit_message_text(f"⚠️ Erro ao salvar no Supabase: {e}")


async def callback_geral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data

    if action.startswith("venc_hoje_"):
        session_id = action.replace("venc_hoje_", "")
        await perguntar_forma_pagamento_recorrente(update, context, session_id)
        return

    if action.startswith("venc_mudar_"):
        session_id = action.replace("venc_mudar_", "")
        context.user_data["session_ativa"] = session_id
        context.user_data["aguardando_dia_vencimento"] = True
        await query.edit_message_text(
            "✍️ *Digite o dia de vencimento dessa conta* (envie apenas o número, ex: `10` ou `25`):",
            parse_mode="Markdown"
        )
        return

    if action.startswith("pagar_rec_"):
        receber_id = int(action.replace("pagar_rec_", ""))
        try:
            def _update_rec():
                return supabase.table("contas_receber").update({"recebido": True}).eq("id", receber_id).execute()

            await asyncio.to_thread(_update_rec)
            
            texto_antigo = query.message.text
            await query.edit_message_text(
                f"{texto_antigo}\n\n"
                f"✅ **STATUS ATUALIZADO: PAGO / RECEBIDO!**",
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            logging.error(f"Erro ao dar baixa em conta a receber: {e}")
            await query.edit_message_text(f"⚠️ Erro ao atualizar status: {e}")
            return

    # Extrai o session_id do final do callback_data
    partes = action.split("_")
    session_id = partes[-1]
    
    dados_temp = context.user_data.get("lancamentos_temp", {}).get(session_id)

    if not dados_temp:
        await query.edit_message_text("⚠️ Sessão expirada ou não encontrada. Por favor, envie o lançamento novamente.")
        return

    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, query.from_user.id)
    lista_cartoes = dados_usuario["cartoes"] if dados_usuario else []

    if action.startswith("c_parcelado_menu_"):
        botoes = []
        val_base = dados_temp["valor"]
        e_rec = dados_temp.get("e_recorrente", False)

        for i in range(2, 13, 2):
            txt_b1 = f"{i}x meses (R$ {val_base:.2f}/mês)" if e_rec else f"{i}x de R$ {(val_base/i):.2f}"
            row = [InlineKeyboardButton(txt_b1, callback_data=f"parc_{i}_{session_id}")]

            if (i + 1) <= 12:
                txt_b2 = f"{i+1}x meses (R$ {val_base:.2f}/mês)" if e_rec else f"{i+1}x de R$ {(val_base/(i+1)):.2f}"
                row.append(InlineKeyboardButton(txt_b2, callback_data=f"parc_{i+1}_{session_id}"))
            
            botoes.append(row)

        msg_texto = (
            f"📅 Selecione por quantos meses deseja REPETIR o valor de R$ {val_base:.2f}/mês:"
            if e_rec else
            f"📅 Selecione por quantas parcelas deseja DIVIDIR este valor de R$ {val_base:.2f}:"
        )

        await query.edit_message_text(
            msg_texto,
            reply_markup=InlineKeyboardMarkup(botoes)
        )
        return

    if action.startswith("parc_"):
        num_parcelas = int(partes[1])
        dados_temp["parcelas"] = num_parcelas

        # CASO 1: FIXO / RECORRENTE
        if dados_temp.get("e_recorrente"):
            valor_parcela = dados_temp["valor"]
            valor_total = valor_parcela * num_parcelas
            
            data_inicial_dt = datetime.strptime(dados_temp["data"], "%Y-%m-%d")
            
            payloads = []
            for i in range(num_parcelas):
                data_parcela_dt = data_inicial_dt + relativedelta(months=i)
                str_data_parcela = data_parcela_dt.strftime("%Y-%m-%d")
                str_mes_fatura = data_parcela_dt.strftime("%m/%Y")

                desc_final = f"{dados_temp['descricao']} ({i+1}/{num_parcelas})"

                payloads.append({
                    "usuario_id": dados_temp["usuario_id"],
                    "conta_id": None,
                    "cartao_id": None,
                    "descricao": desc_final,
                    "valor": valor_parcela,
                    "tipo": "Despesa",
                    "categoria": dados_temp.get("categoria", "Outros"),
                    "forma_pagamento": "Boleto",
                    "data": str_data_parcela,
                    "mes_fatura": str_mes_fatura,
                    "pago": False,
                    "tags": dados_temp.get("tags"),
                })

            try:
                def _insert_parc_fixa():
                    return supabase.table("movimentacoes").insert(payloads).execute()

                await asyncio.to_thread(_insert_parc_fixa)
                tag_str = f"\n🏷️ Tags: {dados_temp['tags']}" if dados_temp.get("tags") else ""

                await query.edit_message_text(
                    f"✅ *Gasto Fixo Agendado!*\n\n"
                    f"💸 *Valor Mensal:* R$ {valor_parcela:.2f}\n"
                    f"📅 *Duração:* {num_parcelas} meses (Total acumulado: R$ {valor_total:.2f})\n"
                    f"📝 *Descrição:* {dados_temp['descricao']}\n"
                    f"🗓️ *Primeiro Vencimento:* {data_inicial_dt.strftime('%d/%m/%Y')}{tag_str}",
                    parse_mode="Markdown"
                )
                context.user_data.get("lancamentos_temp", {}).pop(session_id, None)
            except Exception as e:
                logging.error(f"Erro ao salvar gasto fixo: {e}")
                await query.edit_message_text(f"⚠️ Erro ao salvar no banco: {e}")
            return

        # CASO 2: CARTÃO DE CRÉDITO PARCELADO
        else:
            if len(lista_cartoes) > 1:
                botoes = []
                for c in lista_cartoes:
                    botoes.append([InlineKeyboardButton(f"💳 {c['nome_cartao']}", callback_data=f"crt_{c['id']}_{session_id}")])

                await query.edit_message_text(
                    f"💳 Selecione qual CARTÃO foi utilizado ({num_parcelas}x de R$ {(dados_temp['valor']/num_parcelas):.2f}):\n\n"
                    f"📝 Descrição: {dados_temp['descricao']}\n"
                    f"🏷️ Categoria: {dados_temp.get('categoria', 'Outros')}\n"
                    f"💸 Valor Total: R$ {dados_temp['valor']:.2f}",
                    reply_markup=InlineKeyboardMarkup(botoes)
                )
                return
            else:
                cartao_id = lista_cartoes[0]["id"] if lista_cartoes else None
                await processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id)
                return

    if action.startswith("c_avista_"):
        if dados_temp.get("e_recorrente"):
            lista_contas = dados_usuario.get("contas", []) if dados_usuario else []
            conta_id = lista_contas[0]["id"] if lista_contas else None
            mes_fatura_calc = datetime.strptime(dados_temp["data"], "%Y-%m-%d").strftime("%m/%Y")
            categoria_salvar = dados_temp.get("categoria", "Fixo")

            payload = {
                "usuario_id": dados_temp["usuario_id"],
                "conta_id": conta_id,
                "cartao_id": None,
                "descricao": dados_temp["descricao"],
                "valor": dados_temp["valor"],
                "tipo": "Despesa",
                "categoria": categoria_salvar,
                "forma_pagamento": dados_temp.get("forma_pagamento", "Boleto/Pix"),
                "data": dados_temp["data"],
                "mes_fatura": mes_fatura_calc,
                "pago": False,
                "tags": dados_temp.get("tags"),
            }

            try:
                def _insert_fixo_avista():
                    return supabase.table("movimentacoes").insert(payload).execute()

                await asyncio.to_thread(_insert_fixo_avista)
                tag_str = f"\n🏷️ Tags: {dados_temp['tags']}" if dados_temp.get("tags") else ""
                data_br = datetime.strptime(dados_temp["data"], "%Y-%m-%d").strftime("%d/%m/%Y")

                await query.edit_message_text(
                    f"✅ *Gasto Fixo Registrado com Sucesso!*\n\n"
                    f"📝 Descrição: *{dados_temp['descricao']}*\n"
                    f"💸 Valor: R$ *{dados_temp['valor']:.2f}*\n"
                    f"📅 Vencimento: `{data_br}`\n"
                    f"🏷️ Categoria: {categoria_salvar}{tag_str}",
                    parse_mode="Markdown"
                )
                context.user_data.get("lancamentos_temp", {}).pop(session_id, None)
            except Exception as e:
                await query.edit_message_text(f"⚠️ Erro ao salvar gasto fixo no Supabase: {e}")
            return

        num_parc = dados_temp.get("parcelas", 1)
        if len(lista_cartoes) > 1:
            botoes = []
            for c in lista_cartoes:
                botoes.append([InlineKeyboardButton(f"💳 {c['nome_cartao']}", callback_data=f"crt_{c['id']}_{session_id}")])

            parc_str = f"({num_parc}x)" if num_parc > 1 else "(À Vista)"
            await query.edit_message_text(
                f"💳 Selecione qual CARTÃO foi utilizado {parc_str}:\n\n"
                f"📝 Descrição: {dados_temp['descricao']}\n"
                f"🏷️ Categoria: {dados_temp.get('categoria', 'Outros')}\n"
                f"💸 Valor Total: R$ {dados_temp['valor']:.2f}",
                reply_markup=InlineKeyboardMarkup(botoes)
            )
            return
        else:
            cartao_id = lista_cartoes[0]["id"] if lista_cartoes else None
            await processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id)
            return

    if action.startswith("cnt_"):
        conta_id = int(partes[1])
        mes_fatura_calc = datetime.strptime(dados_temp["data"], "%Y-%m-%d").strftime("%m/%Y")
        categoria_salvar = dados_temp.get("categoria", "Outros")

        payload = {
            "usuario_id": dados_temp["usuario_id"],
            "conta_id": conta_id,
            "cartao_id": None,
            "descricao": dados_temp["descricao"],
            "valor": dados_temp["valor"],
            "tipo": "Despesa",
            "categoria": categoria_salvar,
            "forma_pagamento": dados_temp.get("forma_pagamento", "Pix/Débito"),
            "data": dados_temp["data"],
            "mes_fatura": mes_fatura_calc,
            "pago": True,
            "tags": dados_temp.get("tags"),
        }
        try:
            def _insert_cnt():
                return supabase.table("movimentacoes").insert(payload).execute()

            await asyncio.to_thread(_insert_cnt)
            tag_str = f"\n🏷️ Tags: {dados_temp['tags']}" if dados_temp.get("tags") else ""
            await query.edit_message_text(
                f"✅ Lançamento Registrado!\n\n"
                f"💸 Valor: R$ {dados_temp['valor']:.2f}\n"
                f"📝 Descrição: {dados_temp['descricao']}\n"
                f"🏷️ Categoria: {categoria_salvar}\n"
                f"⚡ Forma: {dados_temp.get('forma_pagamento', 'Pix/Débito')}\n"
                f"📅 Data: {dados_temp['data']}{tag_str}"
            )
            context.user_data.get("lancamentos_temp", {}).pop(session_id, None)
        except Exception as e:
            await query.edit_message_text(f"⚠️ Erro ao salvar no Supabase: {e}")

    elif action.startswith("crt_"):
        cartao_id = int(partes[1])
        await processar_lancamento_cartao(query, context, cartao_id, dados_temp, lista_cartoes, session_id)


async def testar_alertas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Verificando e enviando alertas de boletos do dia...")
    await processar_e_enviar_alertas(context)
    await limpar_botoes_anteriores(update, context)


async def ping_streamlit(context: ContextTypes.DEFAULT_TYPE):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with httpx.AsyncClient() as client:
            response = await client.get(STREAMLIT_URL, headers=headers, timeout=10)
            if response.status_code == 200:
                logging.info("🟢 Ping enviado com sucesso para o Streamlit!")
    except Exception as e:
        logging.error(f"⚠️ Erro ao enviar ping para o Streamlit: {e}")


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
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=None
            )
        except TelegramError:
            pass


async def handler_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Limpa os botões antigos antes de acionar o resumo mensal."""
    await limpar_botoes_anteriores(update, context)
    await enviar_resumo_mensal_telegram(update, context)        


async def job_resumo_mensal(context: ContextTypes.DEFAULT_TYPE):
    """Wrapper para a Job Queue chamar a função do resumo mensal de forma segura."""
    await enviar_resumo_mensal_telegram(None, context)

# --- NOVAS FUNÇÕES: GESTÃO DE CLIENTES RECORRENTES ---

async def cadastrar_cliente_recorrente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cadastra cliente na tabela 'clientes'.
    Uso: /cadastrar Nome | 5565999999999 | 150.00 | 10
    """
    try:
        texto = " ".join(context.args)
        if not texto or "|" not in texto:
            await update.message.reply_text(
                "❌ *Formato incorreto!*\n\n"
                "Use assim:\n`/cadastrar Nome | TelefoneComDDD | Valor | DiaVencimento`\n\n"
                "*Exemplo:*\n`/cadastrar João Silva | 5565999999999 | 150.00 | 10`",
                parse_mode="Markdown"
            )
            return

        dados = [d.strip() for d in texto.split("|")]
        if len(dados) < 4:
            await update.message.reply_text("❌ Preencha todos os 4 campos separados por `|`.", parse_mode="Markdown")
            return

        nome, telefone, valor_raw, dia_raw = dados[0], dados[1], dados[2], dados[3]
        valor = sanitizar_valor(valor_raw)
        dia = int(dia_raw)

        if not (1 <= dia <= 31):
            await update.message.reply_text("⚠️ O dia de vencimento deve ser entre 1 e 31.")
            return

        payload = {
            "nome": nome,
            "telefone": re.sub(r"\D", "", telefone),
            "valor": valor,
            "dia_vencimento": dia,
            "status": "Pendente"
        }

        def _insert_cliente():
            return supabase.table("clientes").insert(payload).execute()

        res = await asyncio.to_thread(_insert_cliente)

        if res.data:
            await update.message.reply_text(
                f"✅ *Cliente Cadastrado com Sucesso!*\n\n"
                f"👤 *Nome:* {nome}\n"
                f"📱 *Telefone:* {payload['telefone']}\n"
                f"💰 *Valor:* R$ {valor:.2f}\n"
                f"📅 *Vence todo dia:* {dia}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Erro ao cadastrar cliente no banco de dados.")

    except Exception as e:
        logging.error(f"Erro ao cadastrar cliente: {e}")
        await update.message.reply_text(f"⚠️ Erro ao processar comando: {e}")


# --- NOVAS FUNÇÕES: GESTÃO DE CLIENTES & COBRANÇAS ---

# --- ETAPAS DA CONVERSA (/cadastrar) ---
NOME, TELEFONE, VALOR, DATA = range(4)

async def iniciar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de cadastro validando a autorização do usuário."""
    await limpar_botoes_anteriores(update, context)
    
    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular sua conta.")
        return ConversationHandler.END

    context.user_data['cad_usuario_id'] = dados_usuario["usuario_id"]
    await update.message.reply_text("👤 **Qual o nome do cliente?**\n\n_(Para cancelar, digite /cancelar)_", parse_mode="Markdown")
    return NOME

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o Nome e pede o Telefone."""
    context.user_data['cad_nome'] = update.message.text.strip()
    await update.message.reply_text("📱 **Qual o telefone do cliente com DDD?**\n_(Exemplo: 556599999999) (Sem o 9)_", parse_mode="Markdown")
    return TELEFONE

async def receber_telefone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o Telefone e pede o Valor."""
    telefone_limpo = re.sub(r"\D", "", update.message.text)
    context.user_data['cad_telefone'] = telefone_limpo
    await update.message.reply_text("💰 **Qual o valor da mensalidade/cobrança?**\n_(Exemplo: 150,00)_", parse_mode="Markdown")
    return VALOR

async def receber_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o Valor e pede a Data de Vencimento."""
    try:
        valor = sanitizar_valor(update.message.text)
        context.user_data['cad_valor'] = valor
        await update.message.reply_text("📅 **Qual a data de vencimento?**\n_(Formatos aceitos: `25/08/2026` ou `2026-08-25`)_", parse_mode="Markdown")
        return DATA
    except Exception:
        await update.message.reply_text("⚠️ Valor inválido. Digite apenas o número (ex: 150.00 ou 150,00):")
        return VALOR

async def receber_data_e_salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a Data, grava no Supabase com o vínculo do usuário e finaliza a conversa."""
    texto_data = update.message.text.strip()
    
    try:
        if "/" in texto_data:
            data_obj = datetime.strptime(texto_data, "%d/%m/%Y")
        else:
            data_obj = datetime.strptime(texto_data, "%Y-%m-%d")
        data_iso = data_obj.strftime("%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("⚠️ Data em formato incorreto. Digite como `DD/MM/AAAA` (ex: `25/08/2026`):")
        return DATA

    nome = context.user_data['cad_nome']
    telefone = context.user_data['cad_telefone']
    valor = context.user_data['cad_valor']
    usuario_id = context.user_data['cad_usuario_id']

    payload = {
        "nome": nome,
        "telefone": telefone,
        "valor": valor,
        "data_vencimento": data_iso,
        "status": "Pendente",
        "usuario_id": usuario_id
    }

    try:
        def _insert_cliente():
            return supabase.table("clientes").insert(payload).execute()

        res = await asyncio.to_thread(_insert_cliente)

        if res.data:
            data_br = data_obj.strftime("%d/%m/%Y")
            await update.message.reply_text(
                f"✅ **Cliente Cadastrado com Sucesso!**\n\n"
                f"👤 **Nome:** {nome}\n"
                f"📱 **Telefone:** {telefone}\n"
                f"💰 **Valor:** R$ {valor:.2f}\n"
                f"📅 **Vencimento:** {data_br}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Erro ao salvar cliente no banco de dados.")

    except Exception as e:
        logging.error(f"Erro ao salvar cliente: {e}")
        await update.message.reply_text(f"⚠️ Erro ao registrar no banco: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def cancelar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await limpar_botoes_anteriores(update, context)
    """Cancela o processo de cadastro."""
    context.user_data.clear()
    await update.message.reply_text("❌ Cadastro cancelado.")
    return ConversationHandler.END


async def listar_clientes_recorrentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await limpar_botoes_anteriores(update, context)

    """
    Lista os clientes pertencentes ao usuário atual com botões de Editar e Excluir.
    Uso: /clientes
    """

    telegram_id = update.effective_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Envie /start para configurar sua conta.")
        return

    usuario_id = dados_usuario["usuario_id"]

    try:
        def _get_clientes():
            return (
                supabase.table("clientes")
                .select("*")
                .eq("usuario_id", usuario_id)
                .order("data_vencimento")
                .execute()
            )

        res = await asyncio.to_thread(_get_clientes)
        clientes = res.data or []

        if not clientes:
            await update.message.reply_text("📂 Nenhum cliente cadastrado na sua conta.")
            return

        await update.message.reply_text("📋 *Sua Lista de Clientes Cadastrados:*", parse_mode="Markdown")

        # Recupera a lista de IDs ou cria uma nova se não existir
        mensagens_com_botoes = context.user_data.get("mensagens_botoes_antigas", [])

        for c in clientes:
            try:
                data_br = datetime.strptime(c['data_vencimento'], "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                data_br = c['data_vencimento']

            status_emoji = "✅" if c.get('status') == 'Pago' else "⏳"
            
            msg_texto = (
                f"👤 *{c['nome']}*\n"
                f"📱 `{c['telefone']}` | 💰 R$ {float(c['valor']):.2f}\n"
                f"📅 Vencimento: *{data_br}* ({status_emoji} {c.get('status', 'Pendente')})"
            )

            # Botões inline específicos para este cliente
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Editar", callback_data=f"cledit_{c['id']}"),
                    InlineKeyboardButton("🗑️ Excluir", callback_data=f"cldel_{c['id']}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Envia a mensagem e captura a resposta para extrair o ID
            msg_enviada = await update.message.reply_text(msg_texto, parse_mode="Markdown", reply_markup=reply_markup)
            
            # Guarda o ID da mensagem para poder fechar/limpar depois
            mensagens_com_botoes.append(msg_enviada.message_id)

        # Atualiza a lista no context
        context.user_data["mensagens_botoes_antigas"] = mensagens_com_botoes

    except Exception as e:
        logging.error(f"Erro ao listar clientes: {e}")
        await update.message.reply_text("❌ Erro ao buscar a lista de clientes no Supabase.")

# --- TRATAMENTO DOS BOTÕES DE AÇÃO (EXCLUSÃO E EDICAO DE DATA) ---

async def botao_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    telegram_id = query.from_user.id
    dados_usuario = await asyncio.to_thread(buscar_dados_usuario, telegram_id)

    if not dados_usuario:
        await query.edit_message_text("🚫 Operação não autorizada.")
        return

    usuario_id = dados_usuario["usuario_id"]

    if data.startswith("cldel_"):
        cliente_id = int(data.split("_")[1])
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar Exclusão", callback_data=f"confdel_{cliente_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel_action")
            ]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("confdel_"):
        cliente_id = int(data.split("_")[1])

        # Exclui apenas se o cliente pertencer ao usuário logado
        def _delete():
            return (
                supabase.table("clientes")
                .delete()
                .eq("id", cliente_id)
                .eq("usuario_id", usuario_id)
                .execute()
            )

        res = await asyncio.to_thread(_delete)
        if res.data:
            await query.edit_message_text("🗑️ *Cliente excluído com sucesso!*", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Erro ao excluir: cliente não encontrado ou sem permissão.")

    elif data.startswith("cledit_"):
        cliente_id = int(data.split("_")[1])

        def _get_nome():
            return (
                supabase.table("clientes")
                .select("nome")
                .eq("id", cliente_id)
                .eq("usuario_id", usuario_id)
                .execute()
            )
        
        res = await asyncio.to_thread(_get_nome)
        if res.data:
            nome = res.data[0]['nome']
            await query.message.reply_text(
                f"✏️ Para alterar a data de *{nome}*, copie a mensagem abaixo, altere a data e envie:\n\n"
                f"`/data {cliente_id} 25/08/2026`",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("❌ Cliente não encontrado ou sem permissão.")

    elif data == "cancel_action":
        await query.edit_message_text("❌ Ação cancelada.")


# --- COMANDO PARA SALVAR A NOVA DATA ---

async def alterar_data_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await limpar_botoes_anteriores(update, context)
    """
    Atualiza a data do cliente no Supabase.
    Uso: /data ID DD/MM/AAAA
    """
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Use assim: `/data ID DATA` (Ex: `/data 5 25/08/2026`)", parse_mode="Markdown")
            return

        cliente_id = int(args[0])
        data_raw = args[1]

        # Tratamento do formato da data
        if "/" in data_raw:
            dt = datetime.strptime(data_raw, "%d/%m/%Y")
        else:
            dt = datetime.strptime(data_raw, "%Y-%m-%d")
        
        data_iso = dt.strftime("%Y-%m-%d")
        data_br = dt.strftime("%d/%m/%Y")

        # Atualiza apenas a data no Supabase pelo ID do cliente
        def _update():
            return supabase.table("clientes").update({"data_vencimento": data_iso}).eq("id", cliente_id).execute()

        res = await asyncio.to_thread(_update)

        if res.data:
            await update.message.reply_text(f"✅ Data de vencimento alterada para *{data_br}*!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Cliente não encontrado.")

    except ValueError:
        await update.message.reply_text("⚠️ Data em formato inválido. Use `DD/MM/AAAA` (Ex: `25/08/2026`).")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro ao atualizar: {e}")


def main():
    global supabase

    # Validação rigorosa das variáveis de ambiente na inicialização
    if not TELEGRAM_TOKEN:
        logging.critical("❌ Erro: Variável TELEGRAM_TOKEN não configurada no arquivo .env!")
        sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.critical("❌ Erro: SUPABASE_URL ou SUPABASE_KEY não configuradas no arquivo .env!")
        sys.exit(1)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY, options=options)

    print("🤖 Bot de Finanças iniciado e escutando mensagens...")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    fuso_br = pytz.timezone("America/Sao_Paulo")

    app.job_queue.run_daily(
        processar_e_enviar_alertas,
        time=time(hour=9, minute=0, tzinfo=fuso_br)
    )

    app.job_queue.run_daily(
        processar_e_enviar_alertas,
        time=time(hour=15, minute=0, tzinfo=fuso_br)
    )

    app.job_queue.run_repeating(
        ping_streamlit,
        interval=18000,
        first=18000
    )

    app.job_queue.run_monthly(
        job_resumo_mensal,
        when=time(hour=8, minute=0, tzinfo=fuso_br),
        day=1
    )

    # --- HANDLERS DE COMANDOS BÁSICOS ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", consultar_contas_receber))
    app.add_handler(CommandHandler("receber", consultar_contas_receber))
    app.add_handler(CommandHandler("cancelar", cancelar_edicao))

    app.add_handler(CommandHandler(["listar", "lancamentos"], listar_lancamentos))
    app.add_handler(CommandHandler("receita", lancar_receita))
    app.add_handler(CommandHandler("entrada", lancar_receita))
    app.add_handler(CommandHandler("testar_alertas", testar_alertas_cmd))
    app.add_handler(CommandHandler("resumo", handler_resumo))

    # --- CLIENTES (LISTAGEM E ALTERAÇÃO DE DATA) ---
    app.add_handler(CommandHandler("clientes", listar_clientes_recorrentes))
    app.add_handler(CommandHandler("data", alterar_data_comando))

    # Handlers da conversa do /cadastrar
    conv_handler_cliente = ConversationHandler(
        entry_points=[CommandHandler("cadastrar", iniciar_cadastro)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_telefone)],
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor)],
            DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_data_e_salvar)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_cadastro)]
    )
    app.add_handler(conv_handler_cliente)

    # --- CALLBACKS DOS BOTÕES ---
    # Botões dos Clientes
    app.add_handler(CallbackQueryHandler(botao_callback_handler, pattern="^(cldel_|cledit_|confdel_|cancel_action)"))
    
    # Botões de Lançamentos Financeiros Gerais
    app.add_handler(CallbackQueryHandler(tratar_botoes_lancamento, pattern="^(del_|edit_)"))
    app.add_handler(CallbackQueryHandler(callback_geral))

    # --- MENSAGENS DE TEXTO E CONTATOS ---
    app.add_handler(
        MessageHandler(
            filters.Regex(re.compile(r"^resumo$", re.IGNORECASE)),
            handler_resumo
        )
    )
    app.add_handler(MessageHandler(filters.CONTACT, receber_contato))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_gastos))

    app.run_polling()


if __name__ == "__main__":
    main()