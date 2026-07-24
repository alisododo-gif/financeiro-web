import requests
import streamlit as st
import re
import pandas as pd

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


# Puxando as credenciais de forma segura do .streamlit/secrets.toml
BASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def criar_tabelas_se_nao_existirem():
    """Mantido por compatibilidade de importação no app_web.py"""
    pass


# =====================================================================
# --- FUNÇÕES DE BUSCA / LEITURA (COM CACHE PARA VELOCIDADE NAS ABAS) ---
# =====================================================================

@st.cache_data(ttl=60)
def buscar_todas_movimentacoes(usuario_id, mes, ano):
    url_contas = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id,nome"
    res_contas = requests.get(url_contas, headers=HEADERS)
    if res_contas.status_code != 200 or not res_contas.json():
        return []
    
    contas_dict = {c['id']: c['nome'] for c in res_contas.json()}
    if not contas_dict:
        return []
        
    ids_filtro = f"({','.join([str(cid) for cid in contas_dict.keys()])})"
    url_movs = f"{BASE_URL}/movimentacoes?conta_id=in.{ids_filtro}&order=data.desc&select=id,data,tipo,forma_pagamento,descricao,valor,categoria,conta_id"
    res_movs = requests.get(url_movs, headers=HEADERS)
    
    dados_filtrados = []
    if res_movs.status_code == 200 and res_movs.json():
        for m in res_movs.json():
            dt = m.get('data', '')
            partes = dt.replace('/', '-').split('-')
            
            ano_dt, mes_dt = "", ""
            if len(partes) == 3:
                if len(partes[0]) == 4:  # YYYY-MM-DD
                    ano_dt = partes[0]
                    mes_dt = partes[1]
                elif len(partes[2]) == 4:  # DD-MM-YYYY
                    ano_dt = partes[2]
                    mes_dt = partes[1]

            if (mes == "Todos" or mes_dt == mes) and (ano == "Todos" or ano_dt == ano):
                dados_filtrados.append([
                    m.get('id'), 
                    m.get('data'), 
                    contas_dict.get(m.get('conta_id'), "Conta"), 
                    m.get('tipo', ''), 
                    m.get('forma_pagamento', ''), 
                    m.get('descricao', ''), 
                    m.get('valor', 0.0), 
                    m.get('categoria', '')
                ])
                
    return dados_filtrados

@st.cache_data(ttl=60)
def dados_dashboard(usuario_id, mes, ano):
    url_contas = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id"
    res_contas = requests.get(url_contas, headers=HEADERS)
    
    dados = {"receitas": 0.0, "despesas": 0.0, "saldo": 0.0}
    if res_contas.status_code != 200 or not res_contas.json():
        return dados
        
    ids = [str(c['id']) for c in res_contas.json()]
    if not ids:
        return dados
    ids_filtro = f"({','.join(ids)})"
    
    url_movs = f"{BASE_URL}/movimentacoes?conta_id=in.{ids_filtro}&select=valor,tipo,data"
    res_movs = requests.get(url_movs, headers=HEADERS)
    
    if res_movs.status_code == 200 and res_movs.json():
        for m in res_movs.json():
            dt = m.get('data', '')
            partes = dt.replace('/', '-').split('-')
            ano_dt, mes_dt = "", ""
            
            if len(partes) == 3:
                if len(partes[0]) == 4:
                    ano_dt = partes[0]
                    mes_dt = partes[1]
                elif len(partes[2]) == 4:
                    ano_dt = partes[2]
                    mes_dt = partes[1]

            if (mes == "Todos" or mes_dt == mes) and (ano == "Todos" or ano_dt == ano):
                val = float(m.get('valor', 0.0))
                if m.get('tipo') == 'Receita':
                    dados['receitas'] += val
                else:
                    dados['despesas'] += val
                    
    dados['saldo'] = dados['receitas'] - dados['despesas']
    return dados

