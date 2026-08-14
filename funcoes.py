from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from dateutil.relativedelta import relativedelta
import requests
import streamlit as st
import calendar

# =====================================================================
# --- CONFIGURAÇÃO E CONEXÃO OTIMIZADA (SESSION POOLING) ---
# =====================================================================

BASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]


def obter_sessao_http():
    s = requests.Session()
    s.headers.update({
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    })
    return s


session = obter_sessao_http()
DEFAULT_TIMEOUT = 5  # Timeout global para evitar travamentos
HTTP_TIMEOUT_LONGO = 10  # Para envios/webhooks como Telegram


def buscar_movimentacoes_paginadas(
    usuario_id, mes="Todos", ano="Todos", pagina=1, itens_por_pagina=100
):
    """Busca movimentações no Supabase com paginação server-side e suporte completo a filtros."""
    offset_inicio = (pagina - 1) * itens_por_pagina
    offset_fim = offset_inicio + itens_por_pagina - 1

    url = f"{BASE_URL}/movimentacoes"

    params = [
        ("usuario_id", f"eq.{usuario_id}"),
        ("select", "*,contas(nome)"),
        ("order", "data.desc"),
    ]

    mapa_meses = {
        "Janeiro": 1,
        "Fevereiro": 2,
        "Março": 3,
        "Abril": 4,
        "Maio": 5,
        "Junho": 6,
        "Julho": 7,
        "Agosto": 8,
        "Setembro": 9,
        "Outubro": 10,
        "Novembro": 11,
        "Dezembro": 12,
    }

    try:
        mes_num = (
            mapa_meses.get(mes)
            if mes in mapa_meses
            else (int(mes) if str(mes).isdigit() else None)
        )
        ano_num = int(ano) if str(ano).isdigit() else None

        # 1. Se informou Ano e Mês (ex: 2027 e Julho)
        if ano_num and mes_num:
            _, ultimo_dia = calendar.monthrange(ano_num, mes_num)
            params.append(
                ("data", f"gte.{ano_num:04d}-{mes_num:02d}-01")
            )
            params.append(
                ("data", f"lte.{ano_num:04d}-{mes_num:02d}-{ultimo_dia:02d}")
            )

        # 2. Se informou apenas o Ano (ex: 2027 e Todos)
        elif ano_num:
            params.append(("data", f"gte.{ano_num:04d}-01-01"))
            params.append(("data", f"lte.{ano_num:04d}-12-31"))

        # 3. Se informou apenas o Mês com Ano em 'Todos' (ex: Julho em qualquer ano)
        elif mes_num:
            params.append(("data", f"like.*-{mes_num:02d}-*"))

        # 4. Se ambos forem 'Todos', não insere filtro de data (traz tudo)

        headers = {
            "Range": f"{offset_inicio}-{offset_fim}",
            "Prefer": "count=exact",
        }

        res = session.get(
            url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT
        )

        if res.status_code in [200, 206]:
            dados = res.json()
            content_range = res.headers.get("Content-Range", "")
            total_registros = (
                int(content_range.split("/")[1])
                if "/" in content_range
                else len(dados)
            )
            total_paginas = (
                total_registros + itens_por_pagina - 1
            ) // itens_por_pagina
            return dados, total_registros, max(1, total_paginas)

        return [], 0, 1
    except Exception as e:
        print(f"Erro ao buscar movimentações: {e}")
        return [], 0, 1
# =====================================================================
# --- AJUDANTES DE LIMPEZA CIRÚRGICA DE CACHE ---
# =====================================================================


def limpar_cache_movimentacoes():
    """Invalida apenas as buscas e relatórios de movimentações."""
    obter_df_movimentacoes_bruto.clear()
    buscar_todas_movimentacoes.clear()
    dados_dashboard.clear()
    dados_grafico_mensal.clear()
    dados_grafico_categorias.clear()
    dados_grafico_tags.clear()
    obter_transacoes.clear()
    buscar_vencimentos_proximos.clear()
    buscar_gastos_fatura.clear()


def limpar_cache_contas():
    """Invalida apenas o cache de contas bancárias."""
    listar_contas.clear()
    nomes_contas.clear()
    obter_id_conta_por_nome.clear()


def limpar_cache_cartoes():
    """Invalida apenas o cache de cartões de crédito."""
    listar_cartoes.clear()
    buscar_gastos_fatura.clear()


def limpar_cache_metas():
    """Invalida apenas o cache de metas financeiras."""
    listar_metas.clear()


def limpar_cache_orcamentos():
    """Invalida apenas o cache de orçamentos."""
    obter_limite_orcamento.clear()
    obter_limites_por_categoria.clear()


def limpar_cache_contas_receber():
    """Invalida apenas o cache de contas a receber."""
    buscar_contas_a_receber.clear()


# =====================================================================
# --- FUNÇÕES DE BUSCA E LEITURA OTIMIZADAS (COM CACHE) ---
# =====================================================================


