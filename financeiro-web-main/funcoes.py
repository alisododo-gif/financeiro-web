import requests
import streamlit as st
import re
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Credenciais do Supabase
BASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def criar_tabelas_se_nao_existirem():
    pass

# =====================================================================
# --- FUNÇÕES DE BUSCA E LEITURA OTIMIZADAS (COM CACHE) ---
# =====================================================================

def _construir_query_data(url_base, mes, ano):
    """Auxiliar para aplicar filtros de data direto na query do Supabase."""
    if ano != "Todos":
        if mes != "Todos":
            # Filtro por Mês e Ano específicos
            ano_int = int(ano)
            mes_int = int(mes)
            dt_inicio = f"{ano_int:04d}-{mes_int:02d}-01"
            
            # Trata a virada do ano para a data final
            if mes_int == 12:
                dt_fim = f"{ano_int + 1:04d}-01-01"
            else:
                dt_fim = f"{ano_int:04d}-{mes_int + 1:02d}-01"
                
            return f"{url_base}&data=gte.{dt_inicio}&data=lt.{dt_fim}"
        else:
            # Filtro por Ano completo
            return f"{url_base}&data=gte.{ano}-01-01&data=lt.{int(ano)+1}-01-01"
    return url_base


@st.cache_data(ttl=300)
def buscar_todas_movimentacoes(usuario_id, mes, ano):
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=id,data,tipo,forma_pagamento,descricao,valor,categoria,contas(nome)&order=data.desc"
    url = _construir_query_data(url, mes, ano)
    
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200 or not res.json():
        return []
        
    dados_filtrados = []
    for m in res.json():
        nome_conta = m.get('contas', {}).get('nome') if m.get('contas') else "Conta"
        dados_filtrados.append([
            m.get('id'),
            m.get('data'),
            nome_conta,
            m.get('tipo', ''),
            m.get('forma_pagamento', ''),
            m.get('descricao', ''),
            m.get('valor', 0.0),
            m.get('categoria', '')
        ])
    return dados_filtrados


@st.cache_data(ttl=300)
def dados_dashboard(usuario_id, mes, ano):
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=valor,tipo"
    url = _construir_query_data(url, mes, ano)
    
    res = requests.get(url, headers=HEADERS)
    dados = {"receitas": 0.0, "despesas": 0.0, "saldo": 0.0}
    
    if res.status_code == 200 and res.json():
        for m in res.json():
            val = float(m.get('valor', 0.0))
            if m.get('tipo') == 'Receita':
                dados['receitas'] += val
            else:
                dados['despesas'] += val
                
    dados['saldo'] = dados['receitas'] - dados['despesas']
    return dados


@st.cache_data(ttl=300)
def dados_grafico_mensal(usuario_id, ano):
    meses_rotulos = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    receitas = [0.0] * 12
    despesas = [0.0] * 12
    
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=valor,tipo,data"
    url = _construir_query_data(url, "Todos", ano)
    
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        for m in res.json():
            dt = m.get('data', '')
            if dt and len(dt) >= 7:
                try:
                    mes_idx = int(dt.split('-')[1]) - 1
                    if 0 <= mes_idx < 12:
                        val = float(m.get('valor', 0.0))
                        if m.get('tipo') == 'Receita':
                            receitas[mes_idx] += val
                        elif m.get('tipo') == 'Despesa':
                            despesas[mes_idx] += val
                except (ValueError, IndexError):
                    continue

    return meses_rotulos, receitas, despesas


@st.cache_data(ttl=300)
def dados_grafico_categorias(usuario_id, mes, ano):
    cats = {}
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&tipo=eq.Despesa&select=valor,categoria"
    url = _construir_query_data(url, mes, ano)
    
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        for m in res.json():
            c = m.get('categoria', 'Sem Categoria')
            cats[c] = cats.get(c, 0.0) + float(m.get('valor', 0.0))

    return list(cats.keys()), list(cats.values())


@st.cache_data(ttl=300)
def obter_limite_orcamento(usuario_id):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=limite"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return float(res.json()[0]['limite'])
    return 0.0


@st.cache_data(ttl=300)
def obter_limites_por_categoria(usuario_id):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=categoria,limite"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return {item['categoria']: float(item['limite']) for item in res.json() if item.get('categoria') and item.get('limite')}
    return {}


@st.cache_data(ttl=300)
def listar_contas(usuario_id):
    url = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id,nome,saldo"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return [[c['id'], c['nome'], c.get('saldo', 0.0)] for c in res.json()]
    return []


