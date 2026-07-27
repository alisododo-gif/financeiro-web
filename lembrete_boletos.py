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


def formatar_moeda(valor) -> str:
    """Auxiliar para formatar valores no padrão R$ 0.000,00."""
    try:
        valor_num = float(valor)
        return f"{valor_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(valor)


def extrair_nome_usuario(dados: dict) -> str:
    """Extrai o nome do usuário tratando None ou valores vazios."""
    nome = dados.get("usuario") or dados.get("nome_usuario") or dados.get("nome")
    return nome if nome else "Cliente"


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
    """Busca dados nas views (hoje, amanhã e faturas de cartão) e envia mensagens."""
    chat_id_solicitante = None

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
                await bot.send_message(
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
                await bot.send_message(
                    chat_id=telegram_id, text=mensagem, parse_mode="Markdown"
                )
                logging.info(
                    f"Aviso de Fatura enviado para {nome_usuario} ({telegram_id}) - Cartão: {nome_cartao}"
                )
            except Exception as e:
                logging.error(
                    f"Falha ao enviar aviso de Fatura para {telegram_id}: {e}"
                )


if __name__ == "__main__":
    asyncio.run(processar_e_enviar_alertas())