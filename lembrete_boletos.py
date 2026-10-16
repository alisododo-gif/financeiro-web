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
FUSO_BR = pytz.timezone("America/Cuiaba")


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
        active=supabase.table('usuarios').select('id,telegram_id').eq('status','ativo').execute().data or []
        module='recebimentos' if nome_view.startswith('recebimentos') else 'cartoes' if nome_view.startswith('faturas') else 'vencimentos'
        permitted=[]
        for u in active:
            access=supabase.rpc('fp_access_v1',{'p_usuario':u['id'],'p_modulo':module}).execute().data
            if access.get('allowed'): permitted.append(u)
        links={u['id']:u.get('telegram_id') for u in permitted}
        counts={tid:sum(1 for u in active if u.get('telegram_id')==tid) for tid in links.values() if tid}
        return [r for r in (resposta.data or []) if links.get(r.get('usuario_id')) and links.get(r.get('usuario_id'))==r.get('telegram_id') and counts.get(r.get('telegram_id'))==1]
    except Exception as e:
        logging.error(f"Erro ao consultar {nome_view}: {e}")
        return []


async def processar_e_enviar_alertas(param=None):
    """At most one daily delivery attempt per owner, persisted across restarts."""
    from daily_alerts import build_daily_alerts
    bot_instancia=param.bot if getattr(param,'bot',None) else bot_global
    movements=consultar_view('movimentacoes_hoje')
    invoices=consultar_view('faturas_vencendo_hoje',filtrar_pago=False)
    receivables=[r for r in consultar_view('recebimentos_hoje',filtrar_pago=False) if r.get('recebido') is not True]
    for owner,chat,message in build_daily_alerts(movements,invoices,receivables,datetime.now(FUSO_BR).date()):
        try:
            claimed=supabase.rpc('fp_telegram_daily_claim_v1',{'p_usuario':owner,'p_telegram':chat}).execute().data
            if claimed is not True:
                continue
            await bot_instancia.send_message(chat_id=chat,text=message)
            logging.info('Resumo diário de pendências enviado.')
        except Exception:
            # Keep the reservation on uncertain delivery; never resend automatically.
            logging.error('Falha no resumo diário; sem repetição automática para evitar duplicidade.')


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
    """Gera o relatório financeiro agrupando corretamente Pix, Débito e Boletos."""
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
        if chat_id_solicitante:
            res_users = (
                supabase.table("usuarios")
                .select("id, usuario, telegram_id")
                .eq("telegram_id", chat_id_solicitante)
                .eq("status", "ativo")
                .execute()
            )
        else:
            res_users = (
                supabase.table("usuarios")
                .select("id, usuario, telegram_id")
                .not_.is_("telegram_id", "null")
                .eq("status", "ativo")
                .execute()
            )

        usuarios = res_users.data or []

        if not usuarios and chat_id_solicitante:
            await bot_instancia.send_message(
                chat_id=chat_id_solicitante, text="⚠️ Usuário não localizado no sistema."
            )
            return

        for u in usuarios:
            uid = u["id"]
            access=supabase.rpc('fp_access_v1',{'p_usuario':uid,'p_modulo':'visao_geral'}).execute().data
            if not access.get('allowed'): continue
            telegram_id = u["telegram_id"]
            nome = u.get("usuario") or "Cliente"

            # 1. Busca os cartões do usuário
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

            # 2. Busca movimentações do mês
            res_movs_fatura = (
                supabase.table("movimentacoes")
                .select("*")
                .eq("usuario_id", uid)
                .eq("mes_fatura", str_mes_fatura)
                .execute()
            )
            res_movs_data = (
                supabase.table("movimentacoes")
                .select("*")
                .eq("usuario_id", uid)
                .like("data", f"{prefixo_data_mes}%")
                .execute()
            )

            todos_movs_dict = {
                m["id"]: m for m in (res_movs_fatura.data or []) + (res_movs_data.data or [])
            }
            movs = sorted(todos_movs_dict.values(), key=lambda x: str(x.get("data", "")))

            # --- IDENTIFICAÇÃO DAS CATEGORIAS ---

            # A) RECEITAS / ENTRADAS
            receitas = [m for m in movs if m.get("tipo") == "Receita"]
            ids_receitas = {m["id"] for m in receitas}

            # B) IDENTIFICAÇÃO DE CARTÃO DE CRÉDITO
            def eh_cartao(m):
                desc = str(m.get("descricao", "")).lower()
                forma = str(m.get("forma_pagamento", "")).lower()
                return (
                    m.get("cartao_id") is not None
                    or "cartão" in desc
                    or "cartao" in desc
                    or "fatura" in desc
                    or "anuidade" in desc
                    or forma in ["cartão de crédito", "cartao de credito", "crédito", "credito"]
                )

            # C) RECORRENTES / GASTOS FIXOS
            def eh_recorrente(m):
                desc = str(m.get("descricao", "")).lower()
                tags = str(m.get("tags", "")).lower()
                return (
                    "recorren" in desc
                    or "fixo" in desc
                    or "recorren" in tags
                    or m.get("recorrente") is True
                    or m.get("fixo") is True
                )

            todos_itens_cartao = [m for m in movs if m["id"] not in ids_receitas and eh_cartao(m)]
            ids_todos_cartao = {m["id"] for m in todos_itens_cartao}

            recorrentes = [
                m for m in movs
                if m["id"] not in ids_receitas
                and m["id"] not in ids_todos_cartao
                and eh_recorrente(m)
            ]
            ids_recorrentes = {m["id"] for m in recorrentes}

            # D) PIX / DÉBITO / Á VISTA
            def eh_pix_debito(m):
                forma = str(m.get("forma_pagamento", "")).lower()
                desc = str(m.get("descricao", "")).lower()
                return (
                    forma in ["pix", "débito", "debito", "dinheiro", "à vista", "a vista"]
                    or "pix" in desc
                    or "débito" in desc
                    or "debito" in desc
                )

            pix_debito = [
                m for m in movs
                if m["id"] not in ids_receitas
                and m["id"] not in ids_todos_cartao
                and m["id"] not in ids_recorrentes
                and eh_pix_debito(m)
                and str(m.get("data", "")).startswith(prefixo_data_mes)
            ]
            ids_pix_debito = {m["id"] for m in pix_debito}

            # E) BOLETOS & CONTAS A PAGAR (O restante das despesas do mês)
            boletos_pagar = [
                m for m in movs
                if m["id"] not in ids_receitas
                and m["id"] not in ids_todos_cartao
                and m["id"] not in ids_recorrentes
                and m["id"] not in ids_pix_debito
                and str(m.get("data", "")).startswith(prefixo_data_mes)
            ]

            # Cartão restrito estritamente ao mês da fatura atual
            itens_cartao_mes_atual = [
                m for m in todos_itens_cartao
                if m.get("mes_fatura") == str_mes_fatura
            ]

            # AGRUPANDO FATURAS POR CARTÃO
            faturas_agrupadas = {}
            for item in itens_cartao_mes_atual:
                cid = item.get("cartao_id")
                desc = str(item.get("descricao", ""))

                nome_cartao = "Cartão de Crédito"
                dia_venc = None

                if cid and cid in mapa_cartoes:
                    info_c = mapa_cartoes[cid]
                    nome_cartao = info_c.get("nome_cartao") or "Cartão de Crédito"
                    dia_venc = info_c.get("dia_vencimento")
                elif " - " in desc:
                    nome_cartao = desc.split(" - ")[-1].split("(")[0].strip()

                if dia_venc:
                    data_venc_str = f"{int(dia_venc):02d}/{agora_br.month:02d}/{agora_br.year}"
                else:
                    data_venc_str = formatar_data_br(item.get("data"))

                val = float(item.get("valor", 0))
                pago = bool(item.get("pago", False))

                chave = (nome_cartao, data_venc_str)
                if chave not in faturas_agrupadas:
                    faturas_agrupadas[chave] = {"total": 0.0, "pago": True}

                faturas_agrupadas[chave]["total"] += val
                if not pago:
                    faturas_agrupadas[chave]["pago"] = False

            # CÁLCULO DOS TOTAIS
            tot_rec = sum(float(m.get("valor", 0)) for m in receitas)
            tot_cartoes = sum(info["total"] for info in faturas_agrupadas.values())
            tot_pix = sum(float(m.get("valor", 0)) for m in pix_debito)
            tot_boletos = sum(float(m.get("valor", 0)) for m in boletos_pagar)
            tot_recorrentes = sum(float(m.get("valor", 0)) for m in recorrentes)

            tot_desp = tot_cartoes + tot_pix + tot_boletos + tot_recorrentes
            saldo = tot_rec - tot_desp

            # --- MONTAGEM DA MENSAGEM FINAL ---
            msg = f"📊 *Relatório Financeiro - {str_mes_fatura}*\n"
            msg += f"👤 Cliente: *{nome}*\n\n"

            msg += f"🟢 *Receitas:* R$ {formatar_moeda(tot_rec)}\n"
            msg += f"🔴 *Despesas:* R$ {formatar_moeda(tot_desp)}\n"
            msg += f"━━━━━━━━━━━━━━━━━━\n"
            msg += f"🔵 *Saldo:* R$ {formatar_moeda(saldo)}\n\n"

            # 1. RECEITAS / ENTRADAS
            msg += "💵 *RECEITAS / ENTRADAS:*\n"
            if receitas:
                for r in receitas:
                    dt = formatar_data_br(r.get("data"))
                    msg += f"• `{dt}` — {r.get('descricao')} | R$ {formatar_moeda(r.get('valor'))}\n"
            else:
                msg += "• Nenhuma receita neste mês.\n"
            msg += "\n"

            # 2. PIX / DÉBITO / Á VISTA
            msg += "💸 *PIX / DÉBITO / Á VISTA:*\n"
            if pix_debito:
                for p in pix_debito:
                    dt = formatar_data_br(p.get("data"))
                    msg += f"• `{dt}` — {p.get('descricao')} | R$ {formatar_moeda(p.get('valor'))}\n"
            else:
                msg += "• Nenhum lançamento Pix/Débito neste mês.\n"
            msg += "\n"

            # 3. FATURAS DE CARTÃO DE CRÉDITO
            msg += "💳 *FATURAS DE CARTÃO:*\n"
            if faturas_agrupadas:
                for (nome_c, dt_venc), info in faturas_agrupadas.items():
                    st = "✅ Pago" if info["pago"] else "⏳ Pendente"
                    prefixo_dt = f"`{dt_venc}` — " if dt_venc else ""
                    msg += f"• {prefixo_dt}*{nome_c}* | R$ {formatar_moeda(info['total'])} — {st}\n"
            else:
                msg += "• Nenhuma fatura neste mês.\n"
            msg += "\n"

            # 4. BOLETOS & CONTAS A PAGAR
            msg += "📑 *BOLETOS & CONTAS A PAGAR:*\n"
            if boletos_pagar:
                for b in boletos_pagar:
                    dt = formatar_data_br(b.get("data"))
                    st = "✅ Pago" if b.get("pago") else "⏳ Pendente"
                    msg += f"• `{dt}` — {b.get('descricao')} | R$ {formatar_moeda(b.get('valor'))} — {st}\n"
            else:
                msg += "• Nenhum boleto pendente.\n"
            msg += "\n"

            # 5. GASTOS FIXOS / RECORRENTES
            msg += "🔄 *GASTOS FIXOS / RECORRENTES:*\n"
            if recorrentes:
                for rec in recorrentes:
                    dt = formatar_data_br(rec.get("data"))
                    st = "✅ Pago" if rec.get("pago") else "⏳ Pendente"
                    msg += f"• `{dt}` — {rec.get('descricao')} | R$ {formatar_moeda(rec.get('valor'))} — {st}\n"
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
