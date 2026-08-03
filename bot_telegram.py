import json
import logging
import os
import re
from datetime import datetime, time
from dateutil.relativedelta import relativedelta

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

from lembrete_boletos import processar_e_enviar_alertas

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO)

CACHE_USUARIOS = {}


def buscar_dados_usuario(telegram_id):
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

            CACHE_USUARIOS[telegram_id_int] = dados
            return dados

    except Exception as e:
        logging.error(f"Erro ao buscar dados do usuário: {e}")

    return None


def calcular_mes_fatura(data_compra, dia_fechamento):
    """Calcula a fatura correta (MM/YYYY) considerando o dia de fechamento do cartão."""
    if not dia_fechamento:
        return data_compra.strftime("%m/%Y")

    dia_fechamento = int(dia_fechamento)

    if data_compra.day >= dia_fechamento:
        proximo_mes = data_compra + relativedelta(months=1)
        return proximo_mes.strftime("%m/%Y")
    
    return data_compra.strftime("%m/%Y")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = buscar_dados_usuario(telegram_id)

    if dados_usuario:
        await update.message.reply_text(
            "👋 Você já está cadastrado no FinanceiroPro!\n\n"
            "• Para lançar: `290.00 teste receber 15/08`\n"
            "• Para consultar pendentes: Digite /status ou `receber`"
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
        response = (
            supabase.table("usuarios")
            .select("id, telefone")
            .or_(f"telefone.eq.{telefone_telegram},telefone.eq.{telefone_sem_9}")
            .execute()
        )

        if response.data:
            usuario = response.data[0]
            usuario_id = usuario["id"]

            supabase.table("usuarios").update({"telegram_id": telegram_id}).eq("id", usuario_id).execute()

            CACHE_USUARIOS.pop(telegram_id, None)
            buscar_dados_usuario(telegram_id)

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


# =========================================================
# CONSULTAR CONTAS A RECEBER PENDENTES
# =========================================================
async def consultar_contas_receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    dados_usuario = buscar_dados_usuario(telegram_id)

    if not dados_usuario:
        await update.message.reply_text("🚫 Acesso não autorizado! Digite /start para vincular.")
        return

    usuario_id = dados_usuario["usuario_id"]

    try:
        res = (
            supabase.table("contas_receber")
            .select("*")
            .eq("usuario_id", usuario_id)
            .eq("recebido", False)
            .order("data_recebimento", desc=False)
            .execute()
        )

        pendentes = res.data if res.data else []

        if not pendentes:
            await update.message.reply_text("🎉 Você não possui nenhuma conta a receber pendente!")
            return

        total_pendente = sum(item["valor"] for item in pendentes)

        await update.message.reply_text(
            f"📥 Contas a Receber Pendentes\n"
            f"💰 Total a receber: **R$ {total_pendente:.2f}**\n"
            f"───────────────"
        )

        for item in pendentes:
            data_formatada = datetime.strptime(item["data_recebimento"], "%Y-%m-%d").strftime("%d/%m/%Y")
            botoes = [[InlineKeyboardButton("✅ Marcar como Pago", callback_data=f"pagar_rec_{item['id']}")]]
            
            await update.message.reply_text(
                f"📝 {item['descricao']}\n"
                f"💵 Valor: R$ {item['valor']:.2f}\n"
                f"📅 Previsão: {data_formatada}",
                reply_markup=InlineKeyboardMarkup(botoes)
            )

    except Exception as e:
        logging.error(f"Erro ao consultar contas a receber: {e}")
        await update.message.reply_text(f"⚠️ Erro ao consultar banco de dados: {e}")


async def registrar_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id

    CACHE_USUARIOS.pop(telegram_id, None)
    dados_usuario = buscar_dados_usuario(telegram_id)

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

    # Atalhos rápidos para consulta
    if texto.lower() in ["status", "receber", "pendentes", "contas"]:
        await consultar_contas_receber(update, context)
        return

    # 1. Extrai hashtags
    tags_encontradas = re.findall(r"#(\w+)", texto)
    tags_final = " ".join([f"#{t.lower()}" for t in tags_encontradas]) if tags_encontradas else None
    texto_sem_tags = re.sub(r"#\w+", "", texto).strip()

    # 2. Extrai data personalizada (Ex: 15/08 ou 15/08/2026)
    match_data = re.search(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", texto_sem_tags)
    now = datetime.now()

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

    # 3. Extrai valor e descrição
    pattern = r"^(?:r\$\s*)?([\d.,]+)\s*(?:reais|reias)?\s+(.+)$"
    match = re.match(pattern, texto_sem_tags, re.IGNORECASE)

    if not match:
        await update.message.reply_text(
            "⚠️ Formato inválido!\n\n"
            "Exemplos aceitos:\n"
            "• `120.00 Internet fixo` (Usa a Data de Hoje)\n"
            "• `120.00 Internet fixo 15/08` (Usa a Data 15/08)\n"
            "• `290.00 Teste receber 15/08` (Lançamento Para Notificar no Dia 15/08)\n"
            "• `50,00 Comida Pix` (Lançamento de Pix)\n"
            "• `50,00 Comida Crédito` (Lançamento de Crédito)\n"
            "• `50,00 Comida Débito` (Lançamento de Débito)\n"    
            "• `Status, Receber ou Pendentes` (Para Consultar os Lançamentos que tem a receber)\n"
        )
        return

    valor_raw, descricao_bruta = match.groups()

    try:
        valor = float(valor_raw.replace(".", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Valor numérico inválido.")
        return

    texto_lower = descricao_bruta.lower()

    # =========================================================
    # FLUXO 0: CONTAS A RECEBER (Salva na tabela 'contas_receber')
    # =========================================================
    e_recebimento = any(kw in texto_lower for kw in ["receber", "ganho", "receita", "salario", "salário", "venda"])

    if e_recebimento:
        palavras_remover = r"\b(receber|ganho|receita|salario|salário|venda)\b"
        descricao_limpa = re.sub(palavras_remover, "", descricao_bruta, flags=re.IGNORECASE).strip()

        payload_receber = {
            "usuario_id": usuario_id,
            "descricao": descricao_limpa or "Recebimento",
            "valor": valor,
            "data_recebimento": data_final,
            "recebido": False,
        }

        try:
            supabase.table("contas_receber").insert(payload_receber).execute()
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

    # =========================================================
    # FLUXO DESPESAS (Mantém a lógica normal para movimentações)
    # =========================================================
    e_credito = any(kw in texto_lower for kw in ["credito", "crédito", "cartao", "cartão"])
    e_debito = any(kw in texto_lower for kw in ["debito", "débito"])
    forma_pagamento = "Cartão de Crédito" if e_credito else ("Cartão de Débito" if e_debito else "Pix")

    palavras_remover = r"\b(pix|debito|débito|credito|crédito|cartao|cartão)\b"
    descricao_limpa = re.sub(palavras_remover, "", descricao_bruta, flags=re.IGNORECASE).strip()

    context.user_data["temp_lancamento"] = {
        "usuario_id": usuario_id,
        "valor": valor,
        "descricao": descricao_limpa,
        "forma_pagamento": forma_pagamento,
        "data": data_final,
        "tags": tags_final,
    }

    # FLUXO CRÉDITO
    if e_credito:
        if not lista_cartoes:
            await update.message.reply_text("⚠️ Nenhum cartão de crédito cadastrado no seu banco!")
            return

        botoes = [
            [
                InlineKeyboardButton("💵 À Vista", callback_data="c_avista"),
                InlineKeyboardButton("📅 Parcelado (2x a 12x)", callback_data="c_parcelado_menu"),
            ]
        ]

        await update.message.reply_text(
            f"💳 Pagamento no Crédito\n\n"
            f"📝 Descrição: {descricao_limpa}\n"
            f"💸 Valor: R$ {valor:.2f}\n\n"
            f"Como deseja registrar esse pagamento?",
            reply_markup=InlineKeyboardMarkup(botoes)
        )

    # FLUXO PIX / DÉBITO
    else:
        if not lista_contas:
            await update.message.reply_text("⚠️ Nenhuma conta bancária cadastrada no seu banco!")
            return

        mes_fatura_atual = datetime.strptime(data_final, "%Y-%m-%d").strftime("%m/%Y")

        if len(lista_contas) > 1:
            botoes = []
            for c in lista_contas:
                botoes.append([InlineKeyboardButton(f"🏦 {c['nome']}", callback_data=f"cnt_{c['id']}")])

            await update.message.reply_text(
                f"🏦 Selecione a conta utilizada:\n\n"
                f"📝 Descrição: {descricao_limpa}\n"
                f"💸 Valor: R$ {valor:.2f}\n"
                f"⚡ Forma: {forma_pagamento}",
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
                "categoria": "Outros",
                "forma_pagamento": forma_pagamento,
                "data": data_final,
                "mes_fatura": mes_fatura_atual,
                "pago": True,
                "tags": tags_final,
            }
            try:
                supabase.table("movimentacoes").insert(payload).execute()
                tag_str = f"\n🏷️ Tags: {tags_final}" if tags_final else ""
                icone = "⚡" if forma_pagamento == "Pix" else "💳"
                await update.message.reply_text(
                    f"✅ Lançamento Registrado!\n\n"
                    f"💸 Valor: R$ {valor:.2f}\n"
                    f"📝 Descrição: {descricao_limpa}\n"
                    f"{icone} Forma: {forma_pagamento}\n"
                    f"📅 Data: {data_final}{tag_str}"
                )
            except Exception as e:
                await update.message.reply_text(f"⚠️ Erro ao salvar no Supabase: {e}")


async def callback_geral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data

    # =========================================================
    # MARCAR CONTA A RECEBER COMO PAGO
    # =========================================================
    if action.startswith("pagar_rec_"):
        receber_id = int(action.replace("pagar_rec_", ""))
        try:
            supabase.table("contas_receber").update({"recebido": True}).eq("id", receber_id).execute()
            
            texto_antigo = query.message.text
            await query.edit_message_text(
                f"{texto_antigo}\n\n"
                f"✅ **STATUS ATUALIZADO: PAGO / RECEBIDO!**"
            )
            return
        except Exception as e:
            logging.error(f"Erro ao dar baixa em conta a receber: {e}")
            await query.edit_message_text(f"⚠️ Erro ao atualizar status: {e}")
            return

    dados_temp = context.user_data.get("temp_lancamento")

    if not dados_temp:
        await query.edit_message_text("⚠️ Sessão expirada. Por favor, envie o lançamento novamente.")
        return

    dados_usuario = buscar_dados_usuario(query.from_user.id)
    lista_cartoes = dados_usuario["cartoes"] if dados_usuario else []

    # 1. Escolheu 'Parcelado'
    if action == "c_parcelado_menu":
        botoes = []
        for i in range(2, 13, 2):
            p1_valor = dados_temp["valor"] / i
            p2_valor = dados_temp["valor"] / (i + 1) if (i + 1) <= 12 else None

            row = [InlineKeyboardButton(f"{i}x (R$ {p1_valor:.2f})", callback_data=f"parc_{i}")]
            if p2_valor:
                row.append(InlineKeyboardButton(f"{i+1}x (R$ {p2_valor:.2f})", callback_data=f"parc_{i+1}"))
            botoes.append(row)

        await query.edit_message_text(
            f"📅 Selecione a quantidade de parcelas para R$ {dados_temp['valor']:.2f}:",
            reply_markup=InlineKeyboardMarkup(botoes)
        )
        return

    # 2. Definiu número de parcelas
    if action.startswith("parc_"):
        num_parcelas = int(action.replace("parc_", ""))
        dados_temp["parcelas"] = num_parcelas
        action = "c_avista"

    # 3. Seleção de Cartão
    if action == "c_avista":
        num_parc = dados_temp.get("parcelas", 1)
        if len(lista_cartoes) > 1:
            botoes = []
            for c in lista_cartoes:
                botoes.append([InlineKeyboardButton(f"💳 {c['nome_cartao']}", callback_data=f"crt_{c['id']}")])

            parc_str = f"({num_parc}x)" if num_parc > 1 else "(À Vista)"
            await query.edit_message_text(
                f"💳 Selecione qual CARTÃO foi utilizado {parc_str}:\n\n"
                f"📝 Descrição: {dados_temp['descricao']}\n"
                f"💸 Valor Total: R$ {dados_temp['valor']:.2f}",
                reply_markup=InlineKeyboardMarkup(botoes)
            )
            return
        else:
            cartao_id = lista_cartoes[0]["id"] if lista_cartoes else None
            action = f"crt_{cartao_id}"

    # 4. SALVAR PIX / DÉBITO
    if action.startswith("cnt_"):
        conta_id = int(action.replace("cnt_", ""))
        mes_fatura_calc = datetime.strptime(dados_temp["data"], "%Y-%m-%d").strftime("%m/%Y")
        payload = {
            "usuario_id": dados_temp["usuario_id"],
            "conta_id": conta_id,
            "cartao_id": None,
            "descricao": dados_temp["descricao"],
            "valor": dados_temp["valor"],
            "tipo": "Despesa",
            "categoria": "Outros",
            "forma_pagamento": dados_temp["forma_pagamento"],
            "data": dados_temp["data"],
            "mes_fatura": mes_fatura_calc,
            "pago": True,
            "tags": dados_temp["tags"],
        }
        try:
            supabase.table("movimentacoes").insert(payload).execute()
            tag_str = f"\n🏷️ Tags: {dados_temp['tags']}" if dados_temp["tags"] else ""
            await query.edit_message_text(
                f"✅ Lançamento Registrado!\n\n"
                f"💸 Valor: R$ {dados_temp['valor']:.2f}\n"
                f"📝 Descrição: {dados_temp['descricao']}\n"
                f"⚡ Forma: {dados_temp['forma_pagamento']}\n"
                f"📅 Data: {dados_temp['data']}{tag_str}"
            )
            context.user_data.pop("temp_lancamento", None)
        except Exception as e:
            await query.edit_message_text(f"⚠️ Erro ao salvar no Supabase: {e}")

    # 5. SALVAR CRÉDITO
    elif action.startswith("crt_"):
        cartao_id = int(action.replace("crt_", ""))
        num_parcelas = dados_temp.get("parcelas", 1)
        valor_total = dados_temp["valor"]
        valor_parcela = round(valor_total / num_parcelas, 2)

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
                "categoria": "Outros",
                "forma_pagamento": "Cartão de Crédito",
                "data": str_data_parcela,
                "mes_fatura": str_mes_fatura,
                "pago": False,
                "tags": dados_temp["tags"],
            })

        try:
            supabase.table("movimentacoes").insert(payloads).execute()

            tag_str = f"\n🏷️ Tags: {dados_temp['tags']}" if dados_temp["tags"] else ""
            detalhe_parc = f" em {num_parcelas}x de R$ {valor_parcela:.2f}" if num_parcelas > 1 else ""

            await query.edit_message_text(
                f"✅ Lançamento no Crédito Registrado!\n\n"
                f"💸 Valor Total: R$ {valor_total:.2f}{detalhe_parc}\n"
                f"📝 Descrição: {dados_temp['descricao']}\n"
                f"💳 Forma: Cartão de Crédito\n"
                f"📌 Primeiros Vencimentos/Fatura: {payloads[0]['mes_fatura']}{tag_str}"
            )
            context.user_data.pop("temp_lancamento", None)
        except Exception as e:
            logging.error(f"Erro ao salvar crédito: {e}")
            await query.edit_message_text(f"⚠️ Erro ao salvar no Supabase: {e}")


async def testar_alertas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Verificando e enviando alertas de boletos do dia...")
    await processar_e_enviar_alertas(context)


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

    # Handlers dos comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", consultar_contas_receber))
    app.add_handler(CommandHandler("receber", consultar_contas_receber))
    app.add_handler(CommandHandler("testar_alertas", testar_alertas_cmd))
    
    app.add_handler(MessageHandler(filters.CONTACT, receber_contato))
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), registrar_gastos)
    )
    app.add_handler(CallbackQueryHandler(callback_geral))

    app.run_polling()


if __name__ == "__main__":
    main()