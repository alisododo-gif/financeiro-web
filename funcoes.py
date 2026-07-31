import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import urllib.parse
import io

# ==========================================
# CONFIGURAÇÕES DA API DO SUPABASE
# ==========================================
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ==========================================
# FUNÇÕES DE CONSULTA (READ)
# ==========================================

@st.cache_data(ttl=300)
def carregar_perfis():
    url = f"{SUPABASE_URL}/rest/v1/perfis?select=*"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

@st.cache_data(ttl=300)
def obter_perfil_usuario(user_id):
    if not user_id:
        return None
    url = f"{SUPABASE_URL}/rest/v1/perfis?user_id=eq.{user_id}&select=*"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and len(res.json()) > 0:
        return res.json()[0]
    return None

@st.cache_data(ttl=300)
def carregar_categorias(user_id):
    url = f"{SUPABASE_URL}/rest/v1/categorias?user_id=eq.{user_id}&select=*"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

@st.cache_data(ttl=300)
def carregar_contas(user_id):
    url = f"{SUPABASE_URL}/rest/v1/contas?user_id=eq.{user_id}&select=*"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

@st.cache_data(ttl=300)
def carregar_cartoes(user_id):
    url = f"{SUPABASE_URL}/rest/v1/cartoes?user_id=eq.{user_id}&select=*"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

@st.cache_data(ttl=300)
def carregar_orcamentos(user_id):
    url = f"{SUPABASE_URL}/rest/v1/orcamentos?user_id=eq.{user_id}&select=*,categorias(nome)"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

@st.cache_data(ttl=300)
def carregar_metas(user_id):
    url = f"{SUPABASE_URL}/rest/v1/metas?user_id=eq.{user_id}&select=*"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

def _construir_query_data(data_inicio, data_fim):
    query = ""
    if data_inicio:
        query += f"&data=gte.{data_inicio.strftime('%Y-%m-%d')}"
    if data_fim:
        query += f"&data=lte.{data_fim.strftime('%Y-%m-%d')}"
    return query

@st.cache_data(ttl=300)
def carregar_movimentacoes(user_id, tipo=None, categoria_id=None, conta_id=None, data_inicio=None, data_fim=None, busca=None):
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes?user_id=eq.{user_id}&select=*,categorias(nome),contas(nome),cartoes(nome)"
    
    if tipo and tipo != "Todos":
        url += f"&tipo=eq.{urllib.parse.quote(tipo)}"
    if categoria_id and categoria_id != "Todas":
        url += f"&categoria_id=eq.{categoria_id}"
    if conta_id and conta_id != "Todas":
        url += f"&conta_id=eq.{conta_id}"
    if busca:
        busca_encoded = urllib.parse.quote(f"%{busca}%")
        url += f"&descricao=ilike.{busca_encoded}"
        
    url += _construir_query_data(data_inicio, data_fim)
    url += "&order=data.desc"

    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

@st.cache_data(ttl=60)
def buscar_gastos_fatura(cartao_id, mes, ano):
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes?cartao_id=eq.{cartao_id}&fatura_mes=eq.{mes}&fatura_ano=eq.{ano}&select=*,categorias(nome)"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else []

# ==========================================
# FUNÇÕES DE ESCRITA / AÇÕES (MUTATION)
# ==========================================