@st.cache_data(ttl=60)
def dados_grafico_mensal(usuario_id, ano):
    meses_rotulos = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    receitas = [0.0] * 12
    despesas = [0.0] * 12
    
    url_contas = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id"
    res_contas = requests.get(url_contas, headers=HEADERS)
    if res_contas.status_code != 200 or not res_contas.json():
        return meses_rotulos, receitas, despesas

    ids = [str(c['id']) for c in res_contas.json()]
    if not ids:
        return meses_rotulos, receitas, despesas
        
    ids_filtro = f"({','.join(ids)})"
    url_movs = f"{BASE_URL}/movimentacoes?conta_id=in.{ids_filtro}&select=valor,tipo,data"
    res_movs = requests.get(url_movs, headers=HEADERS)

    if res_movs.status_code == 200 and res_movs.json():
        for m in res_movs.json():
            dt = m.get('data', '')
            partes = dt.replace('/', '-').split('-')
            
            ano_dt, mes_dt = "", ""
            if len(partes) == 3:
                if len(partes[0]) == 4:
                    ano_dt = partes[0]
                    mes_dt = partes[1]
                elif len(partes[2]) == 4:
                    ano_dt = partes[2]
                    mes_dt = partes[1]

            if dt and (ano == "Todos" or ano_dt == ano):
                try:
                    m_idx = int(mes_dt) - 1
                    if 0 <= m_idx < 12:
                        val = float(m.get('valor', 0.0))
                        if m.get('tipo') == 'Receita':
                            receitas[m_idx] += val
                        elif m.get('tipo') == 'Despesa':
                            despesas[m_idx] += val
                except (ValueError, TypeError):
                    continue

    return meses_rotulos, receitas, despesas

@st.cache_data(ttl=60)
def dados_grafico_categorias(usuario_id, mes, ano):
    cats = {}
    url_contas = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id"
    res_contas = requests.get(url_contas, headers=HEADERS)
    if res_contas.status_code != 200 or not res_contas.json():
        return [], []

    ids = [str(c['id']) for c in res_contas.json()]
    if not ids:
        return [], []

    ids_filtro = f"({','.join(ids)})"
    url_movs = f"{BASE_URL}/movimentacoes?conta_id=in.{ids_filtro}&tipo=eq.Despesa&select=valor,categoria,data"
    res_movs = requests.get(url_movs, headers=HEADERS)

    if res_movs.status_code == 200 and res_movs.json():
        for m in res_movs.json():
            dt = m.get('data', '')
            partes = dt.replace('/', '-').split('-')
            
            ano_dt, mes_dt = "", ""
            if len(partes) == 3:
                if len(partes[0]) == 4:
                    ano_dt = partes[0]
                    mes_dt = partes[1]
                elif len(partes[2]) == 4:
                    ano_dt = partes[2]
                    mes_dt = partes[1]

            if (mes == "Todos" or mes_dt == mes) and (ano == "Todos" or ano_dt == ano):
                c = m.get('categoria', 'Sem Categoria')
                val = float(m.get('valor', 0.0))
                cats[c] = cats.get(c, 0.0) + val

    return list(cats.keys()), list(cats.values())

@st.cache_data(ttl=60)
def obter_limite_orcamento(usuario_id):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=limite"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return float(res.json()[0]['limite'])
    return 0.0

def obter_limites_por_categoria(usuario_id):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&select=categoria,limite"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return {item['categoria']: float(item['limite']) for item in res.json() if item.get('categoria') and item.get('limite')}
    return {}

@st.cache_data(ttl=60)
def listar_contas(usuario_id):
    url = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&select=id,nome,saldo"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return [[c['id'], c['nome'], c.get('saldo', 0.0)] for c in res.json()]
    return []

@st.cache_data(ttl=60)
def listar_metas(usuario_id):
    url = f"{BASE_URL}/metas?usuario_id=eq.{usuario_id}&select=id,nome_meta,valor_alvo,valor_poupado,prazo"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return [[m['id'], m['nome_meta'], m['valor_alvo'], m['valor_poupado'], m['prazo']] for m in res.json()]
    return []

@st.cache_data(ttl=60)
def obter_id_conta_por_nome(usuario_id, nome_conta):
    url = f"{BASE_URL}/contas?usuario_id=eq.{usuario_id}&nome=eq.{nome_conta}&select=id"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return res.json()[0]['id']
    return None

@st.cache_data(ttl=60)
def nomes_contas(usuario_id):
    return [c[1] for c in listar_contas(usuario_id)]

@st.cache_data(ttl=60)
def listar_todos_usuarios_admin():
    url = f"{BASE_URL}/usuarios?select=id,usuario,role,status,valor_mensalidade,telefone"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    return []

