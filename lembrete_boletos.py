import asyncio
import calendar
from datetime import date, datetime, time, timedelta
from dotenv import load_dotenv
import os
import pytz
from supabase import create_client, Client
from telegram import Bot

load_dotenv()

# Configurações do Supabase e Telegram
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Fuso horário do Brasil
fuso_br = pytz.timezone("America/Sao_Paulo")


async def buscar_alertas_vencimento():
    """Busca contas a pagar/receber e investimentos com vencimento/resgate próximo ou hoje."""
    agora_br = datetime.now(fuso_br).date()

    # 1. Alertas de Contas a Pagar / Boletos
    resposta_boletos = (
        supabase.table("contas_pagar")
        .select("*")
        .filter("pago", "eq", False)
        .gte("data_vencimento", agora_br.strftime("%Y-%m-%d"))
        .lte("data_vencimento", (agora_br + timedelta(days=3)).strftime("%Y-%m-%d"))
        .execute()
    )

    alertas_boletos = []
    for item in resposta_boletos.data:
        data_venc = datetime.strptime(item["data_vencimento"], "%Y-%m-%d").date()
        dias_restantes = (data_venc - agora_br).days

        if dias_restantes == 0:
            msg_tempo = "⚠️ *VENCE HOJE!*"
        elif dias_restantes == 1:
            msg_tempo = "⏳ Vence *amanhã*"
        else:
            msg_tempo = f"📅 Vence em *{dias_restantes} dias*"

        alertas_boletos.append(
            f"• *{item['descricao']}*\n"
            f"  💸 Valor: R$ {item['valor']:.2f}\n"
            f"  📆 Vencimento: {data_venc.strftime('%d/%m/%Y')} ({msg_tempo})"
        )

    # 2. Alertas de Contas a Receber
    resposta_receber = (
        supabase.table("contas_receber")
        .select("*")
        .filter("recebido", "eq", False)
        .gte("data_vencimento", agora_br.strftime("%Y-%m-%d"))
        .lte("data_vencimento", (agora_br + timedelta(days=3)).strftime("%Y-%m-%d"))
        .execute()
    )

    alertas_receber = []
    for item in resposta_receber.data:
        data_venc = datetime.strptime(item["data_vencimento"], "%Y-%m-%d").date()
        dias_restantes = (data_venc - agora_br).days

        if dias_restantes == 0:
            msg_tempo = "💰 *RECEBER HOJE!*"
        elif dias_restantes == 1:
            msg_tempo = "⏳ Receber *amanhã*"
        else:
            msg_tempo = f"📅 Receber em *{dias_restantes} dias*"

        alertas_receber.append(
            f"• *{item['descricao']}*\n"
            f"  💵 Valor: R$ {item['valor']:.2f}\n"
            f"  📆 Vencimento: {data_venc.strftime('%d/%m/%Y')} ({msg_tempo})"
        )

    # 3. Alertas de Resgate de Investimentos
    resposta_invest = (
        supabase.table("investimentos")
        .select("*")
        .gte("data_vencimento", agora_br.strftime("%Y-%m-%d"))
        .lte("data_vencimento", (agora_br + timedelta(days=5)).strftime("%Y-%m-%d"))
        .execute()
    )

    alertas_invest = []
    for item in resposta_invest.data:
        data_venc = datetime.strptime(item["data_vencimento"], "%Y-%m-%d").date()
        dias_restantes = (data_venc - agora_br).days

        if dias_restantes == 0:
            msg_tempo = "📈 *RESGATE HOJE!*"
        else:
            msg_tempo = f"📅 Resgate em *{dias_restantes} dias*"

        alertas_invest.append(
            f"• *{item['nome']}* ({item['tipo']})\n"
            f"  🏦 Corretora: {item.get('corretora', 'N/A')}\n"
            f"  💰 Valor Aplicado: R$ {item['valor_aplicado']:.2f}\n"
            f"  📆 Vencimento: {data_venc.strftime('%d/%m/%Y')} ({msg_tempo})"
        )

    return alertas_boletos, alertas_receber, alertas_invest