def _construir_query_data(url_base, mes, ano):
    """Auxiliar para aplicar filtros de data/fatura direto no Supabase."""
    if ano != "Todos":
        if mes != "Todos":
            mes_int = int(mes)
            ano_int = int(ano)
            fatura_ref = f"{mes_int:02d}/{ano_int}"

            dt_inicio = f"{ano_int:04d}-{mes_int:02d}-01"
            if mes_int == 12:
                dt_fim = f"{ano_int + 1:04d}-01-01"
            else:
                dt_fim = f"{ano_int:04d}-{mes_int + 1:02d}-01"

            filtro_or = f"or=(and(forma_pagamento.neq.Cartão de Crédito,data.gte.{dt_inicio},data.lt.{dt_fim}),and(forma_pagamento.eq.Cartão de Crédito,mes_fatura.eq.{fatura_ref}))"
            return f"{url_base}&{filtro_or}"
        else:
            return f"{url_base}&data=gte.{ano}-01-01&data=lt.{int(ano)+1}-01-01"

    return url_base


@st.cache_data(ttl=300, show_spinner=False)
def obter_df_movimentacoes_bruto(usuario_id, mes, ano):
    """Função centralizada para buscar movimentações. Evita requisições duplicadas."""
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=id,data,tipo,forma_pagamento,descricao,valor,categoria,tags,pago,contas(nome)&order=data.desc"
    url = _construir_query_data(url, mes, ano)

    try:
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200 and res.json():
            return res.json()
    except Exception as e:
        print(f"Erro ao buscar movimentações brutas: {e}")
    return []


@st.cache_data(ttl=60, show_spinner=False)
def buscar_todas_movimentacoes(usuario_id, mes, ano):
    raw = obter_df_movimentacoes_bruto(usuario_id, mes, ano)
    dados_filtrados = []
    for m in raw:
        nome_conta = (
            m.get("contas", {}).get("nome") if m.get("contas") else "Conta"
        )
        dados_filtrados.append([
            m.get("id"),
            m.get("data"),
            nome_conta,
            m.get("tipo", ""),
            m.get("forma_pagamento", ""),
            m.get("descricao", ""),
            m.get("valor", 0.0),
            m.get("categoria", ""),
        ])
    return dados_filtrados


@st.cache_data(ttl=60, show_spinner=False)
def dados_dashboard(usuario_id, mes, ano):
    raw = obter_df_movimentacoes_bruto(usuario_id, mes, ano)
    dados = {"receitas": 0.0, "despesas": 0.0, "saldo": 0.0}

    for m in raw:
        val = float(m.get("valor", 0.0))
        if m.get("tipo") == "Receita":
            dados["receitas"] += val
        else:
            dados["despesas"] += val

    dados["saldo"] = dados["receitas"] - dados["despesas"]
    return dados


@st.cache_data(ttl=300, show_spinner=False)
def dados_grafico_mensal(usuario_id, ano):
    meses_rotulos = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    receitas = [0.0] * 12
    despesas = [0.0] * 12

    raw = obter_df_movimentacoes_bruto(usuario_id, "Todos", ano)

    for m in raw:
        dt = m.get("data", "")
        if dt and len(dt) >= 7:
            try:
                mes_idx = int(dt.split("-")[1]) - 1
                if 0 <= mes_idx < 12:
                    val = float(m.get("valor", 0.0))
                    if m.get("tipo") == "Receita":
                        receitas[mes_idx] += val
                    elif m.get("tipo") == "Despesa":
                        despesas[mes_idx] += val
            except (ValueError, IndexError):
                continue

    return meses_rotulos, receitas, despesas


@st.cache_data(ttl=300, show_spinner=False)
def dados_grafico_categorias(usuario_id, mes, ano):
    cats = {}
    raw = obter_df_movimentacoes_bruto(usuario_id, mes, ano)

    for m in raw:
        if m.get("tipo") == "Despesa":
            c = m.get("categoria", "Sem Categoria")
            cats[c] = cats.get(c, 0.0) + float(m.get("valor", 0.0))

    return list(cats.keys()), list(cats.values())


@st.cache_data(ttl=300, show_spinner=False)
def dados_grafico_tags(usuario_id, mes_selecionado, ano_selecionado):
    raw = obter_df_movimentacoes_bruto(
        usuario_id, mes_selecionado, ano_selecionado
    )
    agrupado_tags = {}

    for m in raw:
        raw_tags = m.get("tags")
        if not raw_tags or str(raw_tags).strip() in ["None", "null", ""]:
            continue

        valor = float(m.get("valor", 0))
        tags_lista = [
            t.strip().lower() for t in str(raw_tags).split(",") if t.strip()
        ]

        for tag_item in tags_lista:
            tag_formatada = f"#{tag_item.lstrip('#')}"
            agrupado_tags[tag_formatada] = (
                agrupado_tags.get(tag_formatada, 0.0) + valor
            )

    return list(agrupado_tags.keys()), list(agrupado_tags.values())