# --- MÓDULO DE CARTÕES DE CRÉDITO ---

@st.cache_data(ttl=60)
def listar_cartoes(usuario_id):
    url = f"{BASE_URL}/cartoes?usuario_id=eq.{usuario_id}&select=id,nome_cartao,limite,dia_fechamento,dia_vencimento"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and res.json():
        return res.json()
    return []

def cadastrar_cartao(usuario_id, nome, limite, dia_fechamento, dia_vencimento):
    payload = {
        "usuario_id": int(usuario_id),
        "nome_cartao": str(nome),  # Mapeado exatamente como está no Supabase
        "limite": float(limite),
        "dia_fechamento": int(dia_fechamento),
        "dia_vencimento": int(dia_vencimento)
    }
    res = requests.post(f"{BASE_URL}/cartoes", headers=HEADERS, json=payload)
    
    if res.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    else:
        # Exibe o erro exato do Supabase na tela para facilitar o diagnóstico
        st.error(f"Erro Supabase ({res.status_code}): {res.text}")
        return False

def excluir_cartao(usuario_id, cartao_id):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False


# =====================================================================
# --- FUNÇÕES DE ESCRITA / EVENTOS ---
# =====================================================================

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
    tags=None
):
    url = f"{BASE_URL}/movimentacoes"
    
    # Validação e conversão de IDs
    c_id = int(conta_id) if (conta_id is not None and str(conta_id).isdigit()) else None
    crt_id = int(cartao_id) if (cartao_id is not None and str(cartao_id).isdigit()) else None

    # Normalização robusta de Tags
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
    else:
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
    tags=None
):
    dt_base = datetime.strptime(data_base, "%Y-%m-%d")
    
    for i in range(parcelas):
        # Avança 1 mês por parcela
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
            valor=valor,
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
    tags=None
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
            usuario_id=usuario_id,
            conta_id=conta_id,
            descricao=f"{descricao} (Recorrente)",
            valor=valor,
            tipo=tipo,
            forma_pagamento=forma_pagamento,
            data_str=data_recorrente_str,
            categoria=categoria,
            cartao_id=cartao_id,
            mes_fatura=mes_fatura_calc,
            tags=tags
        )
        if not sucesso:
            return False
            
    return True

def excluir_movimentacao(usuario_id, mov_id):
    """
    Exclui um lançamento da tabela movimentacoes filtrando por ID e Usuário.
    """
    url = f"{BASE_URL}/movimentacoes?id=eq.{mov_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    else:
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
    payload = {
        "status": novo_status,
        "valor_mensalidade": float(novo_valor_mensalidade)
    }
    res = requests.patch(url, headers=HEADERS, json=payload)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False


# =====================================================================
# --- FORMATADORES / VISUAIS ---
# =====================================================================

