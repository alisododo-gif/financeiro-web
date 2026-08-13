import asyncio
import calendar
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv
import pytz
from supabase import Client, create_client
from telegram import Bot

# 1. Carrega as variáveis de ambiente
load_dotenv()

# Configuração de logs
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot_global = Bot(token=TELEGRAM_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fuso horário oficial do Brasil
FUSO_BR = pytz.timezone("America/Sao_Paulo")


def formatar_moeda(valor) -> str:
    """Auxiliar para formatar valores no padrão R$ 0.000,00."""
    try:
        valor_num = float(valor)
        return f"{valor_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(valor)


def extrair_nome_usuario(dados: dict) -> str:
    """Extrai o nome do usuário das views ou busca na tabela usuarios pelo usuario_id."""
    # 1. Tenta pegar do próprio resultado da view
    nome = dados.get("usuario") or dados.get("nome_usuario") or dados.get("nome")
    if nome:
        return nome

    # 2. Se a view só trouxe o usuario_id, busca o nome diretamente no Supabase
    usuario_id = dados.get("usuario_id")
    if usuario_id:
        try:
            res = supabase.table("usuarios").select("usuario").eq("id", usuario_id).execute()
            if res.data and len(res.data) > 0:
                nome_db = res.data[0].get("usuario")
                if nome_db:
                    return nome_db
        except Exception as e:
            logging.error(f"Erro ao buscar nome para usuario_id {usuario_id}: {e}")

    return "Cliente"


def consultar_view(nome_view: str, filtrar_pago: bool = True):
    """Consulta lançamentos na view informada."""
    try:
        query = supabase.table(nome_view).select("*")
        if filtrar_pago:
            query = query.eq("pago", False)
        resposta = query.execute()
        return resposta.data or []
    except Exception as e:
        logging.error(f"Erro ao consultar {nome_view}: {e}")
        return []


async def processar_e_enviar_alertas(param=None):
    """Busca dados nas views (hoje, amanhã, faturas e contas a receber) e envia mensagens."""
    chat_id_solicitante = None
    
    # Identifica a instância correta do bot (do contexto da aplicação ou global)
    bot_instancia = bot_global
    if hasattr(param, "bot") and param.bot:
        bot_instancia = param.bot

    if isinstance(param, int):
        chat_id_solicitante = param
    elif hasattr(param, "effective_chat") and param.effective_chat:
        chat_id_solicitante = param.effective_chat.id

    agora_br = datetime.now(FUSO_BR)
    hoje_str = agora_br.strftime("%d/%m/%Y")
    amanha_str = (agora_br + timedelta(days=1)).strftime("%d/%m/%Y")

    # =========================================================
    # 1. LEITURA E ENVIO DOS LANÇAMENTOS DE HOJE
    # =========================================================
    boletos_hoje = consultar_view("lancamentos_hoje")
    
    if not boletos_hoje:
        logging.info("Nenhum boleto a vencer HOJE.")
        if chat_id_solicitante:
            try:
                await bot_instancia.send_message(
                    chat_id=chat_id_solicitante,
                    text="ℹ️ Nenhum boleto pendente para vencer hoje!"
                )
            except Exception as e:
                logging.error(f"Erro ao enviar aviso de lista vazia: {e}")

    for boleto in boletos_hoje:
        telegram_id = boleto.get("telegram_id")
        nome_usuario = extrair_nome_usuario(boleto)

        if telegram_id:
            descricao = boleto.get("descricao", "Sem descrição")
            valor_formatado = formatar_moeda(boleto.get("valor", 0.0))

            mensagem = (
                f"Olá! *{nome_usuario}* Espero que esteja tendo um ótimo dia. 😊\n\n"
                f"Lembrete rápido sobre o seu boleto que vence na data de hoje!\n\n"
                f"*📆 Data: {hoje_str}*\n"
                f"*📄 Descrição: {descricao}*\n"
                f"*💰 Valor: R$ {valor_formatado}*\n\n"
                f"Se já realizou o pagamento, pode desconsiderar esta mensagem.\n\n"
                f"*FinanceiroPro Web Agradece a Parceria 🫡*"
            )

            try:
                await bot_instancia.send_message(
                    chat_id=telegram_id, text=mensagem, parse_mode="Markdown"
                )
                logging.info(
                    f"Aviso de HOJE enviado com sucesso para {nome_usuario} ({telegram_id})"
                )
            except Exception as e:
                logging.error(
                    f"Falha ao enviar mensagem de HOJE para {telegram_id}: {e}"
                )

    # =========================================================
    # 2. LEITURA E ENVIO DOS LANÇAMENTOS DE AMANHÃ
    # =========================================================
    boletos_amanha = consultar_view("lancamentos_amanha")

    if not boletos_amanha:
        logging.info("Nenhum boleto a vencer AMANHÃ.")

    for boleto in boletos_amanha:
        telegram_id = boleto.get("telegram_id")
        nome_usuario = extrair_nome_usuario(boleto)

        if telegram_id:
            descricao = boleto.get("descricao", "Sem descrição")
            valor_formatado = formatar_moeda(boleto.get("valor", 0.0))

            mensagem = (
                f"Olá! *{nome_usuario}* Espero que esteja tendo um ótimo dia. 😊\n\n"
                f"Lembrete rápido sobre o seu boleto que vence amanhã!\n\n"
                f"*📆 Data: {amanha_str}*\n"
                f"*📄 Descrição: {descricao}*\n"
                f"*💰 Valor: R$ {valor_formatado}*\n\n"
                f"Se já realizou o pagamento, pode desconsiderar esta mensagem.\n\n"
                f"*FinanceiroPro Web Agradece a Parceria 🫡*"
            )

            try:
                await bot_instancia.send_message(
                    chat_id=telegram_id, text=mensagem, parse_mode="Markdown"
                )
                logging.info(
                    f"Aviso de AMANHÃ enviado com sucesso para {nome_usuario} ({telegram_id})"
                )
            except Exception as e:
                logging.error(
                    f"Falha ao enviar mensagem de AMANHÃ para {telegram_id}: {e}"
                )

    # =========================================================
    # 3. LEITURA E ENVIO DAS FATURAS DE CARTÃO DE CRÉDITO VENCENDO HOJE
    # =========================================================
    faturas_cartao = consultar_view("faturas_vencendo_hoje", filtrar_pago=False)

    if not faturas_cartao:
        logging.info("Nenhuma fatura de cartão vencendo HOJE.")

    for fatura in faturas_cartao:
        telegram_id = fatura.get("telegram_id")
        nome_usuario = extrair_nome_usuario(fatura)
        nome_cartao = fatura.get("nome_cartao", "Cartão de Crédito")

        if telegram_id:
            mensagem = (
                f"Olá! *{nome_usuario}* Espero que esteja tendo um ótimo dia. 😊\n\n"
                f"💳 *Lembrete de Fatura de Cartão de Crédito*\n\n"
                f"A fatura do seu cartão *{nome_cartao}* vence na data de hoje!\n\n"
                f"*📆 Data de Vencimento: {hoje_str}*\n\n"
                f"Não se esqueça de checar o aplicativo do cartão e efetuar o pagamento.\n\n"
                f"*FinanceiroPro Web Agradece a Parceria 🫡*"
            )

            try:
                await bot_instancia.send_message(
                    chat_id=telegram_id, text=mensagem, parse_mode="Markdown"
                )
                logging.info(
                    f"Aviso de Fatura enviado para {nome_usuario} ({telegram_id}) - Cartão: {nome_cartao}"
                )
            except Exception as e:
                logging.error(
                    f"Falha ao enviar aviso de Fatura para {telegram_id}: {e}"
                )

    # =========================================================
    # 4. LEITURA E ENVIO DOS RECEBIMENTOS DE HOJE
    # =========================================================
    recebimentos_hoje = consultar_view("recebimentos_hoje", filtrar_pago=False)

    if not recebimentos_hoje:
        logging.info("Nenhum valor a receber HOJE.")

    for rec in recebimentos_hoje:
        telegram_id = rec.get("telegram_id")
        nome_usuario = extrair_nome_usuario(rec)

        if telegram_id:
            descricao = rec.get("descricao", "Sem descrição")
            valor_formatado = formatar_moeda(rec.get("valor", 0.0))

            mensagem = (
                f"Olá! *{nome_usuario}* Espero que esteja tendo um ótimo dia. 😊\n\n"
                f"🤑 *Lembrete de Conta a Receber!*\n\n"
                f"Você tem um valor previsto para receber na data de hoje:\n\n"
                f"*📆 Data: {hoje_str}*\n"
                f"*📄 Descrição: {descricao}*\n"
                f"*💰 Valor: R$ {valor_formatado}*\n\n"
                f"Não se esqueça de checar sua conta bancária!\n\n"
                f"*FinanceiroPro Web Agradece a Parceria 🫡*"
            )

            try:
                await bot_instancia.send_message(
                    chat_id=telegram_id, text=mensagem, parse_mode="Markdown"
                )
                logging.info(
                    f"Alerta de recebimento enviado para {nome_usuario} ({telegram_id})"
                )
            except Exception as e:
                logging.error(
                    f"Falha ao enviar alerta de recebimento para {telegram_id}: {e}"
                )


async def enviar_resumo_mensal_telegram(update=None, context=None):
    """Gera e envia o relatório financeiro completo para todos os usuários cadastrados."""
    bot_instancia = bot_global
    chat_id_solicitante = None

    # Identifica se foi chamado por comando manual ou agendamento automático
    if context and hasattr(context, "bot"):
        bot_instancia = context.bot
    elif hasattr(update, "bot"):
        bot_instancia = update.bot

    if update and hasattr(update, "effective_chat") and update.effective_chat:
        chat_id_solicitante = update.effective_chat.id

    agora_br = datetime.now(FUSO_BR)
    str_mes_fatura = agora_br.strftime("%m/%Y")

    try:
        # Se veio do comando /resumo, envia para quem pediu. Senão, para todos do banco.
        if chat_id_solicitante:
            res_users = supabase.table("usuarios").select("id, usuario, telegram_id").eq("telegram_id", chat_id_solicitante).execute()
        else:
            res_users = supabase.table("usuarios").select("id, usuario, telegram_id").not_.is_("telegram_id", "null").execute()
            
        usuarios = res_users.data or []

        if not usuarios and chat_id_solicitante:
            await bot_instancia.send_message(chat_id=chat_id_solicitante, text="⚠️ Usuário não localizado no sistema.")
            return

        for u in usuarios:
            uid = u["id"]
            telegram_id = u["telegram_id"]
            nome = u.get("usuario") or "Cliente"

            # 1. Movimentações do Mês
            res_movs = supabase.table("movimentacoes").select("*").eq("usuario_id", uid).eq("mes_fatura", str_mes_fatura).execute()
            movs = res_movs.data or []

            tot_rec = sum(float(m.get("valor", 0)) for m in movs if m.get("tipo") == "Receita")
            tot_desp = sum(float(m.get("valor", 0)) for m in movs if m.get("tipo") == "Despesa")
            saldo = tot_rec - tot_desp

            # Filtros Específicos
            faturas = [m for m in movs if m.get("forma_pagamento") == "Cartão de Crédito"]
            recorrentes = [m for m in movs if "recorrente" in str(m.get("descricao", "")).lower() or "(recorrente)" in str(m.get("descricao", "")).lower()]

            # 2. Contas a Receber (Boletos)
            ultimo_dia = calendar.monthrange(agora_br.year, agora_br.month)[1]
            data_inicio = f"{agora_br.year}-{agora_br.month:02d}-01"
            data_fim = f"{agora_br.year}-{agora_br.month:02d}-{ultimo_dia:02d}"
            res_rec = supabase.table("contas_receber").select("*").eq("usuario_id", uid).gte("data_recebimento", data_inicio).lte("data_recebimento", data_fim).execute()
            boletos_rec = res_rec.data or []

            # --- MONTAGEM DA MENSAGEM LEVE ---
            msg = f"📊 *Relatório Financeiro - {str_mes_fatura}*\n"
            msg += f"👤 Cliente: *{nome}*\n\n"
            
            msg += f"🟢 *Receitas:* R$ {formatar_moeda(tot_rec)}\n"
            msg += f"🔴 *Despesas:* R$ {formatar_moeda(tot_desp)}\n"
            msg += f"━━━━━━━━━━━━━━━━━━\n"
            msg += f"🔵 *Saldo:* R$ {formatar_moeda(saldo)}\n\n"

            # Faturas de Cartão
            msg += "💳 *FATURAS DE CARTÃO:*\n"
            if faturas:
                for f in faturas:
                    st = "✅ Pago" if f.get("pago") else "⏳ Pendente"
                    msg += f"• {f.get('descricao')} (R$ {formatar_moeda(f.get('valor'))}) — {st}\n"
            else:
                msg += "• Nenhuma fatura neste mês.\n"
            msg += "\n"

            # Boletos / Recebimentos
            msg += "📑 *BOLETOS & RECEBIMENTOS:*\n"
            if boletos_rec:
                for b in boletos_rec:
                    st = "✅ Recebido" if b.get("recebido") else "⏳ Pendente"
                    msg += f"• {b.get('descricao')} (R$ {formatar_moeda(b.get('valor'))}) — {st}\n"
            else:
                msg += "• Nenhum boleto pendente.\n"
            msg += "\n"

            # Gastos Fixos / Recorrentes
            msg += "🔄 *GASTOS FIXOS / RECORRENTES:*\n"
            if recorrentes:
                for r in recorrentes:
                    st = "✅ Pago" if r.get("pago") else "⏳ Pendente"
                    msg += f"• {r.get('descricao')} (R$ {formatar_moeda(r.get('valor'))}) — {st}\n"
            else:
                msg += "• Nenhum gasto recorrente cadastrado.\n"

            # Envio
            try:
                await bot_instancia.send_message(chat_id=telegram_id, text=msg, parse_mode="Markdown")
                logging.info(f"Relatório enviado com sucesso para {nome} ({telegram_id})")
            except Exception as e:
                logging.error(f"Erro no envio para {telegram_id}: {e}")

    except Exception as e:
        logging.error(f"Erro ao gerar relatório mensal: {e}")


if __name__ == "__main__":
    asyncio.run(processar_e_enviar_alertas())