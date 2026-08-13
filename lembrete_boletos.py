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


def formatar_data_br(data_str):
    """Converte datas no formato YYYY-MM-DD para DD/MM/YYYY."""
    if not data_str:
        return ""
    try:
        partes = str(data_str).split("T")[0].split("-")
        if len(partes) == 3:
            return f"{partes[2]}/{partes[1]}/{partes[0]}"
    except Exception:
        pass
    return str(data_str)


async def enviar_resumo_mensal_telegram(update=None, context=None):
    """Gera o relatório financeiro usando a VIEW otimizada do PostgreSQL."""
    bot_instancia = bot_global
    chat_id_solicitante = None

    if context and hasattr(context, "bot"):
        bot_instancia = context.bot
    elif hasattr(update, "bot"):
        bot_instancia = update.bot

    if update and hasattr(update, "effective_chat") and update.effective_chat:
        chat_id_solicitante = update.effective_chat.id

    agora_br = datetime.now(FUSO_BR)
    str_mes_fatura = agora_br.strftime("%m/%Y")
    prefixo_data_mes = agora_br.strftime("%Y-%m")

    try:
        # Busca usuários
        query_users = supabase.table("usuarios").select("id, usuario, telegram_id")
        if chat_id_solicitante:
            res_users = query_users.eq("telegram_id", chat_id_solicitante).execute()
        else:
            res_users = query_users.not_.is_("telegram_id", "null").execute()

        usuarios = res_users.data or []

        if not usuarios and chat_id_solicitante:
            await bot_instancia.send_message(
                chat_id=chat_id_solicitante, text="⚠️ Usuário não localizado no sistema."
            )
            return

        for u in usuarios:
            uid = u["id"]
            telegram_id = u["telegram_id"]
            nome = u.get("usuario") or "Cliente"

            # 1. Busca os cartões do usuário para mapear os nomes das faturas
            try:
                res_cartoes = (
                    supabase.table("cartoes")
                    .select("id, nome_cartao, dia_vencimento")
                    .eq("usuario_id", uid)
                    .execute()
                )
                mapa_cartoes = {c["id"]: c for c in (res_cartoes.data or [])}
            except Exception as e_c:
                logging.warning(f"Erro ao consultar cartões: {e_c}")
                mapa_cartoes = {}

            # 2. CONSULTA DIRETA NA VIEW (A Mágica de Velocidade acontece aqui!)
            # O PostgreSQL já entrega os registros devidamente classificados em 'tipo_classificado'
            res_movs = (
                supabase.table("vw_lancamentos_categorizados")
                .select("*")
                .eq("usuario_id", uid)
                .or_(f"mes_fatura.eq.{str_mes_fatura},data.like.{prefixo_data_mes}%")
                .order("data")
                .execute()
            )
            movs = res_movs.data or []

            # 3. SEPARAÇÃO SIMPLES POR TIPO_CLASSIFICADO (Sem loops manuais ou regex em Python)
            receitas = [m for m in movs if m.get("tipo") == "Receita"]
            
            # Filtra apenas despesas (entradas já estão em receitas)
            despesas = [m for m in movs if m.get("tipo") != "Receita"]

            pix_debito = [m for m in despesas if m.get("tipo_classificado") == "pix_debito"]
            recorrentes = [m for m in despesas if m.get("tipo_classificado") == "recorrente"]
            cartoes_itens = [m for m in despesas if m.get("tipo_classificado") == "cartao" and m.get("mes_fatura") == str_mes_fatura]
            boletos_pagar = [m for m in despesas if m.get("tipo_classificado") == "outros"]

            # 4. AGRUPANDO FATURAS DE CARTÃO
            faturas_agrupadas = {}
            for item in cartoes_itens:
                cid = item.get("cartao_id")
                desc = str(item.get("descricao", ""))
                nome_cartao = "Cartão de Crédito"
                dia_venc = None

                if cid and cid in mapa_cartoes:
                    nome_cartao = mapa_cartoes[cid].get("nome_cartao") or "Cartão de Crédito"
                    dia_venc = mapa_cartoes[cid].get("dia_vencimento")
                elif " - " in desc:
                    nome_cartao = desc.split(" - ")[-1].split("(")[0].strip()

                data_venc_str = (
                    f"{int(dia_venc):02d}/{agora_br.month:02d}/{agora_br.year}"
                    if dia_venc else formatar_data_br(item.get("data"))
                )

                chave = (nome_cartao, data_venc_str)
                if chave not in faturas_agrupadas:
                    faturas_agrupadas[chave] = {"total": 0.0, "pago": True}

                faturas_agrupadas[chave]["total"] += float(item.get("valor", 0))
                if not item.get("pago", False):
                    faturas_agrupadas[chave]["pago"] = False

            # Contas a receber (Tabela externa)
            ultimo_dia = calendar.monthrange(agora_br.year, agora_br.month)[1]
            try:
                res_rec = (
                    supabase.table("contas_receber")
                    .select("*")
                    .eq("usuario_id", uid)
                    .gte("data_recebimento", f"{agora_br.year}-{agora_br.month:02d}-01")
                    .lte("data_recebimento", f"{agora_br.year}-{agora_br.month:02d}-{ultimo_dia:02d}")
                    .execute()
                )
                boletos_rec = res_rec.data or []
            except Exception:
                boletos_rec = []

            # 5. CÁLCULO DOS TOTAIS
            tot_rec = sum(float(m.get("valor", 0)) for m in receitas) + sum(float(br.get("valor", 0)) for br in boletos_rec)
            tot_cartoes = sum(info["total"] for info in faturas_agrupadas.values())
            tot_pix = sum(float(m.get("valor", 0)) for m in pix_debito)
            tot_boletos = sum(float(m.get("valor", 0)) for m in boletos_pagar)
            tot_recorrentes = sum(float(m.get("valor", 0)) for m in recorrentes)

            tot_desp = tot_cartoes + tot_pix + tot_boletos + tot_recorrentes
            saldo = tot_rec - tot_desp

            # 6. MONTAGEM DA MENSAGEM
            msg = f"📊 *Relatório Financeiro - {str_mes_fatura}*\n"
            msg += f"👤 Cliente: *{nome}*\n\n"
            msg += f"🟢 *Receitas:* R$ {formatar_moeda(tot_rec)}\n"
            msg += f"🔴 *Despesas:* R$ {formatar_moeda(tot_desp)}\n"
            msg += f"━━━━━━━━━━━━━━━━━━\n"
            msg += f"🔵 *Saldo:* R$ {formatar_moeda(saldo)}\n\n"

            # Seções (Receitas, Pix, Cartão, Boletos, Recorrentes)...
            msg += "💵 *RECEITAS / ENTRADAS:*\n"
            if receitas or boletos_rec:
                for r in receitas:
                    msg += f"• `{formatar_data_br(r.get('data'))}` — {r.get('descricao')} | R$ {formatar_moeda(r.get('valor'))}\n"
                for br in boletos_rec:
                    msg += f"• `{formatar_data_br(br.get('data_recebimento'))}` — {br.get('descricao')} | R$ {formatar_moeda(br.get('valor'))}\n"
            else:
                msg += "• Nenhuma receita neste mês.\n"
            msg += "\n"

            msg += "💸 *PIX / DÉBITO / Á VISTA:*\n"
            if pix_debito:
                for p in pix_debito:
                    msg += f"• `{formatar_data_br(p.get('data'))}` — {p.get('descricao')} | R$ {formatar_moeda(p.get('valor'))}\n"
            else:
                msg += "• Nenhum lançamento Pix/Débito neste mês.\n"
            msg += "\n"

            msg += "💳 *FATURAS DE CARTÃO:*\n"
            if faturas_agrupadas:
                for (nome_c, dt_venc), info in faturas_agrupadas.items():
                    st = "✅ Pago" if info["pago"] else "⏳ Pendente"
                    prefixo_dt = f"`{dt_venc}` — " if dt_venc else ""
                    msg += f"• {prefixo_dt}*{nome_c}* | R$ {formatar_moeda(info['total'])} — {st}\n"
            else:
                msg += "• Nenhuma fatura neste mês.\n"
            msg += "\n"

            msg += "📑 *BOLETOS & CONTAS A PAGAR:*\n"
            if boletos_pagar:
                for b in boletos_pagar:
                    st = "✅ Pago" if b.get("pago") else "⏳ Pendente"
                    msg += f"• `{formatar_data_br(b.get('data'))}` — {b.get('descricao')} | R$ {formatar_moeda(b.get('valor'))} — {st}\n"
            else:
                msg += "• Nenhum boleto pendente.\n"
            msg += "\n"

            msg += "🔄 *GASTOS FIXOS / RECORRENTES:*\n"
            if recorrentes:
                for rec in recorrentes:
                    st = "✅ Pago" if rec.get("pago") else "⏳ Pendente"
                    msg += f"• `{formatar_data_br(rec.get('data'))}` — {rec.get('descricao')} | R$ {formatar_moeda(rec.get('valor'))} — {st}\n"
            else:
                msg += "• Nenhum gasto recorrente cadastrado.\n"

            # Envio
            try:
                await bot_instancia.send_message(
                    chat_id=telegram_id, text=msg, parse_mode="Markdown"
                )
                logging.info(f"Relatório enviado com sucesso para {nome} ({telegram_id})")
            except Exception as e:
                logging.error(f"Erro no envio para {telegram_id}: {e}")

    except Exception as e:
        logging.error(f"Erro ao gerar relatório mensal: {e}")