def formatar_moeda_ptbr(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def renderizar_interface_central_downloads(usuario_id, mes, ano, ano_padrao):
    """Mantido por compatibilidade de importação no app_web.py"""
    pass

def obter_transacoes(usuario_id):
    try:
        url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&select=*,contas(nome)&order=data.desc"
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return res.json()
        return []
    except Exception as e:
        print(f"Erro ao buscar transações: {e}")
        return []
    
def excluir_meta(usuario_id, meta_id):
    url = f"{BASE_URL}/metas?id=eq.{meta_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False    

def buscar_vencimentos_proximos(usuario_id, dias=15):
    hoje = datetime.now().strftime("%Y-%m-%d")
    data_limite = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    url = (
        f"{BASE_URL}/movimentacoes?"
        f"usuario_id=eq.{usuario_id}"
        f"&tipo=eq.Despesa"
        f"&and=(data.gte.{hoje},data.lte.{data_limite})"
        f"&order=data.asc"
    )
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    return []

def salvar_orcamento_categoria(usuario_id, categoria, valor_limite):
    url = f"{BASE_URL}/orcamentos"
    payload = {
        "usuario_id": int(usuario_id),
        "categoria": str(categoria),
        "limite": float(valor_limite)
    }
    headers = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
    res = requests.post(url, json=payload, headers=headers)
    if res.status_code in [200, 201]:
        return True
    res_fallback = requests.post(url, json=payload, headers=HEADERS)
    return res_fallback.status_code in [200, 201]

def excluir_orcamento_categoria(usuario_id, categoria):
    url = f"{BASE_URL}/orcamentos?usuario_id=eq.{usuario_id}&categoria=eq.{categoria}"
    res = requests.delete(url, headers=HEADERS)
    return res.status_code in [200, 204]

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

# =====================================================================
# --- MÓDULO DE CARTÕES DE CRÉDITO & FATURAS ---
# =====================================================================

# 1. Função de Cálculo do Mês da Fatura (padrão MM/YYYY)
def calcular_mes_fatura(data_transacao_str, dia_fechamento):
    """
    Calcula o mês/ano da fatura (retorna sempre no formato MM/YYYY, ex: '08/2026').
    """
    if isinstance(data_transacao_str, str):
        dt = datetime.strptime(data_transacao_str, "%Y-%m-%d")
    else:
        dt = data_transacao_str

    dia_fechamento = int(dia_fechamento)

    # Se a compra for realizada no dia do fechamento ou após, cai na fatura do mês seguinte
    if dt.day >= dia_fechamento:
        ano = dt.year + (1 if dt.month == 12 else 0)
        mes = 1 if dt.month == 12 else dt.month + 1
    else:
        ano = dt.year
        mes = dt.month

    return f"{mes:02d}/{ano}"


def salvar_despesa_cartao(usuario_id, cartao_id, descricao, valor, categoria, data_str, dia_fechamento, parcelas=1):
    """
    Lança despesas no cartão de crédito dividindo em parcelas e vinculando às faturas corretas.
    """
    try:
        valor_parcela = float(valor) / int(parcelas)
        if isinstance(data_str, str):
            data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
        else:
            data_obj = data_str

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

            res = requests.post(f"{BASE_URL}/movimentacoes", json=payload, headers=HEADERS)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar despesa no cartão: {e}")
        return False

# =====================================================================
# --- BUSCA DE FATURAS DE CARTÃO ---
# =====================================================================

@st.cache_data(ttl=5) # Cache bem curto para atualizar rápido
def buscar_gastos_fatura(usuario_id, cartao_id, fatura_ref):
    """
    Busca as movimentações atreladas ao cartão e à fatura (ex: '07/2026')
    """
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}&cartao_id=eq.{cartao_id}&mes_fatura=eq.{fatura_ref}&select=id,data,descricao,categoria,valor,pago"
    
    res = requests.get(url, headers=HEADERS)
    
    if res.status_code == 200:
        return res.json()
    else:
        # Imprime o erro se a coluna mes_fatura ou cartao_id não existir na tabela movimentacoes
        st.error(f"Erro ao buscar compras ({res.status_code}): {res.text}")
        return []

def atualizar_limite_cartao(usuario_id, cartao_id, novo_limite):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    payload = {"limite": float(novo_limite)}
    res = requests.patch(url, headers=HEADERS, json=payload)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False

def excluir_cartao(usuario_id, cartao_id):
    url = f"{BASE_URL}/cartoes?id=eq.{cartao_id}&usuario_id=eq.{usuario_id}"
    res = requests.delete(url, headers=HEADERS)
    if res.status_code in [200, 204]:
        st.cache_data.clear()
        return True
    return False    

def dados_grafico_tags(usuario_id, mes_selecionado, ano_selecionado):
    """
    Busca todas as movimentações do usuário, filtra por data/mês/ano
    e extrai e agrupa o valor gasto/recebido por tag.
    """
    url = f"{BASE_URL}/movimentacoes?usuario_id=eq.{usuario_id}"
    
    # Adiciona filtro de ano se especificado
    if ano_selecionado and ano_selecionado != "Todos":
        if mes_selecionado and mes_selecionado != "Todos":
            # Filtro por Mês e Ano Específicos (ex: 2026-07-*)
            prefixo_data = f"{ano_selecionado}-{mes_selecionado}"
            url += f"&data=like.{prefixo_data}*"
        else:
            # Filtro por Ano Inteiro (ex: 2026-*)
            url += f"&data=like.{ano_selecionado}-*"

    res = requests.get(url, headers=HEADERS)
    
    if res.status_code != 200:
        return [], []
        
    movimentacoes = res.json()
    if not movimentacoes:
        return [], []

    # Agrupamento das tags no Python
    agrupado_tags = {}

    for m in movimentacoes:
        raw_tags = m.get("tags")
        valor = float(m.get("valor", 0))

        # Ignora registros sem tag ou com tag vazia/NULL
        if not raw_tags or str(raw_tags).strip() in ["None", "null", ""]:
            continue

        # Trata múltiplas tags separadas por vírgula (ex: "#Viagem, #Festa")
        tags_lista = [t.strip().lower() for t in str(raw_tags).split(",") if t.strip()]

        for tag_item in tags_lista:
            # Formata bonito (ex: #viagem2026 -> #Viagem2026)
            tag_formatada = f"#{tag_item.lstrip('#')}"
            
            # Acumula o valor
            agrupado_tags[tag_formatada] = agrupado_tags.get(tag_formatada, 0.0) + valor

    if not agrupado_tags:
        return [], []

    lista_tags = list(agrupado_tags.keys())
    lista_valores = list(agrupado_tags.values())

    return lista_tags, lista_valores