def criar_perfil_pendente(user_id, email, nome, whatsapp):
    url = f"{SUPABASE_URL}/rest/v1/perfis"
    payload = {
        "user_id": user_id,
        "email": email,
        "nome": nome,
        "whatsapp": whatsapp,
        "status": "pendente",
        "plano": "pro",
        "mrr": 29.90
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    return res.status_code in [200, 201]

def atualizar_status_usuario(user_id, novo_status):
    url = f"{SUPABASE_URL}/rest/v1/perfis?user_id=eq.{user_id}"
    payload = {"status": novo_status}
    res = requests.patch(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code == 200

def salvar_categoria(user_id, nome, tipo, cor="#3b82f6", icone="📁"):
    url = f"{SUPABASE_URL}/rest/v1/categorias"
    payload = {
        "user_id": user_id,
        "nome": nome,
        "tipo": tipo,
        "cor": cor,
        "icone": icone
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code in [200, 201]

def salvar_conta(user_id, nome, tipo, saldo_inicial):
    url = f"{SUPABASE_URL}/rest/v1/contas"
    payload = {
        "user_id": user_id,
        "nome": nome,
        "tipo": tipo,
        "saldo_inicial": float(saldo_inicial)
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code in [200, 201]

def salvar_cartao(user_id, nome, limite, dia_fechamento, dia_vencimento):
    url = f"{SUPABASE_URL}/rest/v1/cartoes"
    payload = {
        "user_id": user_id,
        "nome": nome,
        "limite": float(limite),
        "dia_fechamento": int(dia_fechamento),
        "dia_vencimento": int(dia_vencimento)
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code in [200, 201]

def calcular_mes_ano_fatura(data_compra, dia_fechamento):
    if data_compra.day >= dia_fechamento:
        data_fatura = data_compra + relativedelta(months=1)
    else:
        data_fatura = data_compra
    return data_fatura.month, data_fatura.year

def salvar_movimentacao(user_id, descricao, valor, tipo, data_mov, categoria_id=None, conta_id=None, cartao_id=None, parcela_atual=1, total_parcelas=1, pago=True):
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes"
    
    fatura_mes, fatura_ano = None, None
    if cartao_id:
        cartoes = carregar_cartoes(user_id)
        cartao = next((c for c in cartoes if c['id'] == cartao_id), None)
        if cartao:
            fatura_mes, fatura_ano = calcular_mes_ano_fatura(data_mov, cartao['dia_fechamento'])

    payload = {
        "user_id": user_id,
        "descricao": descricao,
        "valor": float(valor),
        "tipo": tipo,
        "data": data_mov.strftime('%Y-%m-%d'),
        "categoria_id": categoria_id if categoria_id else None,
        "conta_id": conta_id if conta_id else None,
        "cartao_id": cartao_id if cartao_id else None,
        "parcela_atual": int(parcela_atual),
        "total_parcelas": int(total_parcelas),
        "pago": pago,
        "fatura_mes": fatura_mes,
        "fatura_ano": fatura_ano
    }
    
    res = requests.post(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code in [200, 201]

def salvar_movimentacao_parcelada(user_id, descricao, valor_total, tipo, data_mov, total_parcelas, categoria_id=None, cartao_id=None):
    valor_parcela = valor_total / total_parcelas
    sucesso = True
    for i in range(total_parcelas):
        data_p = data_mov + relativedelta(months=i)
        desc = f"{descricao} ({i+1}/{total_parcelas})"
        res = salvar_movimentacao(
            user_id=user_id,
            descricao=desc,
            valor=valor_parcela,
            tipo=tipo,
            data_mov=data_p,
            categoria_id=categoria_id,
            cartao_id=cartao_id,
            parcela_atual=i+1,
            total_parcelas=total_parcelas,
            pago=False if cartao_id else True
        )
        if not res:
            sucesso = False
    return sucesso

def salvar_movimentacao_recorrente(user_id, descricao, valor, tipo, data_inicio, meses, categoria_id=None, conta_id=None):
    sucesso = True
    for i in range(meses):
        data_r = data_inicio + relativedelta(months=i)
        res = salvar_movimentacao(
            user_id=user_id,
            descricao=f"{descricao} (Recorrente)",
            valor=valor,
            tipo=tipo,
            data_mov=data_r,
            categoria_id=categoria_id,
            conta_id=conta_id,
            pago=False
        )
        if not res:
            sucesso = False
    return sucesso

def deletar_movimentacao(mov_id):
    url = f"{SUPABASE_URL}/rest/v1/movimentacoes?id=eq.{mov_id}"
    res = requests.delete(url, headers=HEADERS)
    st.cache_data.clear()
    return res.status_code in [200, 204]

def pagar_fatura_completa(user_id, cartao_id, mes, ano, conta_id, valor_total):
    try:
        # 1. Marca todas as movimentações do cartão/fatura como pagas
        url_patch = f"{SUPABASE_URL}/rest/v1/movimentacoes?cartao_id=eq.{cartao_id}&fatura_mes=eq.{mes}&fatura_ano=eq.{ano}"
        payload_patch = {"pago": True}
        res_patch = requests.patch(url_patch, headers=HEADERS, json=payload_patch)
        
        # 2. Lança a movimentação de saída na conta bancária selecionada
        cartoes = carregar_cartoes(user_id)
        cartao_nome = next((c['nome'] for c in cartoes if c['id'] == cartao_id), "Cartão")
        
        salvar_movimentacao(
            user_id=user_id,
            descricao=f"Pagamento Fatura {cartao_nome} - {mes:02d}/{ano}",
            valor=valor_total,
            tipo="Despesa",
            data_mov=date.today(),
            conta_id=conta_id,
            pago=True
        )
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao liquidar fatura: {e}")
        return False

def salvar_orcamento(user_id, categoria_id, valor_limite, mes, ano):
    url = f"{SUPABASE_URL}/rest/v1/orcamentos"
    payload = {
        "user_id": user_id,
        "categoria_id": categoria_id,
        "valor_limite": float(valor_limite),
        "mes": int(mes),
        "ano": int(ano)
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code in [200, 201]

def salvar_meta(user_id, nome, valor_alvo, data_limite, valor_atual=0.0):
    url = f"{SUPABASE_URL}/rest/v1/metas"
    payload = {
        "user_id": user_id,
        "nome": nome,
        "valor_alvo": float(valor_alvo),
        "valor_atual": float(valor_atual),
        "data_limite": data_limite.strftime('%Y-%m-%d')
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code in [200, 201]

def atualizar_progresso_meta(meta_id, novo_valor):
    url = f"{SUPABASE_URL}/rest/v1/metas?id=eq.{meta_id}"
    payload = {"valor_atual": float(novo_valor)}
    res = requests.patch(url, headers=HEADERS, json=payload)
    st.cache_data.clear()
    return res.status_code == 200

def salvar_despesa_cartao(user_id, descricao, valor, data_compra, cartao_id, categoria_id=None, parcelas=1):
    """
    Função auxiliar para registrar despesas de cartão com suporte a parcelamento automático.
    """
    try:
        if parcelas > 1:
            return salvar_movimentacao_parcelada(
                user_id=user_id,
                descricao=descricao,
                valor_total=valor,
                tipo="Despesa",
                data_mov=data_compra,
                total_parcelas=parcelas,
                categoria_id=categoria_id,
                cartao_id=cartao_id
            )
        else:
            return salvar_movimentacao(
                user_id=user_id,
                descricao=descricao,
                valor=valor,
                tipo="Despesa",
                data_mov=data_compra,
                categoria_id=categoria_id,
                cartao_id=cartao_id,
                pago=False
            )
    except Exception as e:
        st.error(f"Erro ao salvar despesa do cartão: {e}")
        return False