@st.cache_data(ttl=300, show_spinner=False)
def obter_limite_orcamento(usuario_id):
    try:
        url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=limite"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200 and res.json():
            return float(res.json()[0]["limite"])
    except Exception:
        pass
    return 0.0


@st.cache_data(ttl=300, show_spinner=False)
def obter_limites_por_categoria(usuario_id):
    try:
        url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=categoria,limite"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200 and res.json():
            return {
                item["categoria"]: float(item["limite"])
                for item in res.json()
                if item.get("categoria") and item.get("limite")
            }
    except Exception:
        pass
    return {}


@st.cache_data(ttl=300, show_spinner=False)
def listar_contas(usuario_id):
    try:
        url = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id,nome,saldo"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200 and res.json():
            return [
                [c["id"], c["nome"], c.get("saldo", 0.0)] for c in res.json()
            ]
    except Exception as e:
        print(f"Erro ao listar contas: {e}")
    return []


@st.cache_data(ttl=300, show_spinner=False)
def listar_metas(usuario_id):
    try:
        url = f"{BASE_URL}/metas?usuario_id=eq.{usuario_id}&select=id,nome_meta,valor_alvo,valor_poupado,prazo"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200 and res.json():
            return [
                [
                    m["id"],
                    m["nome_meta"],
                    m["valor_alvo"],
                    m["valor_poupado"],
                    m["prazo"],
                ]
                for m in res.json()
            ]
    except Exception:
        pass
    return []


@st.cache_data(ttl=300, show_spinner=False)
def obter_id_conta_por_nome(usuario_id, nome_conta):
    try:
        url = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&nome=eq.{nome_conta}&select=id"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200 and res.json():
            return res.json()[0]["id"]
    except Exception:
        pass
    return None


@st.cache_data(ttl=300, show_spinner=False)
def nomes_contas(usuario_id):
    return [c[1] for c in listar_contas(usuario_id)]