def gerar_insights_financeiros(usuario_id, mes_selecionado, ano_selecionado, movimentacoes_raw, metas_raw):
    """
    Gera insights financeiros automáticos por regras de matemática e lógica,
    sem custos de API externa.
    """
    insights = []
    
    if not movimentacoes_raw:
        return insights

    df = pd.DataFrame(movimentacoes_raw)
    
    # 1. Comparação Mês a Mês por Categoria (Variação de Gastos)
    if mes_selecionado != "Todos" and ano_selecionado != "Todos":
        try:
            mes_int = int(mes_selecionado)
            ano_int = int(ano_selecionado)
            
            # Determina o mês anterior
            if mes_int == 1:
                mes_ant_str, ano_ant_str = "12", str(ano_int - 1)
            else:
                mes_ant_str, ano_ant_str = f"{mes_int - 1:02d}", str(ano_int)
                
            prefixo_atual = f"{ano_selecionado}-{mes_selecionado}"
            prefixo_anterior = f"{ano_ant_str}-{mes_ant_str}"

            # Normaliza e filtra apenas despesas
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
                                    "tipo": "warning",
                                    "icone": "⚠️",
                                    "titulo": f"Aumento em {cat}",
                                    "texto": f"Seus gastos com **{cat}** aumentaram **{variacao:.0f}%** este mês em relação ao anterior."
                                })
                            elif variacao <= -20:
                                insights.append({
                                    "tipo": "success",
                                    "icone": "🎉",
                                    "titulo": f"Economia em {cat}",
                                    "texto": f"Ótimo trabalho! Seus gastos com **{cat}** reduziram **{abs(variacao):.0f}%** este mês."
                                })
        except Exception:
            pass

    # 2. Progresso de Metas de Economia
    if metas_raw:
        for m in metas_raw:
            nome_meta = m[1]
            alvo = float(m[2])
            guardado = float(m[3])
            
            if alvo > 0:
                pct = (guardado / alvo) * 100
                if 85 <= pct < 100:
                    insights.append({
                        "tipo": "success",
                        "icone": "🎯",
                        "titulo": f"Meta {nome_meta}",
                        "texto": f"Você já atingiu **{pct:.0f}%** da sua meta **'{nome_meta}'**!"
                    })
                elif pct >= 100:
                    insights.append({
                        "tipo": "success",
                        "icone": "🏆",
                        "titulo": f"Meta Concluída!",
                        "texto": f"Parabéns! Você alcançou **100%** do seu objetivo **'{nome_meta}'**!"
                    })

    # 3. Comprometimento da Renda (Despesas / Receitas)
    if "tipo" in df.columns and "valor" in df.columns:
        tot_rec = df[df["tipo"].astype(str).str.lower() == "receita"]["valor"].sum()
        tot_desp = df[df["tipo"].astype(str).str.lower() == "despesa"]["valor"].sum()

        if tot_rec > 0:
            pct_comprometido = (tot_desp / tot_rec) * 100
            if pct_comprometido >= 85:
                insights.append({
                    "tipo": "error",
                    "icone": "🚨",
                    "titulo": "Alerta de Orçamento",
                    "texto": f"Suas despesas já comprometeram **{pct_comprometido:.0f}%** da sua receita do período."
                })

    return insights