@st.cache_data(ttl=300)
def listar_metas(usuario_id):
    url = f"{BASE_URL}/metas?usuario_id=eq.{usuario_id}&select=id,nome_meta,valor_alvo,valor_poupado,prazo"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return [[m['id'], m['nome_meta'], m['valor_alvo'], m['valor_poupado'], m['prazo']] for m in res.json()]
    return []


@st.cache_data(ttl=300)
def obter_id_conta_por_nome(usuario_id, nome_conta):
    url = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&nome=eq.{nome_conta}&select=id"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return res.json()[0]['id']
    return None


@st.cache_data(ttl=300)
def nomes_contas(usuario_id):
    return [c[1] for c in listar_contas(usuario_id)]


@st.cache_data(ttl=300)
def listar_todos_usuarios_admin():
    url = f"{BASE_URL}/usuarios?select=id,usuario,role,status,valor_mensalidade,telefone"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []


@st.cache_data(ttl=300)
def listar_cartoes(usuario_id):
    url = f"{BASE_URL}/cartoes?usuario_id=eq.{usuario_id}&select=id,nome_cartao,limite,dia_fechamento,dia_vencimento"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 and res.json() else []


@st.cache_data(ttl=60)
def buscar_gastos_fatura(usuario_id, cartao_id, fatura_ref):
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&cartao_id=eq.{cartao_id}&mes_fatura=eq.{fatura_ref}&select=id,data,descricao,categoria,valor,pago"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []


@st.cache_data(ttl=300)
def obter_transacoes(usuario_id):
    try:
        url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=*,contas(nome)&order=data.desc"
        res = requests.get(url, headers=HEADERS)
        return res.json() if res.status_code == 200 else []
    except Exception as e:
        print(f"Erro ao buscar transações: {e}")
        return []


@st.cache_data(ttl=300)
def buscar_vencimentos_proximos(usuario_id, dias=15):
    hoje = datetime.now().strftime("%Y-%m-%d")
    data_limite = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&tipo=eq.Despesa&and=(data.gte.{hoje},data.lte.{data_limite})&order=data.asc"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []


@st.cache_data(ttl=300)
def dados_grafico_tags(usuario_id, mes_selecionado, ano_selecionado):
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=tags,valor"
    url = _construir_query_data(url, mes_selecionado, ano_selecionado)

    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200 or not res.json():
        return [], []

    agrupado_tags = {}
    for m in res.json():
        raw_tags = m.get("tags")
        if not raw_tags or str(raw_tags).strip() in ["None", "null", ""]:
            continue

        valor = float(m.get("valor", 0))
        tags_lista = [t.strip().lower() for t in str(raw_tags).split(",") if t.strip()]

        for tag_item in tags_lista:
            tag_formatada = f"#{tag_item.lstrip('#')}"
            agrupado_tags[tag_formatada] = agrupado_tags.get(tag_formatada, 0.0) + valor

    return list(agrupado_tags.keys()), list(agrupado_tags.values())


# =====================================================================
# --- FUNÇÕES DE ESCRITA, EDIÇÃO E EXCLUSÃO (INVALIDAM O CACHE) ---
# =====================================================================

def cadastrar_cartao(usuario_id, nome, limite, dia_fechamento, dia_vencimento):
    payload = {
        "usuario_id": int(usuario_id),
        "nome_cartao": str(nome),
        "limite": float(limite),
        "dia_fechamento": int(dia_fechamento),
        "dia_vencimento": int(dia_vencimento)
    }
    res = requests.post(f"{BASE_URL}/cartoes", headers=HEADERS, json=payload)
    if res.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    st.error(f"Erro Supabase ({res.status_code}): {res.text}")
    return False

def excluir_cartao(usuario_id, cartao_id):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def alterar_senha_usuario(usuario_id, nova_senha_hash):
    url = f"{BASE_URL}/usuarios?id=eq.{usuario_id}"
    res = requests.patch(url, headers=HEADERS, json={"senha": nova_senha_hash})
    return res.status_code in [200, 204]

def definir_limite_orcamento(usuario_id, limite):
    url_check = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=id"
    res_check = requests.get(url_check, headers=HEADERS)
    if res_check.status_code == 200 and res_check.json():
        oid = res_check.json()[0]['id']
        requests.patch(f"{BASE_URL}/orcamentos?id=eq.{oid}", headers=HEADERS, json={"limite": limite})
    else:
        requests.post(f"{BASE_URL}/orcamentos", headers=HEADERS, json={"usuario_id": usuario_id, "limite": limite})
    st.cache_data.clear()