def listar_todos_usuarios_admin():
    try:
        url = f"{BASE_URL}/usuarios?select=id,usuario,role,status,valor_mensalidade,telefone"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        return res.json() if res.status_code == 200 else []
    except Exception as e:
        print(f"Erro ao listar usuários admin: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def listar_cartoes(usuario_id):
    try:
        url = f"{BASE_URL}/cartoes?usuario_id=eq.{usuario_id}&select=id,nome_cartao,limite,dia_fechamento,dia_vencimento"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        return res.json() if res.status_code == 200 and res.json() else []
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def buscar_gastos_fatura(usuario_id, cartao_id, fatura_ref=None):
    if fatura_ref:
        url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&cartao_id=eq.{cartao_id}&mes_fatura=eq.{fatura_ref}&select=id,data,descricao,categoria,valor,pago"
    else:
        url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&cartao_id=eq.{cartao_id}&select=id,data,descricao,categoria,valor,pago"

    try:
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def obter_transacoes(usuario_id):
    try:
        url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=*,contas(nome)&order=data.desc"
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        return res.json() if res.status_code == 200 else []
    except Exception as e:
        print(f"Erro ao buscar transações: {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def buscar_vencimentos_proximos(usuario_id, dias=60, dias_atras=90):
    data_inicio = (datetime.now() - timedelta(days=dias_atras)).strftime(
        "%Y-%m-%d"
    )
    data_limite = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

    url = (
        f"{BASE_URL}/movimentacoes"
        f"?select=*,cartoes(nome_cartao,dia_vencimento)"
        f"&usuario_id=eq.{usuario_id}"
        f"&tipo=eq.Despesa"
        f"&data=gte.{data_inicio}"
        f"&data=lte.{data_limite}"
        f"&order=data.asc"
    )

    try:
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        if res.status_code == 200:
            dados = res.json()
            for item in dados:
                cartao_obj = item.get("cartoes")
                if isinstance(cartao_obj, dict):
                    item["nome_cartao"] = cartao_obj.get("nome_cartao")
                    item["dia_vencimento_cartao"] = cartao_obj.get(
                        "dia_vencimento"
                    )
                elif isinstance(cartao_obj, list) and len(cartao_obj) > 0:
                    item["nome_cartao"] = cartao_obj[0].get("nome_cartao")
                    item["dia_vencimento_cartao"] = cartao_obj[0].get(
                        "dia_vencimento"
                    )
            return dados
    except Exception:
        pass
    return []


@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_iniciais_paralelo(usuario_id, mes, ano):
    """⚡ CARREGAMENTO EM PARALELO (MULTI-THREADING)

    Executa 4 requisições simultâneas para inicializar a aplicação
    instantaneamente.
    """
    with ThreadPoolExecutor(max_workers=4) as executor:
        f_movs = executor.submit(
            obter_df_movimentacoes_bruto, usuario_id, mes, ano
        )
        f_contas = executor.submit(listar_contas, usuario_id)
        f_cartoes = executor.submit(listar_cartoes, usuario_id)
        f_metas = executor.submit(listar_metas, usuario_id)

    return (
        f_movs.result(),
        f_contas.result(),
        f_cartoes.result(),
        f_metas.result(),
    )


# =====================================================================
# --- FUNÇÕES DE ESCRITA, EDIÇÃO E EXCLUSÃO (BATCH + CIRÚRGICO) ---
# =====================================================================


def cadastrar_cartao(
    usuario_id, nome, limite, dia_fechamento, dia_vencimento
):
    payload = {
        "usuario_id": int(usuario_id),
        "nome_cartao": str(nome),
        "limite": float(limite),
        "dia_fechamento": int(dia_fechamento),
        "dia_vencimento": int(dia_vencimento),
    }
    res = session.post(
        f"{BASE_URL}/cartoes", json=payload, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code in [200, 201]:
        limpar_cache_cartoes()
        return True
    st.error(f"Erro Supabase ({res.status_code}): {res.text}")
    return False


def excluir_cartao(usuario_id, cartao_id):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_cartoes()
        return True
    return False


def alterar_senha_usuario(usuario_id, nova_senha_hash):
    url = f"{BASE_URL}/usuarios?id=eq.{usuario_id}"
    res = session.patch(
        url, json={"senha": nova_senha_hash}, timeout=DEFAULT_TIMEOUT
    )
    return res.status_code in [200, 204]


def definir_limite_orcamento(usuario_id, limite):
    url_check = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=id"
    res_check = session.get(url_check, timeout=DEFAULT_TIMEOUT)
    if res_check.status_code == 200 and res_check.json():
        oid = res_check.json()[0]["id"]
        session.patch(
            f"{BASE_URL}/orcamentos?id=eq.{oid}",
            json={"limite": limite},
            timeout=DEFAULT_TIMEOUT,
        )
    else:
        session.post(
            f"{BASE_URL}/orcamentos",
            json={"usuario_id": usuario_id, "limite": limite},
            timeout=DEFAULT_TIMEOUT,
        )
    limpar_cache_orcamentos()


def cadastrar_conta(usuario_id, nome, saldo=0.00):
    payload = {
        "usuario_id": int(usuario_id),
        "nome": nome,
        "saldo": float(saldo),
    }
    res = session.post(
        f"{BASE_URL}/contas", json=payload, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code in [200, 201]:
        limpar_cache_contas()
        return True
    return False


def excluir_conta(usuario_id, conta_id):
    res = session.delete(
        f"{BASE_URL}/contas?id=eq.{conta_id}&usuario_id=eq.{usuario_id}",
        timeout=DEFAULT_TIMEOUT,
    )
    if res.status_code in [200, 204]:
        limpar_cache_contas()
        return True
    return False


def criar_meta(usuario_id, nome_meta, valor_alvo, prazo):
    res = session.post(
        f"{BASE_URL}/metas",
        json={
            "usuario_id": usuario_id,
            "nome_meta": nome_meta,
            "valor_alvo": valor_alvo,
            "valor_poupado": 0.00,
            "prazo": str(prazo),
        },
        timeout=DEFAULT_TIMEOUT,
    )
    if res.status_code in [200, 201]:
        limpar_cache_metas()


def atualizar_progresso_meta(meta_id, valor_poupado):
    res = session.patch(
        f"{BASE_URL}/metas?id=eq.{meta_id}",
        json={"valor_poupado": valor_poupado},
        timeout=DEFAULT_TIMEOUT,
    )
    if res.status_code in [200, 204]:
        limpar_cache_metas()


def excluir_meta(usuario_id, meta_id):
    url = f"{BASE_URL}/metas?id=eq.{meta_id}&usuario_id=eq.{usuario_id}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_metas()
        return True
    return False


def _formatar_tags(tags):
    if not tags:
        return None
    if isinstance(tags, str):
        tags = tags.split(",")
    if isinstance(tags, (list, tuple)):
        tags_limpas = [
            f"#{str(t).strip().lstrip('#')}" for t in tags if str(t).strip()
        ]
        return ", ".join(tags_limpas) if tags_limpas else None
    return None


def salvar_movimentacao(
    usuario_id,
    conta_id,
    descricao,
    valor,
    tipo,
    forma_pagamento,
    data_str,
    categoria,
    cartao_id=None,
    mes_fatura=None,
    tags=None,
    pago=False,
):
    url = f"{BASE_URL}/movimentacoes"
    c_id = (
        int(conta_id)
        if (conta_id is not None and str(conta_id).isdigit())
        else None
    )
    crt_id = (
        int(cartao_id)
        if (cartao_id is not None and str(cartao_id).isdigit())
        else None
    )

    payload = {
        "usuario_id": int(usuario_id),
        "conta_id": c_id,
        "cartao_id": crt_id,
        "descricao": str(descricao),
        "valor": float(valor),
        "tipo": str(tipo),
        "forma_pagamento": str(forma_pagamento),
        "data": str(data_str),
        "categoria": str(categoria),
        "mes_fatura": (
            mes_fatura
            if str(forma_pagamento).strip().lower() == "cartão de crédito"
            else None
        ),
        "tags": _formatar_tags(tags),
        "pago": pago,
    }

    res = session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 201]:
        limpar_cache_movimentacoes()
        return True

    st.error(f"❌ Erro Supabase ({res.status_code}): {res.text}")
    return False


def salvar_movimentacao_parcelada(
    usuario_id,
    conta_id,
    descricao,
    valor,
    tipo,
    forma_pagamento,
    parcelas,
    data_base,
    categoria,
    cartao_id=None,
    dia_fechamento=None,
    tags=None,
):
    dt_base = datetime.strptime(data_base, "%Y-%m-%d")
    valor_parcela = round(float(valor) / int(parcelas), 2)

    c_id = (
        int(conta_id)
        if (conta_id is not None and str(conta_id).isdigit())
        else None
    )
    crt_id = (
        int(cartao_id)
        if (cartao_id is not None and str(cartao_id).isdigit())
        else None
    )
    tags_fmt = _formatar_tags(tags)

    payloads = []
    for i in range(int(parcelas)):
        ano = dt_base.year + ((dt_base.month + i - 1) // 12)
        mes = ((dt_base.month + i - 1) % 12) + 1
        dia = min(dt_base.day, 28)

        data_parcela_str = f"{ano}-{mes:02d}-{dia:02d}"
        desc_parcela = f"{descricao} ({i+1}/{parcelas})"

        mes_fatura_calc = None
        if (
            str(forma_pagamento).strip().lower() == "cartão de crédito"
            and crt_id
            and dia_fechamento
        ):
            mes_fatura_calc = calcular_mes_fatura(
                data_parcela_str, dia_fechamento
            )

        payloads.append({
            "usuario_id": int(usuario_id),
            "conta_id": c_id,
            "cartao_id": crt_id,
            "descricao": desc_parcela,
            "valor": valor_parcela,
            "tipo": str(tipo),
            "forma_pagamento": str(forma_pagamento),
            "data": data_parcela_str,
            "categoria": str(categoria),
            "mes_fatura": mes_fatura_calc,
            "tags": tags_fmt,
            "pago": False,
        })

    res = session.post(
        f"{BASE_URL}/movimentacoes", json=payloads, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code in [200, 201]:
        limpar_cache_movimentacoes()
        return True
    st.error(f"Erro ao salvar parcelas ({res.status_code}): {res.text}")
    return False


def salvar_movimentacao_recorrente(
    usuario_id,
    conta_id,
    descricao,
    valor,
    tipo,
    forma_pagamento,
    meses,
    data_base,
    categoria,
    cartao_id=None,
    dia_fechamento=None,
    tags=None,
):
    dt_base = datetime.strptime(data_base, "%Y-%m-%d")
    c_id = (
        int(conta_id)
        if (conta_id is not None and str(conta_id).isdigit())
        else None
    )
    crt_id = (
        int(cartao_id)
        if (cartao_id is not None and str(cartao_id).isdigit())
        else None
    )
    tags_fmt = _formatar_tags(tags)

    payloads = []
    for i in range(int(meses)):
        ano = dt_base.year + ((dt_base.month + i - 1) // 12)
        mes = ((dt_base.month + i - 1) % 12) + 1
        dia = min(dt_base.day, 28)

        data_recorrente_str = f"{ano}-{mes:02d}-{dia:02d}"

        mes_fatura_calc = None
        if (
            str(forma_pagamento).strip().lower() == "cartão de crédito"
            and crt_id
            and dia_fechamento
        ):
            mes_fatura_calc = calcular_mes_fatura(
                data_recorrente_str, dia_fechamento
            )

        payloads.append({
            "usuario_id": int(usuario_id),
            "conta_id": c_id,
            "cartao_id": crt_id,
            "descricao": f"{descricao} (Recorrente)",
            "valor": float(valor),
            "tipo": str(tipo),
            "forma_pagamento": str(forma_pagamento),
            "data": data_recorrente_str,
            "categoria": str(categoria),
            "mes_fatura": mes_fatura_calc,
            "tags": tags_fmt,
            "pago": False,
        })

    res = session.post(
        f"{BASE_URL}/movimentacoes", json=payloads, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code in [200, 201]:
        limpar_cache_movimentacoes()
        return True
    st.error(
        f"Erro ao salvar lançamentos recorrentes ({res.status_code}): {res.text}"
    )
    return False


def excluir_movimentacao(usuario_id, mov_id):
    url = f"{BASE_URL}/movimentacoes?id=eq.{mov_id}&usuario_id=eq.{usuario_id}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_movimentacoes()
        return True
    st.error(f"Erro ao excluir ({res.status_code}): {res.text}")
    return False


def atualizar_categoria_e_forma(usuario_id, mov_id, categoria, forma_pagamento):
    res = session.patch(
        f"{BASE_URL}/movimentacoes?id=eq.{mov_id}",
        json={"categoria": categoria, "forma_pagamento": forma_pagamento},
        timeout=DEFAULT_TIMEOUT,
    )
    if res.status_code in [200, 204]:
        limpar_cache_movimentacoes()
    return res.status_code in [200, 204]


def excluir_usuario_admin(usuario_id):
    url = f"{BASE_URL}/usuarios?id=eq.{usuario_id}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        # ❌ Removido: listar_todos_usuarios_admin.clear()
        return True
    return False


def atualizar_status_e_mensalidade(usuario_id, novo_status, novo_valor_mensalidade):
    url = f"{BASE_URL}/usuarios?id=eq.{usuario_id}"
    payload = {
        "status": novo_status,
        "valor_mensalidade": float(novo_valor_mensalidade),
    }
    res = session.patch(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        # ❌ Removido: listar_todos_usuarios_admin.clear()
        return True
    return False


def salvar_orcamento_categoria(usuario_id, categoria, valor_limite):
    url = f"{BASE_URL}/orcamentos"
    payload = {
        "usuario_id": int(usuario_id),
        "categoria": str(categoria),
        "limite": float(valor_limite),
    }
    res = session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 201]:
        limpar_cache_orcamentos()
        return True
    return False


def excluir_orcamento_categoria(usuario_id, categoria):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&categoria=eq.{categoria}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_orcamentos()
        return True
    return False


def alterar_status_pagamento(id_lancamento, status_pago: bool):
    url = f"{BASE_URL}/movimentacoes?id=eq.{id_lancamento}"
    payload = {"pago": status_pago}
    res = session.patch(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_movimentacoes()
        return True
    return False


def marcar_lancamento_como_pago(id_lancamento):
    return alterar_status_pagamento(id_lancamento, True)


def marcar_lancamento_como_pendente(id_lancamento):
    return alterar_status_pagamento(id_lancamento, False)


def excluir_lancamento_pendente(id_lancamento):
    url = f"{BASE_URL}/movimentacoes?id=eq.{id_lancamento}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_movimentacoes()
        return True
    return False


def desfazer_pagamento_lancamento(id_lancamento):
    return alterar_status_pagamento(id_lancamento, False)


def dar_baixa_fatura_completa(usuario_id, cartao_id, mes_fatura):
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&cartao_id=eq.{cartao_id}&mes_fatura=eq.{mes_fatura}"
    payload = {"pago": True}
    res = session.patch(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_movimentacoes()
        return True
    return False


def atualizar_limite_cartao(usuario_id, cartao_id, novo_limite):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    payload = {"limite": float(novo_limite)}
    res = session.patch(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_cartoes()
        return True
    return False


def salvar_despesa_cartao(
    usuario_id,
    cartao_id,
    descricao,
    valor,
    categoria,
    data_str,
    dia_fechamento,
    parcelas=1,
):
    try:
        valor_parcela = round(float(valor) / int(parcelas), 2)
        data_obj = (
            datetime.strptime(data_str, "%Y-%m-%d").date()
            if isinstance(data_str, str)
            else data_str
        )

        payloads = []
        for i in range(1, int(parcelas) + 1):
            data_parcela = data_obj + relativedelta(months=i - 1)
            mes_fatura = calcular_mes_fatura(data_parcela, dia_fechamento)
            desc_final = (
                f"{descricao} ({i}/{parcelas})" if parcelas > 1 else descricao
            )

            payloads.append({
                "usuario_id": int(usuario_id),
                "cartao_id": int(cartao_id),
                "descricao": desc_final,
                "valor": valor_parcela,
                "tipo": "Despesa",
                "forma_pagamento": "Cartão de Crédito",
                "categoria": categoria,
                "data": data_parcela.strftime("%Y-%m-%d"),
                "mes_fatura": mes_fatura,
                "pago": False,
            })

        res = session.post(
            f"{BASE_URL}/movimentacoes", json=payloads, timeout=DEFAULT_TIMEOUT
        )
        if res.status_code in [200, 201]:
            limpar_cache_movimentacoes()
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao salvar despesa no cartão: {e}")
        return False


# =====================================================================
# --- FUNÇÕES AUXILIARES E DE INTERFACE ---
# =====================================================================


def calcular_mes_fatura(data_transacao_str, dia_fechamento):
    dt = (
        datetime.strptime(data_transacao_str, "%Y-%m-%d")
        if isinstance(data_transacao_str, str)
        else data_transacao_str
    )
    dia_fechamento = int(dia_fechamento)

    # 🔧 1. Descobre o número máximo de dias no mês da transação
    max_dias_mes = calendar.monthrange(dt.year, dt.month)[1]

    # 🔧 2. Ajusta o dia de fechamento se o mês tiver menos dias (ex: 30 em Setembro, 28 em Fev)
    dia_fechamento_real = min(dia_fechamento, max_dias_mes)

    # 🔧 3. Compara o dia da compra com o fechamento real do mês
    if dt.day >= dia_fechamento_real:
        ano = dt.year + (1 if dt.month == 12 else 0)
        mes = 1 if dt.month == 12 else dt.month + 1
    else:
        ano = dt.year
        mes = dt.month

    return f"{mes:02d}/{ano}"


def formatar_moeda_ptbr(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def renderizar_interface_central_downloads(usuario_id, mes, ano, ano_padrao):
    pass


def gerar_insights_financeiros(
    usuario_id, mes_selecionado, ano_selecionado, movimentacoes_raw, metas_raw
):
    insights = []
    if not movimentacoes_raw:
        return insights

    if mes_selecionado != "Todos" and ano_selecionado != "Todos":
        try:
            mes_int, ano_int = int(mes_selecionado), int(ano_selecionado)
            mes_ant_str, ano_ant_str = (
                ("12", str(ano_int - 1))
                if mes_int == 1
                else (f"{mes_int - 1:02d}", str(ano_int))
            )

            prefixo_atual = f"{ano_selecionado}-{mes_int:02d}"
            prefixo_anterior = f"{ano_ant_str}-{mes_ant_str}"

            cat_atual = {}
            cat_ant = {}

            for m in movimentacoes_raw:
                tipo = str(m.get("tipo", "")).lower()
                data_str = str(m.get("data", ""))
                if tipo == "despesa":
                    categoria = m.get("categoria") or "Sem Categoria"
                    valor = float(m.get("valor") or 0.0)

                    if data_str.startswith(prefixo_atual):
                        cat_atual[categoria] = (
                            cat_atual.get(categoria, 0.0) + valor
                        )
                    elif data_str.startswith(prefixo_anterior):
                        cat_ant[categoria] = (
                            cat_ant.get(categoria, 0.0) + valor
                        )

            for cat, v_atual in cat_atual.items():
                if cat in cat_ant and cat_ant[cat] > 0:
                    v_ant = cat_ant[cat]
                    variacao = ((v_atual - v_ant) / v_ant) * 100

                    if variacao >= 20:
                        insights.append({
                            "tipo": "warning",
                            "icone": "⚠️",
                            "titulo": f"Aumento em {cat}",
                            "texto": (
                                f"Seus gastos com **{cat}** aumentaram"
                                f" **{variacao:.0f}%** este mês em relação ao"
                                " anterior."
                            ),
                        })
                    elif variacao <= -20:
                        insights.append({
                            "tipo": "success",
                            "icone": "🎉",
                            "titulo": f"Economia em {cat}",
                            "texto": (
                                f"Ótimo trabalho! Seus gastos com **{cat}**"
                                f" reduziram **{abs(variacao):.0f}%** este"
                                " mês."
                            ),
                        })
        except Exception:
            pass

    if metas_raw:
        for m in metas_raw:
            nome_meta, alvo, guardado = m[1], float(m[2]), float(m[3])
            if alvo > 0:
                pct = (guardado / alvo) * 100
                if 85 <= pct < 100:
                    insights.append({
                        "tipo": "success",
                        "icone": "🎯",
                        "titulo": f"Meta {nome_meta}",
                        "texto": (
                            f"Você já atingiu **{pct:.0f}%** da sua meta"
                            f" **'{nome_meta}'**!"
                        ),
                    })
                elif pct >= 100:
                    insights.append({
                        "tipo": "success",
                        "icone": "🏆",
                        "titulo": "Meta Concluída!",
                        "texto": (
                            "Parabéns! Você alcançou **100%** do seu objetivo"
                            f" **'{nome_meta}'**!"
                        ),
                    })

    tot_rec = sum(
        float(m.get("valor") or 0.0)
        for m in movimentacoes_raw
        if str(m.get("tipo", "")).lower() == "receita"
    )
    tot_desp = sum(
        float(m.get("valor") or 0.0)
        for m in movimentacoes_raw
        if str(m.get("tipo", "")).lower() == "despesa"
    )

    if tot_rec > 0:
        pct_comprometido = (tot_desp / tot_rec) * 100
        if pct_comprometido >= 85:
            insights.append({
                "tipo": "error",
                "icone": "🚨",
                "titulo": "Alerta de Orçamento",
                "texto": (
                    "Suas despesas já comprometeram"
                    f" **{pct_comprometido:.0f}%** da sua receita do período."
                ),
            })

    return insights


# =====================================================================
# --- FUNÇÕES PARA A TABELA 'contas_receber' ---
# =====================================================================


@st.cache_data(ttl=60, show_spinner=False)
def buscar_contas_a_receber(usuario_id, status_filtro="Todos"):
    url = f"{BASE_URL}/contas_receber?usuario_id=eq.{usuario_id}&order=data_recebimento.asc"

    if status_filtro == "Pendentes":
        url += "&recebido=eq.false"
    elif status_filtro == "Recebidos":
        url += "&recebido=eq.true"

    try:
        res = session.get(url, timeout=DEFAULT_TIMEOUT)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []


def salvar_conta_a_receber(usuario_id, descricao, valor, data_recebimento):
    url = f"{BASE_URL}/contas_receber"
    payload = {
        "usuario_id": int(usuario_id),
        "descricao": str(descricao),
        "valor": float(valor),
        "data_recebimento": str(data_recebimento),
        "recebido": False,
    }
    res = session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 201]:
        limpar_cache_contas_receber()
        return True
    st.error(f"Erro Supabase ({res.status_code}): {res.text}")
    return False


def alternar_status_contas_a_receber(mov_id, recebido_atual):
    novo_status = not recebido_atual
    url = f"{BASE_URL}/contas_receber?id=eq.{mov_id}"
    res = session.patch(
        url, json={"recebido": novo_status}, timeout=DEFAULT_TIMEOUT
    )
    if res.status_code in [200, 204]:
        limpar_cache_contas_receber()
        return True
    return False


def excluir_conta_a_receber(usuario_id, mov_id):
    url = f"{BASE_URL}/contas_receber?id=eq.{mov_id}&usuario_id=eq.{usuario_id}"
    res = session.delete(url, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_contas_receber()
        return True
    return False


def atualizar_conta_a_receber(
    mov_id, usuario_id, nova_descricao, novo_valor, nova_data
):
    url = f"{BASE_URL}/contas_receber?id=eq.{mov_id}&usuario_id=eq.{usuario_id}"
    payload = {
        "descricao": str(nova_descricao),
        "valor": float(novo_valor),
        "data_recebimento": str(nova_data),
    }
    res = session.patch(url, json=payload, timeout=DEFAULT_TIMEOUT)
    if res.status_code in [200, 204]:
        limpar_cache_contas_receber()
        return True
    st.error(f"Erro ao atualizar: {res.text}")
    return False

def enviar_resumo_completo_telegram(
    chat_id,
    nome_usuario,
    mes_ref,
    ano_ref,
    total_rec,
    total_desp,
    saldo,
    faturas_cartao,
    boletos_receber,
    recorrentes,
):
    """Envia o resumo financeiro completo e leve (sem arquivos) para o Telegram."""
    bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print("Erro: TELEGRAM_BOT_TOKEN não configurado nos secrets.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    rec_fmt = (
        f"R$ {total_rec:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    desp_fmt = (
        f"R$ {total_desp:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    saldo_fmt = (
        f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )

    msg = f"📊 *Resumo Geral - FinanceiroPro*\n"
    msg += f"👤 Cliente: *{nome_usuario}* | Mês: *{mes_ref:02d}/{ano_ref}*\n\n"

    # 💰 RESUMO
    msg += f"🟢 *Receitas:* {rec_fmt}\n"
    msg += f"🔴 *Despesas:* {desp_fmt}\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"🔵 *Saldo:* {saldo_fmt}\n\n"

    # 💳 FATURAS DE CARTÃO
    msg += f"💳 *FATURAS DE CARTÃO:*\n"
    if faturas_cartao:
        for f in faturas_cartao:
            status = "✅ Pago" if f.get("pago") else "⏳ Pendente"
            val = (
                f"R$ {float(f.get('valor', 0)):,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )
            msg += f"• {f.get('descricao', 'Cartão')} ({val}) — {status}\n"
    else:
        msg += "• Nenhuma fatura lançada.\n"
    msg += "\n"

    # 📑 BOLETOS / CONTAS A RECEBER
    msg += f"📑 *BOLETOS & RECEBIMENTOS:*\n"
    if boletos_receber:
        for b in boletos_receber:
            status = "✅ Recebido" if b.get("recebido") else "⏳ Pendente"
            val = (
                f"R$ {float(b.get('valor', 0)):,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )
            msg += f"• {b.get('descricao', 'Boleto')} ({val}) — {status}\n"
    else:
        msg += "• Nenhum boleto a receber.\n"
    msg += "\n"

    # 🔄 FIXOS & RECORRENTES
    msg += f"🔄 *GASTOS FIXOS / RECORRENTES:*\n"
    if recorrentes:
        for r in recorrentes:
            status = "✅ Pago" if r.get("pago") else "⏳ Pendente"
            val = (
                f"R$ {float(r.get('valor', 0)):,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )
            msg += f"• {r.get('descricao', 'Recorrente')} ({val}) — {status}\n"
    else:
        msg += "• Nenhum lançamento recorrente.\n"

    payload = {"chat_id": str(chat_id), "text": msg, "parse_mode": "Markdown"}

    try:
        res = session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        return res.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar no Telegram: {e}")
        return False


def obter_caminho_logo(
    pasta_assets: str = "assets", nome_base: str = "logo"
) -> str | None:
    """Procura pelo arquivo de logo na pasta de assets (com ou sem extensão)

    e retorna o caminho correto, ou None se não encontrar.
    """
    extensoes = ["", ".png", ".jpeg", ".jpg", ".svg", ".webp"]

    for ext in extensoes:
        caminho_teste = os.path.join(pasta_assets, f"{nome_base}{ext}")
        if os.path.exists(caminho_teste):
            return caminho_teste

    return None
    