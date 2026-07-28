import streamlit as st
import pandas as pd
from datetime import datetime, date
import calendar
from supabase import create_client, Client

# ==============================================================================
# CONEXÃO E GERENCIAMENTO DE CACHE
# ==============================================================================

@st.cache_resource
def get_supabase_client() -> Client:
    """Inicializa e reutiliza o cliente do Supabase."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def invalidar_cache():
    """Limpa o cache de dados do Streamlit após qualquer mutação (insert/update/delete)."""
    st.cache_data.clear()

# ==============================================================================
# CONSULTAS OTIMIZADAS COM CACHE (READ)
# ==============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_categorias(user_id: str) -> list:
    """Busca a lista de categorias cadastradas do usuário."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("categorias")\
            .select("nome")\
            .eq("user_id", user_id)\
            .order("nome")\
            .execute()
        return [item["nome"] for item in response.data] if response.data else []
    except Exception as e:
        st.error(f"Erro ao carregar categorias: {e}")
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_transacoes_mes(user_id: str, ano: int, mes: int) -> pd.DataFrame:
    """
    Busca transações filtrando no BANCO por período (mês/ano).
    Evita trafegar dados desnecessários pela rede.
    """
    try:
        supabase = get_supabase_client()
        
        # Define o primeiro e último dia do mês para o filtro
        _, ultimo_dia = calendar.monthrange(ano, mes)
        data_inicio = f"{ano}-{mes:02d}-01"
        data_fim = f"{ano}-{mes:02d}-{ultimo_dia:02d}"

        response = supabase.table("transacoes")\
            .select("id, data, descricao, valor, tipo, categoria, status")\
            .eq("user_id", user_id)\
            .gte("data", data_inicio)\
            .lte("data", data_fim)\
            .order("data", desc=True)\
            .execute()

        df = pd.DataFrame(response.data)
        if not df.empty:
            df["data"] = pd.to_datetime(df["data"]).dt.date
            df["valor"] = pd.to_numeric(df["valor"])
        return df
    except Exception as e:
        st.error(f"Erro ao buscar transações do mês: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_todas_transacoes(user_id: str) -> pd.DataFrame:
    """Busca o histórico completo de transações do usuário."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("transacoes")\
            .select("id, data, descricao, valor, tipo, categoria, status")\
            .eq("user_id", user_id)\
            .order("data", desc=True)\
            .execute()

        df = pd.DataFrame(response.data)
        if not df.empty:
            df["data"] = pd.to_datetime(df["data"]).dt.date
            df["valor"] = pd.to_numeric(df["valor"])
        return df
    except Exception as e:
        st.error(f"Erro ao buscar histórico de transações: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_orcamentos(user_id: str, ano: int, mes: int) -> pd.DataFrame:
    """Busca o orçamento definido pelo usuário para o mês/ano específico."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("orcamentos")\
            .select("id, categoria, teto_gasto")\
            .eq("user_id", user_id)\
            .eq("ano", ano)\
            .eq("mes", mes)\
            .execute()

        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Erro ao carregar orçamentos: {e}")
        return pd.DataFrame()

# ==============================================================================
# OPERAÇÕES DE ESCRITA (MUTATIONS)
# ==============================================================================

def add_transacao(dados: dict) -> bool:
    """Insere uma nova transação e invalida o cache."""
    try:
        supabase = get_supabase_client()
        supabase.table("transacoes").insert(dados).execute()
        invalidar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao cadastrar transação: {e}")
        return False

def update_transacao(transacao_id: int, dados: dict) -> bool:
    """Atualiza uma transação existente e invalida o cache."""
    try:
        supabase = get_supabase_client()
        supabase.table("transacoes").update(dados).eq("id", transacao_id).execute()
        invalidar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar transação: {e}")
        return False

def delete_transacao(transacao_id: int) -> bool:
    """Remove uma transação e invalida o cache."""
    try:
        supabase = get_supabase_client()
        supabase.table("transacoes").delete().eq("id", transacao_id).execute()
        invalidar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao excluir transação: {e}")
        return False

def add_categoria(user_id: str, nome_categoria: str) -> bool:
    """Adiciona uma nova categoria caso não exista."""
    try:
        supabase = get_supabase_client()
        supabase.table("categorias").insert({"user_id": user_id, "nome": nome_categoria.strip()}).execute()
        invalidar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar categoria: {e}")
        return False

def salvar_orcamento(user_id: str, categoria: str, teto: float, ano: int, mes: int) -> bool:
    """Cria ou atualiza (upsert) o teto orçamentário para uma categoria."""
    try:
        supabase = get_supabase_client()
        payload = {
            "user_id": user_id,
            "categoria": categoria,
            "teto_gasto": teto,
            "ano": ano,
            "mes": mes
        }
        # Upsert baseado nas colunas chave configuradas no Supabase
        supabase.table("orcamentos").upsert(payload, on_conflict="user_id, categoria, ano, mes").execute()
        invalidar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar orçamento: {e}")
        return False