def cadastrar_conta(usuario_id, nome, saldo=0.00):
    payload = {"usuario_id": int(usuario_id), "nome": nome, "saldo": float(saldo)}
    res = requests.post(f"{BASE_URL}/contas", headers=HEADERS, json=payload)
    if res.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    return False

def excluir_conta(usuario_id, conta_id):
    res = requests.delete(f"{BASE_URL}/contas?id=eq.{conta_id}&usuario_id=eq.{usuario_id}", headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def criar_meta(usuario_id, nome_meta, valor_alvo, prazo):
    res = requests.post(f"{BASE_URL}/metas", headers=HEADERS, json={"usuario_id": usuario_id, "nome_meta": nome_meta, "valor_alvo": valor_alvo, "valor_poupado": 0.00, "prazo": str(prazo)})
    if res.status_code in [200, 201]:
        st.cache_data.clear()

def atualizar_progresso_meta(meta_id, valor_poupado):
    res = requests.patch(f"{BASE_URL}/metas?id=eq.{meta_id}", headers=HEADERS, json={"valor_poupado": valor_poupado})
    if res.status_code in [200, 204]:
        st.cache_data.clear()

def excluir_meta(usuario_id, meta_id):
    url = f"{BASE_URL}/metas?id=eq.{meta_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def salvar_movimentacao(
    usuario_id, conta_id, descricao, valor, tipo, forma_pagamento, 
    data_str, categoria, cartao_id=None, mes_fatura=None, tags=None
):
    url = f"{BASE_URL}/movimentacoes"
    c_id = int(conta_id) if (conta_id is not None and str(conta_id).isdigit()) else None
    crt_id = int(cartao_id) if (cartao_id is not None and str(cartao_id).isdigit()) else None

    tags_formatadas = None
    if tags:
        if isinstance(tags, list):
            tags_limpas = [f"#{t.strip().lstrip('#')}" for t in tags if str(t).strip()]
            tags_formatadas = ", ".join(tags_limpas) if tags_limpas else None
        elif isinstance(tags, str) and tags.strip():
            tags_separadas = [t.strip() for t in tags.split(",") if t.strip()]
            tags_limpas = [f"#{t.lstrip('#')}" for t in tags_separadas]
            tags_formatadas = ", ".join(tags_limpas) if tags_limpas else None

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
        "mes_fatura": mes_fatura if str(forma_pagamento).strip().lower() == "cartão de crédito" else None,
        "tags": tags_formatadas
    }

    res = requests.post(url, json=payload, headers=HEADERS)
    if res.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    st.error(f"❌ Erro Supabase ({res.status_code}): {res.text}")
    return False

