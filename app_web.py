import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px

# Importa todas as funções otimizadas do backend
from funcoes import (
    get_categorias,
    get_transacoes_mes,
    get_todas_transacoes,
    get_orcamentos,
    add_transacao,
    update_transacao,
    delete_transacao,
    add_categoria,
    salvar_orcamento,
)

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="FinanceiroPro Web",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS adicional para refinamento visual
st.markdown("""
    <style>
    .stMetric {
        background-color: #1f2937;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #374151;
    }
    .stButton>button {
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# AUTENTICAÇÃO / USUÁRIO (Simulação de Session State)
# ==============================================================================
if "user_id" not in st.session_state:
    # Caso você já tenha tela de login, o user_id virá da sessão de autenticação.
    # Exemplo temporário para testes:
    st.session_state["user_id"] = "user_demo_123"

user_id = st.session_state["user_id"]

# ==============================================================================
# SIDEBAR - FILTROS DE PERÍODO & AÇÕES RÁPIDAS
# ==============================================================================
st.sidebar.title("💰 FinanceiroPro")
st.sidebar.caption("Gestão Financeira Pessoal")

hoje = date.today()
meses_nome = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

st.sidebar.subheader("📅 Período de Análise")
col_m, col_a = st.sidebar.columns([2, 1])
mes_nome_selecionado = col_m.selectbox("Mês", meses_nome, index=hoje.month - 1)
ano_selecionado = col_a.number_input("Ano", min_value=2020, max_value=2030, value=hoje.year)

mes_num_selecionado = meses_nome.index(mes_nome_selecionado) + 1

# ==============================================================================
# CARREGAMENTO DE DADOS COM CACHE
# ==============================================================================
df_mes = get_transacoes_mes(user_id, ano_selecionado, mes_num_selecionado)
categorias_cadastradas = get_categorias(user_id)

# Garantir categorias mínimas padrões caso o usuário não tenha nenhuma ainda
if not categorias_cadastradas:
    categorias_cadastradas = ["Alimentação", "Moradia", "Transporte", "Lazer", "Saúde", "Salário", "Investimentos", "Outros"]

# ==============================================================================
# CORPO PRINCIPAL - ABAS
# ==============================================================================
st.title(f"Painel Financeiro — {mes_nome_selecionado}/{ano_selecionado}")

tab_dashboard, tab_nova_transacao, tab_gerenciar, tab_orcamento = st.tabs([
    "📊 Dashboard", 
    "➕ Nova Transação", 
    "📝 Gerenciar Registros", 
    "🎯 Orçamentos & Categorias"
])

# ------------------------------------------------------------------------------
# TAB 1: DASHBOARD
# ------------------------------------------------------------------------------
with tab_dashboard:
    if df_mes.empty:
        st.info("Nenhuma transação registrada para o período selecionado.")
    else:
        # Cálculo dos KPIs
        total_receitas = df_mes[df_mes["tipo"] == "Receita"]["valor"].sum()
        total_despesas = df_mes[df_mes["tipo"] == "Despesa"]["valor"].sum()
        saldo_mes = total_receitas - total_despesas
        taxa_poupanca = ((total_receitas - total_despesas) / total_receitas * 100) if total_receitas > 0 else 0.0

        # Métrica / Cards
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Receitas no Mês", f"R$ {total_receitas:,.2f}")
        kpi2.metric("Despesas no Mês", f"R$ {total_despesas:,.2f}", delta=f"-R$ {total_despesas:,.2f}", delta_color="inverse")
        kpi3.metric("Saldo do Mês", f"R$ {saldo_mes:,.2f}", delta=f"R$ {saldo_mes:,.2f}")
        kpi4.metric("Taxa de Poupança", f"{taxa_poupanca:.1f}%")

        st.markdown("---")

        # Gráficos em Colunas
        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.subheader("Despesas por Categoria")
            df_despesas = df_mes[df_mes["tipo"] == "Despesa"]
            if not df_despesas.empty:
                df_cat = df_despesas.groupby("categoria")["valor"].sum().reset_index()
                fig_cat = px.pie(
                    df_cat, 
                    names="categoria", 
                    values="valor", 
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_cat.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_cat, use_container_width=True)
            else:
                st.write("Sem despesas cadastradas neste mês.")

        with col_graf2:
            st.subheader("Evolução Diária de Entradas/Saídas")
            df_diario = df_mes.groupby(["data", "tipo"])["valor"].sum().reset_index()
            fig_bar = px.bar(
                df_diario,
                x="data",
                y="valor",
                color="tipo",
                barmode="group",
                color_discrete_map={"Receita": "#10B981", "Despesa": "#EF4444"}
            )
            fig_bar.update_layout(xaxis_title="Data", yaxis_title="Valor (R$)")
            st.plotly_chart(fig_bar, use_container_width=True)

        # Tabela Detalhada do Mês
        st.subheader("Últimas Transações do Mês")
        st.dataframe(
            df_mes,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": None, # Esconde o ID
                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "descricao": "Descrição",
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Receita", "Despesa"]),
                "categoria": "Categoria",
                "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "status": "Status"
            }
        )

# ------------------------------------------------------------------------------
# TAB 2: NOVA TRANSAÇÃO (UTILIZANDO ST.FORM)
# ------------------------------------------------------------------------------
with tab_nova_transacao:
    st.subheader("Cadastrar Novo Lançamento")
    
    with st.form("form_add_transacao", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        
        data_transacao = col_f1.date_input("Data da Transação", value=date.today())
        tipo_transacao = col_f2.selectbox("Tipo", ["Despesa", "Receita"])
        
        col_f3, col_f4 = st.columns(2)
        descricao = col_f3.text_input("Descrição", placeholder="Ex: Compras do Mês, Salário...")
        valor = col_f4.number_input("Valor (R$)", min_value=0.01, step=10.0, format="%.2f")
        
        col_f5, col_f6 = st.columns(2)
        categoria = col_f5.selectbox("Categoria", categorias_cadastradas)
        status = col_f6.selectbox("Status", ["Pago / Recebido", "Pendente"])
        
        btn_salvar = st.form_submit_button("💾 Salvar Transação", use_container_width=True)
        
        if btn_salvar:
            if not descricao.strip():
                st.warning("A descrição é obrigatória!")
            else:
                payload = {
                    "user_id": user_id,
                    "data": str(data_transacao),
                    "descricao": descricao,
                    "valor": valor,
                    "tipo": tipo_transacao,
                    "categoria": categoria,
                    "status": status
                }
                sucesso = add_transacao(payload)
                if sucesso:
                    st.success("Transação registrada com sucesso!")
                    st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: GERENCIAR REGISTROS (EDITAR / EXCLUIR)
# ------------------------------------------------------------------------------
with tab_gerenciar:
    st.subheader("Editar ou Remover Transações")
    
    df_todos = get_todas_transacoes(user_id)
    
    if df_todos.empty:
        st.info("Nenhuma transação encontrada no histórico.")
    else:
        # Criação de seletor intuitivo para edição
        df_todos["label_busca"] = df_todos.apply(
            lambda r: f"ID: {r['id']} | {r['data']} | {r['descricao']} (R$ {r['valor']:.2f})", axis=1
        )
        
        transacao_selecionada_label = st.selectbox(
            "Selecione uma transação para editar ou excluir:",
            df_todos["label_busca"].tolist()
        )
        
        if transacao_selecionada_label:
            idx_selecionado = df_todos["label_busca"].tolist().index(transacao_selecionada_label)
            row_edit = df_todos.iloc[idx_selecionado]
            
            st.markdown("---")
            st.markdown(f"**Modificando Transação ID:** `{row_edit['id']}`")
            
            with st.form("form_edit_transacao"):
                col_e1, col_e2 = st.columns(2)
                
                # Conversão segura da data string/date
                dt_valor = row_edit["data"] if isinstance(row_edit["data"], date) else datetime.strptime(str(row_edit["data"]), "%Y-%m-%d").date()
                
                e_data = col_e1.date_input("Data", value=dt_valor)
                e_tipo = col_e2.selectbox("Tipo", ["Despesa", "Receita"], index=0 if row_edit["tipo"] == "Despesa" else 1)
                
                col_e3, col_e4 = st.columns(2)
                e_desc = col_e3.text_input("Descrição", value=row_edit["descricao"])
                e_valor = col_e4.number_input("Valor (R$)", value=float(row_edit["valor"]), min_value=0.01, format="%.2f")
                
                col_e5, col_e6 = st.columns(2)
                cat_idx = categorias_cadastradas.index(row_edit["categoria"]) if row_edit["categoria"] in categorias_cadastradas else 0
                e_cat = col_e5.selectbox("Categoria", categorias_cadastradas, index=cat_idx)
                
                status_opts = ["Pago / Recebido", "Pendente"]
                status_idx = status_opts.index(row_edit["status"]) if row_edit["status"] in status_opts else 0
                e_status = col_e6.selectbox("Status", status_opts, index=status_idx)
                
                col_btn1, col_btn2 = st.columns(2)
                btn_atualizar = col_btn1.form_submit_button("🔄 Atualizar Registros", use_container_width=True)
                btn_deletar = col_btn2.form_submit_button("🗑️ Excluir Transação", use_container_width=True, type="primary")
                
                if btn_atualizar:
                    payload_update = {
                        "data": str(e_data),
                        "descricao": e_desc,
                        "valor": e_valor,
                        "tipo": e_tipo,
                        "categoria": e_cat,
                        "status": e_status
                    }
                    if update_transacao(int(row_edit["id"]), payload_update):
                        st.success("Transação atualizada com sucesso!")
                        st.rerun()

                if btn_deletar:
                    if delete_transacao(int(row_edit["id"])):
                        st.success("Transação removida com sucesso!")
                        st.rerun()

# ------------------------------------------------------------------------------
# TAB 4: ORÇAMENTOS & CATEGORIAS
# ------------------------------------------------------------------------------
with tab_orcamento:
    col_o1, col_o2 = st.columns(2)
    
    with col_o1:
        st.subheader("🎯 Definir Teto Orçamentário do Mês")
        st.caption(f"Meta de gastos para **{mes_nome_selecionado}/{ano_selecionado}**")
        
        with st.form("form_orcamento"):
            cat_orc = st.selectbox("Categoria", categorias_cadastradas, key="orc_cat")
            teto_gasto = st.number_input("Teto Limite de Gastos (R$)", min_value=0.0, step=50.0, format="%.2f")
            
            if st.form_submit_button("Salvar Orçamento", use_container_width=True):
                if salvar_orcamento(user_id, cat_orc, teto_gasto, ano_selecionado, mes_num_selecionado):
                    st.success(f"Orçamento para '{cat_orc}' configurado com sucesso!")
                    st.rerun()

        # Exibição do acompanhamento do Orçamento
        df_orc = get_orcamentos(user_id, ano_selecionado, mes_num_selecionado)
        if not df_orc.empty:
            st.markdown("#### Acompanhamento de Metas")
            df_gastos_cat = df_mes[df_mes["tipo"] == "Despesa"].groupby("categoria")["valor"].sum().reset_index()
            
            df_meta = pd.merge(df_orc, df_gastos_cat, on="categoria", how="left").fillna(0.0)
            df_meta.rename(columns={"valor": "gasto_atual"}, inplace=True)
            df_meta["progresso"] = (df_meta["gasto_atual"] / df_meta["teto_gasto"]).clip(upper=1.0)
            
            for _, r in df_meta.iterrows():
                st.write(f"**{r['categoria']}**: R$ {r['gasto_atual']:,.2f} de R$ {r['teto_gasto']:,.2f}")
                st.progress(float(r["progresso"]))

    with col_o2:
        st.subheader("📁 Cadastrar Nova Categoria")
        with st.form("form_add_categoria", clear_on_submit=True):
            nova_cat = st.text_input("Nome da Nova Categoria")
            
            if st.form_submit_button("Adicionar Categoria", use_container_width=True):
                if nova_cat.strip():
                    if add_categoria(user_id, nova_cat):
                        st.success(f"Categoria '{nova_cat}' adicionada com sucesso!")
                        st.rerun()
                else:
                    st.warning("O nome da categoria não pode ser vazio.")