async def processar_e_enviar_alertas():
    """Formata a mensagem e envia via Telegram."""
    alertas_boletos, alertas_receber, alertas_invest = await buscar_alertas_vencimento()

    if not alertas_boletos and not alertas_receber and not alertas_invest:
        print("Nenhum alerta para enviar hoje.")
        return

    mensagem = "🔔 *LEMBRETE FINANCEIRO DA SEMANA*\n\n"

    if alertas_boletos:
        mensagem += "🔴 *CONTAS A PAGAR*\n" + "\n\n".join(alertas_boletos) + "\n\n"

    if alertas_receber:
        mensagem += "🟢 *CONTAS A RECEBER*\n" + "\n\n".join(alertas_receber) + "\n\n"

    if alertas_invest:
        mensagem += "📈 *INVESTIMENTOS A VENCER*\n" + "\n\n".join(alertas_invest) + "\n\n"

    mensagem += "💡 _Acesse a plataforma para atualizar seus status!_"

    if TELEGRAM_CHAT_ID:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=mensagem,
            parse_mode="Markdown"
        )
        print("Alertas enviados com sucesso via Telegram!")


async def enviar_resumo_mensal_telegram(param1=None, param2=None):
    """
    Gera o resumo de receitas x despesas e pendências do mês.
    Trata argumentos tanto do comando /resumo quanto do agendamento mensal da JobQueue.
    """
    # Identifica a origem da chamada
    context = param1 if hasattr(param1, "bot") else param2
    update = param1 if hasattr(param1, "effective_chat") else None

    # Chat ID seguro
    chat_id = TELEGRAM_CHAT_ID
    if update and update.effective_chat:
        chat_id = update.effective_chat.id

    agora_br = datetime.now(fuso_br).date()
    
    # FIX: Ajustado cálculo do último dia do mês para evitar erros de sintaxe (ex: 31 de fev/abr)
    ultimo_dia = calendar.monthrange(agora_br.year, agora_br.month)[1]
    data_inicio = f"{agora_br.year}-{agora_br.month:02d}-01"
    data_fim = f"{agora_br.year}-{agora_br.month:02d}-{ultimo_dia:02d}"

    # 1. Movimentações registradas no mês
    resp_mov = (
        supabase.table("movimentacoes")
        .select("*")
        .gte("data", data_inicio)
        .lte("data", data_fim)
        .execute()
    )

    total_receitas = sum(item["valor"] for item in resp_mov.data if item["tipo"] == "receita")
    total_despesas = sum(item["valor"] for item in resp_mov.data if item["tipo"] == "despesa")
    saldo_mes = total_receitas - total_despesas

    # 2. Contas a Pagar pendentes do mês
    resp_pagar = (
        supabase.table("contas_pagar")
        .select("*")
        .filter("pago", "eq", False)
        .gte("data_vencimento", data_inicio)
        .lte("data_vencimento", data_fim)
        .execute()
    )
    pendente_pagar = sum(item["valor"] for item in resp_pagar.data)

    # 3. Contas a Receber pendentes do mês
    resp_receber = (
        supabase.table("contas_receber")
        .select("*")
        .filter("recebido", "eq", False)
        .gte("data_vencimento", data_inicio)
        .lte("data_vencimento", data_fim)
        .execute()
    )
    pendente_receber = sum(item["valor"] for item in resp_receber.data)

    nome_mes = agora_br.strftime("%B/%Y")

    msg = (
        f"📊 *RESUMO FINANCEIRO DE {nome_mes.upper()}*\n\n"
        f"🟢 *Entradas:* R$ {total_receitas:,.2f}\n"
        f"🔴 *Saídas:* R$ {total_despesas:,.2f}\n"
        f"💰 *Saldo do Mês:* R$ {saldo_mes:,.2f}\n\n"
        f"📌 *PENDÊNCIAS DO MÊS:*\n"
        f"• Contas a Pagar: R$ {pendente_pagar:,.2f} ({len(resp_pagar.data)} conta(s))\n"
        f"• Contas a Receber: R$ {pendente_receber:,.2f} ({len(resp_receber.data)} conta(s))\n\n"
        f"💡 _Monitore seu orçamento no painel Web!_"
    )

    if context and chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode="Markdown"
        )
    elif TELEGRAM_CHAT_ID:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )


if __name__ == "__main__":
    asyncio.run(processar_e_enviar_alertas())