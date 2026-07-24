import asyncio
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

bot = Bot(token=TELEGRAM_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fuso horário oficial do Brasil
FUSO_BR = pytz.timezone("America/Sao_Paulo")


def consultar_view(nome_view: str):
    """Consulta os lançamentos não pagos diretamente da view do Supabase."""
    try:
        resposta = (
            supabase.table(nome_view).select("*").eq("pago", False).execute()
        )
        return resposta.data or []
    except Exception as e:
        logging.error(f"Erro ao consultar {nome_view}: {e}")
        return []


async def processar_e_enviar_alertas():
    """Busca dados nas views (hoje e amanhã) e envia as mensagens formatadas individualmente."""
    agora_br = datetime.now(FUSO_BR)
    hoje_str = agora_br.strftime("%d/%m/%Y")
    amanha_str = (agora_br + timedelta(days=1)).strftime("%d/%m/%Y")

    # =========================================================
    # 1. LEITURA E ENVIO DOS LANÇAMENTOS DE HOJE
    # =========================================================
    boletos_hoje = consultar_view("lancamentos_hoje")

    for boleto in boletos_hoje:
        # Pega os dados diretamente do registro da view
        telegram_id = boleto.get("telegram_id")
        nome_usuario = boleto.get("nome") or boleto.get("nome_usuario", "Cliente")

        if telegram_id:
            descricao = boleto.get("descricao", "Sem descrição")
            valor = boleto.get("valor", 0.0)

            valor_formatado = (
                f"{valor:g}" if isinstance(valor, (int, float)) else str(valor)
            )

            mensagem = (
                f"Olá! *{nome_usuario}* Espero que esteja tendo um ótimo dia. 😊\n\n"
                f"Lembrete rápido sobre o seu lançamento que vence na data de hoje !\n\n"
                f"*📆 Data: {hoje_str}*\n"
                f"*📄 Descrição: {descricao}*\n"
                f"*💰 Valor: R$ {valor_formatado}*\n\n"
                f"Se já realizou o pagamento, pode desconsiderar esta mensagem.\n\n"
                f"*FinanceiroPro Web Agradece a Parceria🫡*"
            )

            try:
                await bot.send_message(
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

    for boleto in boletos_amanha:
        telegram_id = boleto.get("telegram_id")
        nome_usuario = boleto.get("nome") or boleto.get("nome_usuario", "Cliente")

        if telegram_id:
            descricao = boleto.get("descricao", "Sem descrição")
            valor = boleto.get("valor", 0.0)

            valor_formatado = (
                f"{valor:g}" if isinstance(valor, (int, float)) else str(valor)
            )

            mensagem = (
                f"Olá! *{nome_usuario}* Espero que esteja tendo um ótimo dia. 😊\n\n"
                f"Lembrete rápido sobre o seu lançamento que vence amanhã !\n\n"
                f"*📆 Data: {amanha_str}*\n"
                f"*📄 Descrição: {descricao}*\n"
                f"*💰 Valor: R$ {valor_formatado}*\n\n"
                f"Se já realizou o pagamento, pode desconsiderar esta mensagem.\n\n"
                f"*FinanceiroPro Web Agradece a Parceria🫡*"
            )

            try:
                await bot.send_message(
                    chat_id=telegram_id, text=mensagem, parse_mode="Markdown"
                )
                logging.info(
                    f"Aviso de AMANHÃ enviado com sucesso para {nome_usuario} ({telegram_id})"
                )
            except Exception as e:
                logging.error(
                    f"Falha ao enviar mensagem de AMANHÃ para {telegram_id}: {e}"
                )


if __name__ == "__main__":
    asyncio.run(processar_e_enviar_alertas())