def salvar_movimentacao_parcelada(
    usuario_id, conta_id, descricao, valor, tipo, forma_pagamento, 
    parcelas, data_base, categoria, cartao_id=None, dia_fechamento=None, tags=None
):
    dt_base = datetime.strptime(data_base, "%Y-%m-%d")
    
    # 💡 CORREÇÃO: Divide o valor total pelo número de parcelas
    # (Usamos round para evitar dizimas infinitas com centavos)
    valor_parcela = round(float(valor) / int(parcelas), 2)
    
    for i in range(parcelas):
        ano = dt_base.year + ((dt_base.month + i - 1) // 12)
        mes = ((dt_base.month + i - 1) % 12) + 1
        dia = min(dt_base.day, 28)
        
        data_parcela_str = f"{ano}-{mes:02d}-{dia:02d}"
        desc_parcela = f"{descricao} ({i+1}/{parcelas})"
        
        mes_fatura_calc = None
        if str(forma_pagamento).strip().lower() == "cartão de crédito" and cartao_id and dia_fechamento:
            mes_fatura_calc = calcular_mes_fatura(data_parcela_str, dia_fechamento)
            
        sucesso = salvar_movimentacao(
            usuario_id=usuario_id, 
            conta_id=conta_id, 
            descricao=desc_parcela,
            valor=valor_parcela,  # <--- Agora envia o valor da parcela (ex: 25.00)
            tipo=tipo, 
            forma_pagamento=forma_pagamento,
            data_str=data_parcela_str, 
            categoria=categoria, 
            cartao_id=cartao_id,
            mes_fatura=mes_fatura_calc, 
            tags=tags
        )
        if not sucesso:
            return False
    return True

def salvar_movimentacao_recorrente(
    usuario_id, conta_id, descricao, valor, tipo, forma_pagamento, 
    meses, data_base, categoria, cartao_id=None, dia_fechamento=None, tags=None
):
    dt_base = datetime.strptime(data_base, "%Y-%m-%d")
    for i in range(meses):
        ano = dt_base.year + ((dt_base.month + i - 1) // 12)
        mes = ((dt_base.month + i - 1) % 12) + 1
        dia = min(dt_base.day, 28)
        
        data_recorrente_str = f"{ano}-{mes:02d}-{dia:02d}"
        
        mes_fatura_calc = None
        if str(forma_pagamento).strip().lower() == "cartão de crédito" and cartao_id and dia_fechamento:
            mes_fatura_calc = calcular_mes_fatura(data_recorrente_str, dia_fechamento)
            
        sucesso = salvar_movimentacao(
            usuario_id=usuario_id, conta_id=conta_id, descricao=f"{descricao} (Recorrente)",
            valor=valor, tipo=tipo, forma_pagamento=forma_pagamento,
            data_str=data_recorrente_str, categoria=categoria, cartao_id=cartao_id,
            mes_fatura=mes_fatura_calc, tags=tags
        )
        if not sucesso:
            return False
    return True

def excluir_movimentacao(usuario_id, mov_id):
    url = f"{BASE_URL}/movimentacoes?id=eq.{mov_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    st.error(f"Erro ao excluir ({res.status_code}): {res.text}")
    return False

def atualizar_categoria_e_forma(usuario_id, mov_id, categoria, forma_pagamento):
    res = requests.patch(f"{BASE_URL}/movimentacoes?id=eq.{mov_id}", headers=HEADERS, json={"categoria": categoria, "forma_pagamento": forma_pagamento})
    if res.status_code in [200, 204]:
        st.cache_data.clear()
    return res.status_code in [200, 204]

def excluir_usuario_admin(usuario_id):
    url = f"{BASE_URL}/usuarios?id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def atualizar_status_e_mensalidade(usuario_id, novo_status, novo_valor_mensalidade):
    url = f"{BASE_URL}/usuarios?id=eq.{usuario_id}"
    payload = {"status": novo_status, "valor_mensalidade": float(novo_valor_mensalidade)}
    res = requests.patch(url, headers=HEADERS, json=payload)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def salvar_orcamento_categoria(usuario_id, categoria, valor_limite):
    url = f"{BASE_URL}/orcamentos"
    payload = {"usuario_id": int(usuario_id), "categoria": str(categoria), "limite": float(valor_limite)}
    res = requests.post(url, json=payload, headers=HEADERS)
    if res.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    return False

def excluir_orcamento_categoria(usuario_id, categoria):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&categoria=eq.{categoria}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def alterar_status_pagamento(id_lancamento, status_pago: bool):
    url = f"{BASE_URL}/movimentacoes?id=eq.{id_lancamento}"
    payload = {"pago": status_pago}
    res = requests.patch(url, json=payload, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def marcar_lancamento_como_pago(id_lancamento):
    return alterar_status_pagamento(id_lancamento, True)

def marcar_lancamento_como_pendente(id_lancamento):
    return alterar_status_pagamento(id_lancamento, False)

def excluir_lancamento_pendente(id_lancamento):
    url = f"{BASE_URL}/movimentacoes?id=eq.{id_lancamento}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def desfazer_pagamento_lancamento(id_lancamento):
    return alterar_status_pagamento(id_lancamento, False)

def dar_baixa_fatura_completa(usuario_id, cartao_id, mes_fatura):
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&cartao_id=eq.{cartao_id}&mes_fatura=eq.{mes_fatura}"
    payload = {"pago": True}
    res = requests.patch(url, json=payload, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def atualizar_limite_cartao(usuario_id, cartao_id, novo_limite):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    payload = {"limite": float(novo_limite)}
    res = requests.patch(url, headers=HEADERS, json=payload)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def salvar_despesa_cartao(usuario_id, cartao_id, descricao, valor, categoria, data_str, dia_fechamento, parcelas=1):
    try:
        valor_parcela = float(valor) / int(parcelas)
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date() if isinstance(data_str, str) else data_str

        for i in range(1, int(parcelas) + 1):
            data_parcela = data_obj + relativedelta(months=i - 1)
            mes_fatura = calcular_mes_fatura(data_parcela, dia_fechamento)
            desc_final = f"{descricao} ({i}/{parcelas})" if parcelas > 1 else descricao

            payload = {
                "usuario_id": int(usuario_id),
                "cartao_id": int(cartao_id),
                "descricao": desc_final,
                "valor": round(valor_parcela, 2),
                "tipo": "Despesa",
                "forma_pagamento": "Cartão de Crédito",
                "categoria": categoria,
                "data": data_parcela.strftime("%Y-%m-%d"),
                "mes_fatura": mes_fatura,
                "pago": False
            }
            requests.post(f"{BASE_URL}/movimentacoes", json=payload, headers=HEADERS)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar despesa no cartão: {e}")
        return False


# =====================================================================
# --- FUNÇÕES AUXILIARES E DE INTERFACE ---
# =====================================================================

def calcular_mes_fatura(data_transacao_str, dia_fechamento):
    dt = datetime.strptime(data_transacao_str, "%Y-%m-%d") if isinstance(data_transacao_str, str) else data_transacao_str
    dia_fechamento = int(dia_fechamento)

    if dt.day >= dia_fechamento:
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

def gerar_insights_financeiros(usuario_id, mes_selecionado, ano_selecionado, movimentacoes_raw, metas_raw):
    insights = []
    if not movimentacoes_raw:
        return insights

    df = pd.DataFrame(movimentacoes_raw)
    
    if mes_selecionado != "Todos" and ano_selecionado != "Todos":
        try:
            mes_int, ano_int = int(mes_selecionado), int(ano_selecionado)
            mes_ant_str, ano_ant_str = ("12", str(ano_int - 1)) if mes_int == 1 else (f"{mes_int - 1:02d}", str(ano_int))
                
            prefixo_atual = f"{ano_selecionado}-{mes_selecionado}"
            prefixo_anterior = f"{ano_ant_str}-{mes_ant_str}"

            if "tipo" in df.columns:
                df_despesas = df[df["tipo"].astype(str).str.lower() == "despesa"].copy()
            else:
                df_despesas = pd.DataFrame()

            if not df_despesas.empty and "data" in df_despesas.columns:
                df_atual = df_despesas[df_despesas["data"].astype(str).str.startswith(prefixo_atual)]
                df_ant = df_despesas[df_despesas["data"].astype(str).str.startswith(prefixo_anterior)]

                if not df_atual.empty and not df_ant.empty:
                    cat_atual = df_atual.groupby("categoria")["valor"].sum()
                    cat_ant = df_ant.groupby("categoria")["valor"].sum()

                    for cat, v_atual in cat_atual.items():
                        if cat in cat_ant and cat_ant[cat] > 0:
                            v_ant = cat_ant[cat]
                            variacao = ((v_atual - v_ant) / v_ant) * 100

                            if variacao >= 20:
                                insights.append({
                                    "tipo": "warning", "icone": "⚠️", "titulo": f"Aumento em {cat}",
                                    "texto": f"Seus gastos com **{cat}** aumentaram **{variacao:.0f}%** este mês em relação ao anterior."
                                })
                            elif variacao <= -20:
                                insights.append({
                                    "tipo": "success", "icone": "🎉", "titulo": f"Economia em {cat}",
                                    "texto": f"Ótimo trabalho! Seus gastos com **{cat}** reduziram **{abs(variacao):.0f}%** este mês."
                                })
        except Exception:
            pass

    if metas_raw:
        for m in metas_raw:
            nome_meta, alvo, guardado = m[1], float(m[2]), float(m[3])
            if alvo > 0:
                pct = (guardado / alvo) * 100
                if 85 <= pct < 100:
                    insights.append({"tipo": "success", "icone": "🎯", "titulo": f"Meta {nome_meta}", "texto": f"Você já atingiu **{pct:.0f}%** da sua meta **'{nome_meta}'**!"})
                elif pct >= 100:
                    insights.append({"tipo": "success", "icone": "🏆", "titulo": "Meta Concluída!", "texto": f"Parabéns! Você alcançou **100%** do seu objetivo **'{nome_meta}'**!"})

    if "tipo" in df.columns and "valor" in df.columns:
        tot_rec = df[df["tipo"].astype(str).str.lower() == "receita"]["valor"].sum()
        tot_desp = df[df["tipo"].astype(str).str.lower() == "despesa"]["valor"].sum()

        if tot_rec > 0:
            pct_comprometido = (tot_desp / tot_rec) * 100
            if pct_comprometido >= 85:
                insights.append({"tipo": "error", "icone": "🚨", "titulo": "Alerta de Orçamento", "texto": f"Suas despesas já comprometeram **{pct_comprometido:.0f}%** da sua receita do período."})

    return insights