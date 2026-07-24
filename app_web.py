import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
import io
import plotly.graph_objects as go
import plotly.express as px
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import urllib.parse
import pytz


# Novas importações para o PDF profissional e leve
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from funcoes import (
    buscar_todas_movimentacoes,
    dados_dashboard,
    dados_grafico_mensal,
    dados_grafico_categorias,
    alterar_senha_usuario,
    obter_limite_orcamento,
    definir_limite_orcamento,
    cadastrar_conta,
    listar_contas,
    excluir_conta,
    criar_meta,
    listar_metas,
    atualizar_progresso_meta,
    salvar_movimentacao,
    salvar_movimentacao_parcelada,
    salvar_movimentacao_recorrente,
    excluir_movimentacao,
    formatar_moeda_ptbr,
    listar_todos_usuarios_admin,
    atualizar_status_e_mensalidade,
    excluir_usuario_admin,
    excluir_meta,
    obter_limites_por_categoria,
    buscar_vencimentos_proximos,
    salvar_orcamento_categoria,
    excluir_orcamento_categoria,
    excluir_lancamento_pendente,
    marcar_lancamento_como_pago,
    desfazer_pagamento_lancamento,
    dar_baixa_fatura_completa,
    listar_cartoes,
    cadastrar_cartao,
    calcular_mes_fatura,
    buscar_gastos_fatura,
    atualizar_limite_cartao,
    excluir_cartao,
    dados_grafico_tags,
    gerar_insights_financeiros
)

from views import render_sidebar_footer

# --- CONFIGURAÇÃO DA PÁGINA (DEVE APARECER APENAS UMA VEZ) ---
st.set_page_config(
    page_title="FinanceiroPro Web",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- NOVA PERSISTÊNCIA VIA URL (NATIVA E IMEDIATA) ---
# Se o ID do usuário estiver na URL da página, loga ele automaticamente após o F5
url_uid = st.query_params.get("uid")

if "usuario_id" not in st.session_state:
    st.session_state["usuario_id"] = int(url_uid) if url_uid else None

if "is_admin" not in st.session_state:
    # Se o ID recuperado for o do admin (1), já define como True automaticamente
    st.session_state["is_admin"] = True if st.session_state["usuario_id"] == 1 else False

# --- TRANSFERIDO PARA O TOPO ABSOLUTO ---
if st.session_state["usuario_id"] == 1:
    st.session_state["is_admin"] = True

def fmt_moeda(valor):
    return formatar_moeda_ptbr(float(valor))

# --- ADICIONADO: DEFINIÇÃO GLOBAL DA FUNÇÃO DO WHATSAPP ---
def criar_link_cobranca(telefone, nome, valor):
    if not telefone:
        return None
    telefone_limpo = "".join(filter(str.isdigit, str(telefone)))
    mensagem = (
        f"Olá, {nome}! Tudo bem?\n\n"
        f"Passando para lembrar que a mensalidade da sua plataforma FinanceiroPro "
        f"no valor de R$ {valor:.2f} está em aberto.\n\n"
        f"Para restabelecer ou manter o seu acesso integral, você pode realizar o pagamento. "
        f"Caso já tenha efetuado, por favor, envie o comprovante por aqui. Obrigado!"
    )
    texto_codificado = urllib.parse.quote(mensagem)
    return f"https://api.whatsapp.com/send?phone=55{telefone_limpo}&text={texto_codificado}"


CATEGORIAS_DESPADREVAL = ["Alimentação", "Transporte", "Cartão de Crédito", "Cartão de Débito", "Pix", "Moradia", "Lazer", "Saúde", "Educação", "Assinaturas/Serviços", "Outros"]
CATEGORIAS_RECEITAS = ["Salário", "Freelance", "Investimentos", "Presente/Prêmio"]

# --- FUNÇÃO DE EXPORTAÇÃO EXCEL PROFISSIONAL ---
def gerar_excel_profissional(dados_banco, mes, ano):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extrato Financeiro"
    ws.views.sheetView[0].showGridLines = True
    
    # Título do Relatório
    ws.merge_cells("A1:I1")
    ws["A1"] = f"Relatório de Extrato Detalhado - Período: {mes}/{ano}"
    ws["A1"].font = Font(name="Arial", size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40
    
    headers = ["ID", "Data", "Conta", "Tipo", "Forma Pagto", "Descrição", "Valor", "Categoria", "Tags"]
    ws.append([]) 
    ws.append(headers)
    ws.row_dimensions[3].height = 26
    
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
    )
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = thin_border
        
    row_num = 4
    total_receitas = 0.0
    total_despesas = 0.0
    
    for item in dados_banco:
        v_id = item[0]
        v_data = item[1]
        v_conta = item[2]
        v_tipo = item[3]
        v_forma = item[4]
        v_desc = item[5]
        v_valor = item[6]
        v_cat = item[7]
        v_tags = item[8] if len(item) > 8 else ""
        
        v_valor_float = float(v_valor)
        
        # Formata a data para DD/MM/AAAA
        try:
            v_data_fmt = pd.to_datetime(v_data).strftime('%d/%m/%Y')
        except Exception:
            v_data_fmt = str(v_data)

        if str(v_tipo).lower() == "receita":
            total_receitas += v_valor_float
        else:
            total_despesas += v_valor_float
            
        # Usa v_data_fmt no lugar de v_data
        ws.append([v_id, v_data_fmt, v_conta, v_tipo, v_forma, v_desc, v_valor_float, v_cat, v_tags])
        ws.row_dimensions[row_num].height = 20
        
        bg_color = "F9FBFD" if row_num % 2 == 0 else "FFFFFF"
        row_fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
        
        for col_num in range(1, 10):
            cell = ws.cell(row=row_num, column=col_num)
            cell.fill = row_fill
            cell.border = thin_border
            cell.font = Font(name="Arial", size=10)
            
            if col_num in [1, 2, 4, 5]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_num == 7:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = '"R$"#,##0.00'
                cell.font = Font(name="Arial", size=10, color="27AE60" if str(v_tipo).lower() == "receita" else "C0392B")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        row_num += 1
        
    ws.append([])
    row_num += 1
    ws.merge_cells(start_row=row_num, start_column=1, end_row=row_num, end_column=6)
    ws.cell(row=row_num, column=1, value="SALDO FINAL DO PERÍODO:").font = Font(name="Arial", size=11, bold=True)
    ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="right")
    
    saldo_final = total_receitas - total_despesas
    cell_saldo = ws.cell(row=row_num, column=7, value=saldo_final)
    cell_saldo.font = Font(name="Arial", size=11, bold=True)
    cell_saldo.number_format = '"R$"#,##0.00'
    
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == 1: continue
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# --- NOVA FUNÇÃO DE EXPORTAÇÃO PDF SUPER LEVE E ESTÁVEL ---
def gerar_pdf_profissional(dados_banco, mes, ano):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18,
        textColor=colors.HexColor('#1F4E78'), spaceAfter=6, alignment=1
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10,
        textColor=colors.HexColor('#7F8C8D'), spaceAfter=20, alignment=1
    )
    
    story.append(Paragraph("FinanceiroPro Web - Extrato Detalhado", title_style))
    story.append(Paragraph(f"Período consultado: {mes}/{ano} — Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    
    table_data = [["ID", "Data", "Conta", "Tipo", "Forma Pagto", "Descrição", "Valor", "Categoria", "Tags"]]
    
    total_rec = 0.0
    total_des = 0.0
    
    for item in dados_banco:
        v_id = item[0]
        v_data = item[1]
        v_conta = item[2]
        v_tipo = item[3]
        v_forma = item[4]
        v_desc = item[5]
        v_valor = item[6]
        v_cat = item[7]
        v_tags = item[8] if len(item) > 8 else ""
        
        v_valor_float = float(v_valor)
        
        # Formata a data para DD/MM/AAAA
        try:
            v_data_fmt = pd.to_datetime(v_data).strftime('%d/%m/%Y')
        except Exception:
            v_data_fmt = str(v_data)

        if str(v_tipo).lower() == "receita":
            total_rec += v_valor_float
        else:
            total_des += v_valor_float
            
        # Usa v_data_fmt no lugar de str(v_data)
        table_data.append([
            str(v_id), v_data_fmt, str(v_conta), str(v_tipo), 
            str(v_forma), str(v_desc), formatar_moeda_ptbr(v_valor_float), str(v_cat), str(v_tags)
        ])
        
    table_data.append(["", "", "", "", "", "Total Receitas:", formatar_moeda_ptbr(total_rec), "", ""])
    table_data.append(["", "", "", "", "", "Total Despesas:", formatar_moeda_ptbr(total_des), "", ""])
    table_data.append(["", "", "", "", "", "SALDO LÍQUIDO:", formatar_moeda_ptbr(total_rec - total_des), "", ""])
    
    t = Table(table_data, colWidths=[25, 60, 80, 50, 75, 130, 80, 85, 85])
    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('ALIGN', (6, 1), (6, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -4), 0.5, colors.HexColor('#E2E8F0')),
    ])
    
    for i in range(1, len(dados_banco) + 1):
        if i % 2 == 0:
            t_style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8FAFC'))
            
    total_idx = len(table_data)
    t_style.add('FONTNAME', (5, total_idx-3), (6, total_idx-1), 'Helvetica-Bold')
    t_style.add('TEXTCOLOR', (6, total_idx-3), (6, total_idx-3), colors.HexColor('#27AE60'))
    t_style.add('TEXTCOLOR', (6, total_idx-2), (6, total_idx-2), colors.HexColor('#C0392B'))
    t_style.add('BACKGROUND', (5, total_idx-1), (6, total_idx-1), colors.HexColor('#EAEDED'))
    
    t.setStyle(t_style)
    story.append(t)
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def fazer_login_rest(usuario, senha):
    import requests
    BASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    senha_hash = hashlib.sha256(senha.encode('utf-8')).hexdigest()
    url = f"{BASE_URL}/usuarios?usuario=eq.{usuario.strip()}&select=id,senha,role,status"
    res = requests.get(url, headers=headers)
    if res.status_code == 200 and res.json():
        usuario_banco = res.json()[0]
        if usuario_banco['senha'] == senha_hash:
            status_atual = usuario_banco.get('status', 'ativo')
            if status_atual == 'inativo':
                st.error("⚠️ Sua conta está suspensa. Entre em contato com o administrador.")
                return None
            elif status_atual == 'pendente':
                st.warning("⏳ Seu acesso está em análise! Aguarde a liberação do administrador.")
                return None
                
            st.session_state["is_admin"] = (usuario_banco.get('role') == 'admin')
            return usuario_banco['id']
    return None

import hashlib
import requests
import streamlit as st

def criar_usuario_rest(usuario, senha, status='pendente', valor_mensalidade=0.0, telefone=""):
    BASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    headers = {
        "apikey": SUPABASE_KEY, 
        "Authorization": f"Bearer {SUPABASE_KEY}", 
        "Content-Type": "application/json", 
        "Prefer": "return=representation"
    }
    
    url_check = f"{BASE_URL}/usuarios?usuario=eq.{usuario.strip()}&select=id"
    res_check = requests.get(url_check, headers=headers)
    if res_check.status_code == 200 and res_check.json():
        return "Existe"
        
    senha_hash = hashlib.sha256(senha.encode('utf-8')).hexdigest()
    url_ins = f"{BASE_URL}/usuarios"
    
    # Payload para o Supabase
    payload = {
        "usuario": usuario.strip(), 
        "senha": senha_hash, 
        "role": "user", 
        "status": status, 
        "valor_mensalidade": valor_mensalidade,
        "telefone": telefone.strip()
    }
    
    res_ins = requests.post(url_ins, headers=headers, json=payload)
    if res_ins.status_code in [200, 201] and res_ins.json():
        return res_ins.json()[0]['id']
    return False

# Autenticação
if st.session_state.get("usuario_id") is None:
    st.markdown("<h2 style='text-align: center;'>🔑 Acesso ao FinanceiroPro Web</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        modo = st.radio("Opção:", ["Fazer Login", "📝 Criar Nova Conta"], horizontal=True)
        
        # Campo alterado para 'Seu Usuário'
        username_input = st.text_input("Seu Usuário")
        
        # Campo de telefone exibido apenas no cadastro
        telefone_input = ""
        if modo == "📝 Criar Nova Conta":
            telefone_input = st.text_input("Telefone")
            
        password_input = st.text_input("Senha", type="password")
        
        if modo == "Fazer Login":
            if st.button("Entrar", width="stretch"):
                if not username_input.strip() or not password_input.strip():
                    st.error("Preencha o usuário e a senha para entrar.")
                else:
                    uid = fazer_login_rest(username_input, password_input)
                    if uid:
                        st.session_state["usuario_id"] = uid
                        st.query_params["uid"] = str(uid)
                        st.success("Logado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Usuário incorreto, senha inválida ou restrição de acesso.")
        else:
            if st.button("Cadastrar e Solicitar Acesso", width="stretch"):
                # Validação garantindo que os 3 campos estão preenchidos
                if username_input.strip() and telefone_input.strip() and password_input.strip():
                    # Passando explicitamente 'telefone=telefone_input' para evitar conflito de ordem
                    res = criar_usuario_rest(
                        usuario=username_input, 
                        senha=password_input, 
                        telefone=telefone_input, 
                        status='pendente'
                    )
                    
                    if res == "Existe":
                        st.error("Este nome de usuário já está em uso.")
                    elif res:
                        st.success("🎉 Cadastro realizado! Aguarde a liberação do administrador.")
                    else:
                        st.error("Erro ao realizar o cadastro. Tente novamente.")
                else:
                    st.error("Por favor, preencha todos os campos obrigatórios (Seu Usuário, Telefone e Senha).")
                    
    st.stop()

# Sua lista de opções padrão com as novas telas incluídas
opcoes_menu = [
    "📊 Dashboard",
    "🏦 Gerir Contas",
    "💸 Lançar Movimentações",
    "💳 Cartões & Faturas",
    "📅 Próximos Vencimentos",     # <--- Nova opção 
    "🎯 Metas de Economia", 
    "🎯 Orçamentos por Categoria",  # <--- Nova opção
    "📋 Extrato Detalhado", 
    "⚙️ Configurações"
]

# SE for admin, adiciona o Painel SaaS no FINAL da lista (depois de Configurações)
if st.session_state["is_admin"]:
    opcoes_menu.append("👑 Painel Admin SaaS") # <-- Trocado .insert(0) por .append()

# Agora o Streamlit desenha a barra lateral na ordem correta
with st.sidebar:
    st.title("💰 FinanceiroPro")
    st.write(f"👤 Usuário ID: **{st.session_state['usuario_id']}** {'(👑 Admin)' if st.session_state['is_admin'] else ''}")
    opcao = st.selectbox("Menu de Navegação", opcoes_menu)
    
    # 🔽 O BOTÃO ENTRA BEM AQUI:
    st.markdown("---")  # Linha divisória para dar um espaçamento elegante
    if st.button("🚪 Sair do Sistema", width="stretch"):
        st.query_params.clear()  # Limpa o ?uid=1 da URL do navegador
        if "usuario_id" in st.session_state:
            del st.session_state["usuario_id"]
        if "is_admin" in st.session_state:
            del st.session_state["is_admin"]
        st.rerun()  # Recarrega a página instantaneamente já deslogado

# --- NOVO PAINEL ADMIN SAAS COMPLETO ---
if opcao == "👑 Painel Admin SaaS" and st.session_state["is_admin"]:
    st.title("👑 Painel de Controle Master SaaS")
    
    # 1. Carregar todos os usuários do banco
    usuarios_lista = listar_todos_usuarios_admin()
    df_users = pd.DataFrame(usuarios_lista)
    
    # 2. Métrica de Faturamento Total Recorrente (MRR)
    faturamento_mrr = 0.0
    if not df_users.empty and 'valor_mensalidade' in df_users.columns:
        # Soma apenas a mensalidade dos clientes que estão ativos
        faturamento_mrr = df_users[df_users['status'] == 'ativo']['valor_mensalidade'].astype(float).sum()
        
    col_fat1, col_fat2, col_fat3 = st.columns(3)
    col_fat1.metric("💰 Faturamento Mensal Estimado (Ativos)", fmt_moeda(faturamento_mrr))
    if not df_users.empty:
        col_fat2.metric("👥 Total de Clientes", len(df_users))
        col_fat3.metric("⏳ Cadastros Pendentes", len(df_users[df_users['status'] == 'pendente']))

    st.markdown("---")
    
    # Criação das Sub-Abas do Admin
    adm_tab1, adm_tab2, adm_tab3 = st.tabs(["⏳ Liberar Cadastros", "➕ Criar Cliente Manual", "👥 Gerenciar Clientes (Ativar/Inativar)"])
    
    # Sub-Aba 1: Fila de aprovação de novos cadastros
    with adm_tab1:
        st.write("### 🔑 Clientes aguardando liberação de acesso")
        if not df_users.empty and 'status' in df_users.columns:
            df_pendentes = df_users[df_users['status'] == 'pendente']
            if df_pendentes.empty:
                st.success("Nenhum cliente aguardando liberação no momento.")
            else:
                for idx, row in df_pendentes.iterrows():
                    col_p1, col_p2, col_p3 = st.columns([2, 2, 1.5])
                    col_p1.write(f"👤 Cliente: **{row['usuario']}**")
                    with col_p2:
                        v_mensal = st.number_input(f"Definir Mensalidade (R$)", min_value=0.0, value=49.90, key=f"v_pend_{row['id']}")
                    with col_p3:
                        if st.button("✅ Ativar Conta", key=f"btn_lib_{row['id']}", width="stretch"):
                            if atualizar_status_e_mensalidade(row['id'], 'ativo', v_mensal):
                                st.success(f"Acesso liberado para {row['usuario']}!")
                                st.rerun()
        else:
            st.info("Nenhum registro encontrado.")
            
    # Sub-Aba 2: Cadastro Manual de Clientes pelo Admin
    with adm_tab2:
        st.write("### ➕ Cadastrar novo cliente diretamente")
        with st.form("form_cadastro_manual", clear_on_submit=True):
            novo_usr = st.text_input("Nome de Usuário:")
            nova_sen = st.text_input("Senha Inicial:", type="password")
            novo_tel = st.text_input("Telefone (Apenas números com DDD):", placeholder="65999998888")
            mensalidade_manual = st.number_input("Valor da Mensalidade (R$):", min_value=0.0, value=49.90)
            status_manual = st.selectbox("Status Inicial:", ["ativo", "inativo", "pendente"])
            
            if st.form_submit_button("Salvar e Criar Cliente"):
                if novo_usr and nova_sen:
                    res_manual = criar_usuario_rest(
                    novo_usr, 
                    nova_sen, 
                    status=status_manual, 
                    valor_mensalidade=mensalidade_manual, 
                    telefone=novo_tel        
                    )
                    if res_manual == "Existe":
                        st.error("Este nome de usuário já existe.")
                    elif res_manual:
                        st.success(f"🎉 Cliente '{novo_usr}' cadastrado com sucesso de forma manual!")
                        st.rerun()
                else:
                    st.error("Preencha o usuário e a senha.")

    # Sub-Aba 3: Ativar, Inativar e Visualizar a Lista Geral de Clientes
    with adm_tab3:
        st.write("### 👥 Gerenciamento e Modificação de Clientes Existentes")
        if not df_users.empty:
            for idx, row in df_users.iterrows():
                # Ignorar o próprio admin para ele não se auto-bloquear
                if row.get('role') == 'admin':
                    continue
                    
                # Aumentamos o número de colunas para adicionar o espaço do WhatsApp (col_g5)
                col_g1, col_g2, col_g3, col_g4, col_g5 = st.columns([2, 1.5, 1.5, 1.5, 1.5])
                
                col_g1.write(f"👤 **{row['usuario']}**")
                
                # Exibe o status atual com cor indicativa
                status_atual = row.get('status', 'ativo')
                if status_atual == 'ativo':
                    col_g2.markdown("🟢 **Ativo**")
                elif status_atual == 'inativo':
                    col_g2.markdown("🔴 **Inativo (Bloqueado)**")
                else:
                    col_g2.markdown("⏳ **Pendente**")
                    
                col_g3.write(f"Mensalidade: {fmt_moeda(row.get('valor_mensalidade', 0.0))}")
                
                with col_g4:
                    # Se está ativo, dá a opção de inativar. Se está inativo, dá a opção de ativar.
                    if status_atual == 'ativo':
                        if st.button("🚫 Suspender", key=f"btn_susp_{row['id']}", width="stretch"):
                            atualizar_status_e_mensalidade(row['id'], 'inativo', float(row.get('valor_mensalidade', 0.0)))
                            st.rerun()
                    else:
                        if st.button("⚡ Reativar", key=f"btn_reat_{row['id']}", width="stretch"):
                            atualizar_status_e_mensalidade(row['id'], 'ativo', float(row.get('valor_mensalidade', 0.0)))
                            st.rerun()
                            
                with col_g5:
                    # GERAÇÃO DINÂMICA DO WHATSAPP E BOTÃO DE EXCLUSÃO
                    if status_atual in ['inativo', 'pendente']:
                        tel_cadastro = row.get('telefone', '')
                        
                        # Criamos duas sub-colunas internas para os botões ficarem lado a lado de forma elegante
                        col_btn_zap, col_btn_del = st.columns([1, 1])
                        
                        with col_btn_zap:
                            if tel_cadastro:
                                url_whatsapp = criar_link_cobranca(
                                    telefone=tel_cadastro,
                                    nome=row['usuario'],
                                    valor=float(row.get('valor_mensalidade', 0.0))
                                )
                                st.link_button("💬 Cobrar", url_whatsapp, width="stretch")
                            else:
                                st.caption("⚠️ Sem Tel.")
                                
                        with col_btn_del:
                            if st.button("❌ Excluir", key=f"btn_del_{row['id']}", width="stretch"):
                                if excluir_usuario_admin(row['id']):
                                    st.success(f"Usuário deletado!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao deletar.")
                    else:
                        st.write("") # Mantém a coluna alinhada vazia para clientes ativos          
            

# --- ABA 1: DASHBOARD ---
elif opcao == "📊 Dashboard":
    st.markdown("<h2>📊 Dashboard Financeiro</h2>", unsafe_allow_html=True)
    
    # Mapeamento dos meses por extenso
    opcoes_meses = [
        "Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    
    col_mes, col_ano = st.columns(2)
    with col_mes:
        mes_nome = st.selectbox(
            "Filtrar por Mês", 
            opcoes_meses, 
            index=datetime.now().month  # Define o mês atual por padrão
        )
        
        # Converte a seleção de volta para o formato esperado ("Todos", "01", "02", ...)
        if mes_nome == "Todos":
            mes_selecionado = "Todos"
        else:
            mes_selecionado = f"{opcoes_meses.index(mes_nome):02d}"

    with col_ano:
        opcoes_anos = ["2026", "2027", "2028", "2029", "2030"]
        ano_atual_str = str(datetime.now().year)
        idx_ano = opcoes_anos.index(ano_atual_str) if ano_atual_str in opcoes_anos else 0
        ano_selecionado = st.selectbox("Filtrar por Ano", opcoes_anos, index=idx_ano)
    
    dados = dados_dashboard(st.session_state["usuario_id"], mes_selecionado, ano_selecionado)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Total Receitas", fmt_moeda(dados['receitas']))
    m2.metric("💸 Total Despesas", fmt_moeda(dados['despesas']))
    m3.metric("🏦 Saldo Atual", fmt_moeda(dados['saldo']))
    m4.metric("🎯 Eficiência", f"{(dados['saldo']/dados['receitas']*100) if dados['receitas'] > 0 else 0:.1f}%")

   # --- SEÇÃO DE ASSISTENTE DE IA / INSIGHTS FINANCEIROS ---
    st.markdown("---")
    st.markdown("### 🤖 Assistente de IA / Insights Financeiros")

    try:
        # Aproveita as funções que já existem e funcionam no seu projeto
        metas_raw = listar_metas(st.session_state["usuario_id"])
        
        # Cria insights diretamente a partir das métricas e metas carregadas
        insights_gerados = []
        
        # 1. Alerta de Comprometimento de Renda (Despesas x Receitas)
        rec_tot = float(dados.get('receitas', 0))
        desp_tot = float(dados.get('despesas', 0))
        
        if rec_tot > 0:
            pct_comp = (desp_tot / rec_tot) * 100
            if pct_comp >= 85:
                insights_gerados.append({
                    "tipo": "error",
                    "icone": "🚨",
                    "titulo": "Alerta de Comprometimento",
                    "texto": f"Suas despesas representam **{pct_comp:.1f}%** da sua receita neste período!"
                })
            elif pct_comp <= 50:
                insights_gerados.append({
                    "tipo": "success",
                    "icone": "👏",
                    "titulo": "Excelente Gestão",
                    "texto": f"Você comprometeu apenas **{pct_comp:.1f}%** das suas receitas até agora."
                })

        # 2. Insights sobre as Metas
        if metas_raw:
            for m in metas_raw:
                try:
                    nome_m = m[1]
                    alvo_m = float(m[2])
                    guardado_m = float(m[3])
                    if alvo_m > 0:
                        pct_m = (guardado_m / alvo_m) * 100
                        if pct_m >= 100:
                            insights_gerados.append({
                                "tipo": "success",
                                "icone": "🏆",
                                "titulo": f"Meta Alcanada!",
                                "texto": f"Parabéns! A meta **{nome_m}** atingiu **100%** do objetivo!"
                            })
                        elif pct_m >= 75:
                            insights_gerados.append({
                                "tipo": "info",
                                "icone": "🎯",
                                "titulo": f"Meta {nome_m}",
                                "texto": f"Falta pouco! Você já atingiu **{pct_m:.0f}%** da meta **{nome_m}**."
                            })
                except Exception:
                    pass

        # Exibição dos cards
        if insights_gerados:
            cols_ins = st.columns(min(len(insights_gerados), 3))
            for idx, item in enumerate(insights_gerados[:3]):
                with cols_ins[idx % len(cols_ins)]:
                    msg = f"{item['icone']} **{item['titulo']}**\n\n{item['texto']}"
                    if item["tipo"] == "warning":
                        st.warning(msg)
                    elif item["tipo"] == "success":
                        st.success(msg)
                    elif item["tipo"] == "error":
                        st.error(msg)
                    else:
                        st.info(msg)
        else:
            st.info("💡 **Tudo sob controle**: Não foram detectados alertas críticos para o filtro selecionado.")

    except Exception as e:
        st.error(f"⚠️ Erro ao processar os insights: {e}")

    st.markdown("### 🎯 Progresso do Orçamento Mensal")
    limite_definido = obter_limite_orcamento(st.session_state["usuario_id"])
    if limite_definido > 0:
        porcentagem_gasta = min(float(dados['despesas']) / float(limite_definido), 1.0)
        st.progress(porcentagem_gasta)
        restante = limite_definido - dados['despesas']
        if restante >= 0:
            st.success(f"Você utilizou **{porcentagem_gasta*100:.1f}%** do seu limite. Ainda restam **{fmt_moeda(restante)}** disponíveis.")
        else:
            st.error(f"⚠️ Atenção! Você **estourou** o seu orçamento em **{fmt_moeda(abs(restante))}**.")
    else:
        st.info("💡 Você ainda não definiu um teto de orçamento. Vá na aba '⚙️ Configurações' para estabelecer um limite.")

    st.markdown("---")
    c_graf1, c_graf2 = st.columns(2)
    with c_graf1:
        st.write("### 📈 Fluxo de Caixa Mensal")
        meses, recs, desps = dados_grafico_mensal(st.session_state["usuario_id"], ano_selecionado)
        fig_mensal = go.Figure()
        fig_mensal.add_trace(go.Bar(x=meses, y=recs, name='Receitas', marker_color='#2ecc71'))
        fig_mensal.add_trace(go.Bar(x=meses, y=desps, name='Despesas', marker_color='#e74c3c'))
        fig_mensal.update_layout(barmode='group', height=350, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_mensal, width="stretch")
    with c_graf2:
        st.write("### 🍕 Despesas por Categoria")
        cats, valores = dados_grafico_categorias(st.session_state["usuario_id"], mes_selecionado, ano_selecionado)
        if cats:
            fig_pizza = px.pie(names=cats, values=valores, hole=0.4)
            fig_pizza.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_pizza, width="stretch")
        else:
            st.info("Nenhuma despesa registrada para o período selecionado.")

    # --- SEÇÃO DE GRÁFICOS DE TAGS / EVENTOS ---
    st.markdown("---")
    st.markdown("### 🏷️ Gastos por Tag / Evento")

    tags_retornadas, valores_tags = None, None
    try:
        tags_retornadas, valores_tags = dados_grafico_tags(st.session_state["usuario_id"], mes_selecionado, ano_selecionado)
    except Exception:
        pass

    if tags_retornadas and len(tags_retornadas) > 0:
        df_temp_tags = pd.DataFrame({"Tag": tags_retornadas, "Valor": valores_tags})
        df_temp_tags["Tag_Norm"] = df_temp_tags["Tag"].astype(str).str.strip().str.lower()
        
        df_grouped = df_temp_tags.groupby("Tag_Norm")["Valor"].sum().reset_index()
        df_grouped["Tag"] = df_grouped["Tag_Norm"].apply(lambda t: f"#{t.lstrip('#')}")

        col_t1, col_t2 = st.columns([1.5, 1])
        with col_t1:
            fig_tags = px.pie(
                df_grouped, 
                names="Tag", 
                values="Valor", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_tags.update_traces(textposition='inside', textinfo='percent+label')
            fig_tags.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_tags, width="stretch")
        with col_t2:
            st.write("#### 📋 Detalhamento")
            df_tags_detalhe = pd.DataFrame({
                "Tag": df_grouped["Tag"],
                "Total Gasto": [fmt_moeda(v) for v in df_grouped["Valor"]]
            })
            st.dataframe(df_tags_detalhe, use_container_width=True, hide_index=True)
    else:
        st.info("💡 Nenhuma movimentação com tag registrada para o período selecionado.")

    # --- SEÇÃO DE GRÁFICOS DE METAS NO DASHBOARD ---
    st.markdown("---")
    st.markdown("### 🎯 Progresso das Metas de Economia")

    metas = listar_metas(st.session_state["usuario_id"])

    if metas:
        nomes_metas = [m[1] for m in metas]
        valores_guardados = [float(m[3]) for m in metas]
        valores_alvo = [float(m[2]) for m in metas]

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.write("#### 📊 Comparativo por Meta")
            fig_metas = go.Figure()
            fig_metas.add_trace(go.Bar(
                x=nomes_metas, 
                y=valores_guardados, 
                name='Guardado (R$)', 
                marker_color='#2ecc71'
            ))
            fig_metas.add_trace(go.Bar(
                x=nomes_metas, 
                y=valores_alvo, 
                name='Objetivo (R$)', 
                marker_color='#3498db'
            ))
            fig_metas.update_layout(
                barmode='group', 
                height=350, 
                margin=dict(l=20, r=20, t=20, b=20)
            )
            st.plotly_chart(fig_metas, width="stretch")

        with col_g2:
            st.write("#### 🎯 Conclusão Geral dos Objetivos")
            total_guardado = sum(valores_guardados)
            total_alvo = sum(valores_alvo)
            porcentagem_total = (total_guardado / total_alvo * 100) if total_alvo > 0 else 0

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=porcentagem_total,
                number={'suffix': "%"},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "#2ecc71"},
                    'steps': [
                        {'range': [0, 50], 'color': "#34495e"},
                        {'range': [50, 85], 'color': "#2980b9"}
                    ],
                }
            ))
            fig_gauge.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_gauge, width="stretch")

    else:
        st.info("Nenhuma meta cadastrada até o momento. Cadastre suas metas no menu lateral!")

# --- ABA 2: METAS ---
elif opcao == "🎯 Metas de Economia":
    st.title("🎯 Metas de Economia")
    aba1, aba2 = st.tabs(["📋 Suas Metas", "➕ Criar Nova Meta"])
    
    with aba2:
        with st.form("nova_meta_form", clear_on_submit=True):
            nome_m = st.text_input("Objetivo")
            alvo_m = st.number_input("Valor Alvo (R$)", min_value=1.0)
            prazo_m = st.date_input("Prazo Limite", format="DD/MM/YYYY")
            
            if st.form_submit_button("Salvar Meta") and nome_m:
                criar_meta(st.session_state["usuario_id"], nome_m, alvo_m, prazo_m)
                st.cache_data.clear()
                st.success("Meta criada com sucesso!")
                st.rerun()
                
    with aba1:
        metas = listar_metas(st.session_state["usuario_id"])
        if not metas: 
            st.info("Você ainda não criou nenhuma meta de economia.")
        else:
            for m in metas:
                data_raw = str(m[4])
                try:
                    data_limite_fmt = datetime.strptime(data_raw.replace("/", "-").split("T")[0], "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    data_limite_fmt = data_raw

                st.write(f"### {m[1]} (Até: {data_limite_fmt})")
                st.write(f"Guardado: **{fmt_moeda(m[3])}** de **{fmt_moeda(m[2])}**")
                progresso = min(float(m[3]) / float(m[2]), 1.0) if float(m[2]) > 0 else 0.0
                st.progress(progresso)
                
                col_v, col_b1, col_b2, col_b3 = st.columns([2, 1, 1, 1])

                with col_v:
                    valor_mov = st.number_input(
                        "Valor da movimentação (R$):", 
                        min_value=0.01, 
                        value=100.0, 
                        key=f"val_{m[0]}"
                    )

                with col_b1:
                    st.write("")
                    st.write("")
                    if st.button("➕ Depositar", key=f"dep_{m[0]}", use_container_width=True):
                        novo_saldo = float(m[3]) + valor_mov
                        atualizar_progresso_meta(m[0], novo_saldo)
                        st.cache_data.clear()
                        st.success(f"Guardado +{fmt_moeda(valor_mov)}!")
                        st.rerun()

                with col_b2:
                    st.write("")
                    st.write("")
                    if st.button("➖ Resgatar", key=f"res_{m[0]}", use_container_width=True):
                        if valor_mov > float(m[3]):
                            st.error("O valor de resgate é maior do que o saldo guardado!")
                        else:
                            novo_saldo = float(m[3]) - valor_mov
                            atualizar_progresso_meta(m[0], novo_saldo)
                            st.cache_data.clear()
                            st.success(f"Retirado -{fmt_moeda(valor_mov)}!")
                            st.rerun()

                with col_b3:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Excluir", key=f"del_{m[0]}", use_container_width=True, type="secondary"):
                        if excluir_meta(st.session_state["usuario_id"], m[0]):
                            st.cache_data.clear()
                            st.success(f"Meta '{m[1]}' excluída!")
                            st.rerun()
                        else:
                            st.error("Erro ao excluir a meta no banco.")
                
                st.markdown("---")
                
# --- ABA 3: CONTAS ---
elif opcao == "🏦 Gerir Contas":
    st.title("🏦 Gerenciamento de Contas Bancárias")
    
    OPCOES_BANCOS = [
        "260 - Nubank", "001 - Banco do Brasil", "341 - Itaú Unibanco", 
        "237 - Bradesco", "033 - Santander", "104 - Caixa Econômica Federal", 
        "336 - C6 Bank", "077 - Banco Inter", "380 - PicPay", 
        "000 - Carteira (Dinheiro)", "Outro"
    ]
    
    with st.form("cadastro_conta_form", clear_on_submit=True):
        banco_selecionado = st.selectbox("Escolha o Banco/Conta que deseja criar", OPCOES_BANCOS)
        nome_personalizado = st.text_input("Nome personalizado (Caso escolha 'Outro'):")
        saldo_inicial_input = st.number_input("Saldo Inicial (R$)", value=0.0, step=10.0)
        
        if st.form_submit_button("Cadastrar Conta"):
            nome_final = nome_personalizado.strip() if banco_selecionado == "Outro" else banco_selecionado
            if nome_final:
                # Passa o usuario_id, nome e saldo_inicial para a função
                if cadastrar_conta(st.session_state["usuario_id"], nome_final, saldo_inicial_input):
                    st.success(f"Conta '{nome_final}' cadastrada com sucesso!")
                    st.rerun()
                else:
                    st.error("Erro ao cadastrar conta.")
            else:
                st.error("Por favor, informe o nome da conta.")

    st.markdown("---")
    st.subheader("📋 Contas Cadastradas")
    
    contas_lista = listar_contas(st.session_state["usuario_id"])
    
    if contas_lista:
        for item in contas_lista:
            # Suporta tanto retorno em Dicionário (Supabase API) quanto Tupla/Lista
            if isinstance(item, dict):
                cid = item.get("id")
                cnome = item.get("nome", "Sem Nome")
                csaldo = float(item.get("saldo_inicial", 0.0))
            else:
                cid, cnome, csaldo = item[0], item[1], float(item[2])

            col_c1, col_c2, col_c3 = st.columns([3, 2, 1])
            col_c1.write(f"🔹 **{cnome}**")
            col_c2.write(f"Saldo Inicial: {formatar_moeda_ptbr(csaldo)}")
            
            with col_c3:
                if st.button("Remover", key=f"del_c_{cid}"):
                    if excluir_conta(st.session_state["usuario_id"], cid):
                        st.success("Conta removida.")
                        st.rerun()
                    else:
                        st.error("Erro ao remover conta.")
    else:
        st.info("Nenhuma conta cadastrada ainda.")

# --- ABA 4: MOVIMENTAÇÕES ---
elif opcao == "💸 Lançar Movimentações":
    st.title("💸 Lançar Movimentações")
    
    # 1. Busca a lista de contas do banco
    contas_raw = listar_contas(st.session_state["usuario_id"])
    
    if not contas_raw: 
        st.warning("⚠️ Você precisa cadastrar ao menos uma conta antes de lançar movimentações.")
    else:
        # 2. Mapeia apenas "Nome Exibido": ID_REAL_DO_BANCO
        mapa_contas = {}
        for c in contas_raw:
            if isinstance(c, dict):
                mapa_contas[c.get('nome', 'Conta')] = c['id']
            elif isinstance(c, (list, tuple)):
                mapa_contas[str(c[1])] = c[0]

        # Seleção da Frequência do Lançamento
        modalidade = st.radio(
            "Frequência do Lançamento", 
            ["Único", "Parcelado", "Fixo / Recorrente"], 
            horizontal=True
        )

        tipo_mov = st.selectbox("Tipo de Lançamento", ["Despesa", "Receita"])
        
        # --- SELEÇÃO DE DESCRIÇÃO COM SUPORTE A "OUTROS" ---
        OPCOES_DESCRICAO = [
            "Mercado", "Combustível", "Custo de Casa", "Pix Recebido", "Pix Enviado",
            "Cartão de Débito", "Cartão de Crédito", "Almoço / Jantar / Lanche",
            "Pagamento de Salário", "Conta de Luz", "Assinatura (Netflix, Spotify, etc.)",
            "Conta de Água", "Internet", "Transferência entre Contas", "Outros"
        ]
        
        desc_container = st.container()
        with desc_container:
            desc_selecionada = st.selectbox("Descrição / Histórico", OPCOES_DESCRICAO, key="select_desc_mov")
            
            desc_customizada = ""
            if desc_selecionada == "Outros":
                desc_customizada = st.text_input(
                    "Digite a descrição personalizada:", 
                    placeholder="Ex: Compra na feira", 
                    key="txt_desc_custom"
                )

        # --- SELEÇÃO DE FORMA DE PAGAMENTO E CARTÃO ---
        forma = st.selectbox("Forma de Pagamento", ["Pix", "Dinheiro", "Cartão de Crédito", "Cartão de Débito", "Boleto"])
        
        cartao_id_sel = None
        fechamento_cartao_sel = None
        
        if forma == "Cartão de Crédito":
            cartoes_usuario = listar_cartoes(st.session_state["usuario_id"])
            if cartoes_usuario:
                dict_cartoes = {c["id"]: f"{c['nome_cartao']} (Fecha dia {c['dia_fechamento']})" for c in cartoes_usuario}
                cartao_id_sel = st.selectbox(
                    "Selecione o Cartão de Crédito",
                    options=list(dict_cartoes.keys()),
                    format_func=lambda x: dict_cartoes[x]
                )
                info_cartao_sel = next(c for c in cartoes_usuario if c["id"] == cartao_id_sel)
                fechamento_cartao_sel = info_cartao_sel["dia_fechamento"]
            else:
                st.warning("⚠️ Nenhum cartão cadastrado. Cadastre um cartão na aba '💳 Cartões & Faturas'.")

        # --- FORMULÁRIO DE CADASTRO ---
        with st.form("lancamento_form", clear_on_submit=True, border=False):
            conta_label = st.selectbox("Conta Origem/Destino", list(mapa_contas.keys()))

            col_v, col_q = st.columns(2)
            with col_v:
                val = st.number_input(
                    "Valor da Parcela (R$)" if modalidade == "Parcelado" else "Valor (R$)", 
                    min_value=0.01
                )
            
            num_repeticoes = 1
            with col_q:
                if modalidade == "Parcelado":
                    num_repeticoes = st.number_input("Quantidade de Parcelas", min_value=2, max_value=72, value=2, step=1)
                elif modalidade == "Fixo / Recorrente":
                    num_repeticoes = st.number_input("Repetir por quantos meses?", min_value=2, max_value=60, value=12, step=1)

            cat_sel = st.selectbox("Categoria", CATEGORIAS_DESPADREVAL if tipo_mov == "Despesa" else CATEGORIAS_RECEITAS)
            
            # --- CAMPO DE TAGS ADICIONADO AQUI ---
            tags_input = st.text_input(
                "🏷️ Tags / Etiquetas (Opcional)", 
                placeholder="Ex: #Viagem2026, #Trabalho, #Reforma",
                help="Separe por vírgulas para indicar eventos ou projetos específicos."
            )

                # Pega a data exata no fuso do Brasil
            fuso_br = pytz.timezone("America/Sao_Paulo")
            hoje_br = datetime.now(fuso_br).date()

            # Define o 'value' com a data do Brasil
            data_f = st.date_input("Data da Operação", value=hoje_br, format="DD/MM/YYYY")
            
            enviado = st.form_submit_button("Registrar Transação")
            
            if enviado:
                desc_final = desc_customizada.strip() if desc_selecionada == "Outros" else desc_selecionada

                if desc_selecionada == "Outros" and not desc_final:
                    st.error("Por favor, digite a descrição personalizada.")
                elif forma == "Cartão de Crédito" and not cartao_id_sel:
                    st.error("Por favor, selecione ou cadastre um Cartão de Crédito antes de continuar.")
                else:
                    data_salvar = data_f.strftime("%Y-%m-%d")
                    id_real_conta = mapa_contas[conta_label]
                    
                    # Calcula o mês da fatura se for Cartão de Crédito
                    mes_fatura_calc = None
                    if cartao_id_sel and fechamento_cartao_sel:
                        mes_fatura_calc = calcular_mes_fatura(data_salvar, fechamento_cartao_sel)

                    if modalidade == "Parcelado":
                        sucesso = salvar_movimentacao_parcelada(
                            usuario_id=st.session_state["usuario_id"],
                            conta_id=id_real_conta,
                            descricao=desc_final,
                            valor=val,
                            tipo=tipo_mov,
                            forma_pagamento=forma,
                            parcelas=int(num_repeticoes),
                            data_base=data_salvar,
                            categoria=cat_sel,
                            cartao_id=cartao_id_sel,
                            dia_fechamento=fechamento_cartao_sel,
                            tags=tags_input  # <--- PASSANDO TAGS
                        )
                    elif modalidade == "Fixo / Recorrente":
                        sucesso = salvar_movimentacao_recorrente(
                            usuario_id=st.session_state["usuario_id"],
                            conta_id=id_real_conta,
                            descricao=desc_final,
                            valor=val,
                            tipo=tipo_mov,
                            forma_pagamento=forma,
                            meses=int(num_repeticoes),
                            data_base=data_salvar,
                            categoria=cat_sel,
                            cartao_id=cartao_id_sel,
                            dia_fechamento=fechamento_cartao_sel,
                            tags=tags_input  # <--- PASSANDO TAGS
                        )
                    else:
                        sucesso = salvar_movimentacao(
                            usuario_id=st.session_state["usuario_id"], 
                            conta_id=id_real_conta, 
                            descricao=desc_final, 
                            valor=val, 
                            tipo=tipo_mov, 
                            forma_pagamento=forma, 
                            data_str=data_salvar, 
                            categoria=cat_sel,
                            cartao_id=cartao_id_sel,
                            mes_fatura=mes_fatura_calc,
                            tags=tags_input  # <--- PASSANDO TAGS
                        )
                    
                    if sucesso:
                        st.cache_data.clear()
                        st.success(f"Transação ({modalidade}) salva com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar a transação no banco de dados.")

    # --- SEÇÃO DE LANÇAMENTOS RECENTES ---
    st.markdown("---")
    st.subheader("🕒 Lançamentos Recentes")
    
    dados_recentes = buscar_todas_movimentacoes(st.session_state["usuario_id"], "Todos", "Todos")
    
    if dados_recentes:
        df_recentes = pd.DataFrame(
            dados_recentes, 
            columns=["ID", "Data", "Conta", "Tipo", "Forma Pagto", "Descrição", "Valor", "Categoria"]
        )
        
        # Ordena estritamente do ID mais recente (maior) para o mais antigo (menor)
        df_recentes["ID"] = pd.to_numeric(df_recentes["ID"])
        df_recentes = df_recentes.sort_values(by="ID", ascending=False)
        
        # Formatação para exibição
        df_exibicao = df_recentes.copy()
        df_exibicao["Valor"] = df_exibicao["Valor"].apply(lambda v: fmt_moeda(v))
        df_exibicao["Data"] = pd.to_datetime(df_exibicao["Data"]).dt.strftime('%d/%m/%Y')
        
        # Tabela rolável de dados
        with st.container(height=300):
            st.dataframe(df_exibicao, width="stretch", hide_index=True)

        # --- ÁREA DE EXCLUSÃO DE REGISTRO ---
        st.markdown("#### 🗑️ Excluir Lançamento Incorreto")
        col_del_1, col_del_2 = st.columns([3, 1])
        
        with col_del_1:
            # Garante que os IDs sejam inteiros para o selectbox
            ids_disponiveis = [int(i) for i in df_recentes["ID"].tolist()]
            id_para_deletar = st.selectbox(
                "Selecione o ID da transação que deseja remover:", 
                ids_disponiveis,
                key="select_del_id"
            )
            
        with col_del_2:
            st.write("") # Espaçamento vertical para alinhar o botão
            st.write("") 
            if st.button("🗑️ Excluir", use_container_width=True, type="secondary"):
                id_limpo = int(id_para_deletar)
                
                # Chamada com a ordem correta (usuario_id, mov_id)
                if excluir_movimentacao(
                    usuario_id=st.session_state["usuario_id"], 
                    mov_id=id_limpo
                ):
                    st.cache_data.clear() # Limpa caches ativos para sincronizar a tabela
                    st.success(f"Lançamento ID {id_limpo} excluído com sucesso!")
                    st.rerun()
                else:
                    st.error("Não foi possível excluir o lançamento selecionado.")
    else:
        st.info("Nenhuma movimentação cadastrada até o momento.")

# --- ABA 5: EXTRATO DETALHADO ---
elif opcao == "📋 Extrato Detalhado":
    st.title("📋 Extrato Detalhado de Transações")
    
    # Lista de meses por extenso
    opcoes_meses = [
        "Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    
    col_e1, col_e2 = st.columns(2)
    with col_e1: 
        mes_nome_extrato = st.selectbox(
            "Filtrar Mês", 
            opcoes_meses, 
            index=datetime.now().month  # Seleciona o mês atual por padrão
        )
        
        # Converte o nome do mês para o formato numérico esperado ("Todos" ou "01", "02", ...)
        if mes_nome_extrato == "Todos":
            mes_extrato = "Todos"
        else:
            mes_extrato = f"{opcoes_meses.index(mes_nome_extrato):02d}"

    with col_e2: 
        ano_extrato = st.selectbox("Filtrar Ano", ["Todos", "2026", "2027", "2028", "2029", "2030"], index=1)
        
    dados_banco = buscar_todas_movimentacoes(st.session_state["usuario_id"], mes_extrato, ano_extrato)
    
    if dados_banco:
        st.write("### 📥 Exportar Relatórios")
        c_btn1, c_btn2, _ = st.columns([1.5, 1.5, 4])
        
        with c_btn1:
            excel_data = gerar_excel_profissional(dados_banco, mes_extrato, ano_extrato)
            st.download_button(
                label="🟢 Baixar Excel (.xlsx)",
                data=excel_data,
                file_name=f"extrato_financeiro_{mes_extrato}_{ano_extrato}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )
            
        with c_btn2:
            pdf_data = gerar_pdf_profissional(dados_banco, mes_extrato, ano_extrato)
            st.download_button(
                label="🔴 Baixar PDF Relatório",
                data=pdf_data,
                file_name=f"extrato_financeiro_{mes_extrato}_{ano_extrato}.pdf",
                mime="application/pdf",
                width="stretch"
            )
            
        st.markdown("---")

        # Ajuste para carregar a coluna Tags caso esteja no banco
        colunas = ["ID", "Data", "Conta", "Tipo", "Forma Pagto", "Descrição", "Valor", "Categoria", "Tags"]
        
        df = pd.DataFrame(dados_banco)
        if df.shape[1] == len(colunas):
            df.columns = colunas
        else:
            df = pd.DataFrame(dados_banco, columns=["ID", "Data", "Conta", "Tipo", "Forma Pagto", "Descrição", "Valor", "Categoria"])
            df["Tags"] = ""

        # Filtro opcional por Tags
        todas_tags = set()
        for t in df["Tags"].dropna():
            if t:
                todas_tags.update([x.strip() for x in str(t).split(",") if x.strip()])

        if todas_tags:
            tags_sel = st.multiselect("🏷️ Filtrar por Tag / Evento", sorted(list(todas_tags)))
            if tags_sel:
                df = df[df["Tags"].astype(str).apply(lambda x: any(tag.lower() in x.lower() for tag in tags_sel))]

        df["Valor"] = df["Valor"].apply(lambda v: fmt_moeda(v))

        # Formata a data para o padrão brasileiro na telaz
        df["Data"] = pd.to_datetime(df["Data"]).dt.strftime('%d/%m/%Y')

        st.dataframe(df, width="stretch", hide_index=True)
        
        st.markdown("---")
        st.write("#### 🛠️ Operações Avançadas")
        id_excluir = st.number_input("Deseja deletar algum lançamento? Digite o ID dele aqui:", min_value=0, step=1)
        if st.button("Excluir Lançamento") and id_excluir > 0:
            excluir_movimentacao(st.session_state["usuario_id"], id_excluir)
            st.success(f"Movimentação {id_excluir} excluída!")
            st.rerun()
    else:
        st.info("Nenhuma movimentação encontrada para o período filtrado.")

# --- ABA 6: CONFIGURAÇÕES ---
elif opcao == "⚙️ Configurações":
    st.title("⚙️ Painel de Configurações")
    st.write("### 🎯 Orçamento Global de Despesas")
    limite_atual = obter_limite_orcamento(st.session_state["usuario_id"])
    st.write(f"Seu Limite de Gastos Alvo Atual: **{fmt_moeda(limite_atual)}**")
    
    n_limite = st.number_input("Definir novo teto de orçamento (R$):", value=float(limite_atual))
    if st.button("Atualizar Limite"):
        definir_limite_orcamento(st.session_state["usuario_id"], n_limite)
        st.success("Teto do orçamento updated com sucesso!")
        st.rerun()
        
    st.markdown("---")
    st.write("### 🔒 Alteração de Credenciais")
    with st.form("alterar_senha_form"):
        nova_senha = st.text_input("Nova Senha de Acesso:", type="password")
        if st.form_submit_button("Alterar Senha"):
            if nova_senha:
                senha_hash = hashlib.sha256(nova_senha.encode('utf-8')).hexdigest()
                if alterar_senha_usuario(st.session_state["usuario_id"], senha_hash):
                    st.success("Senha modificada com sucesso!")
                else:
                    st.error("Erro operacional ao atualizar senha.")
            else:
                st.error("Digite uma senha válida.")

# --- ABA: ORÇAMENTOS POR CATEGORIA ---
elif opcao == "🎯 Orçamentos por Categoria":
    st.title("📊 Dashboard de Orçamentos e Limites")

    # --- FILTRO DE MÊS E ANO ---
    hoje = datetime.now().date()
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        mes_sel = st.selectbox(
            "📅 Mês", 
            options=list(range(1, 13)), 
            index=hoje.month - 1, 
            format_func=lambda m: ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][m-1]
        )
    with col_f2:
        ano_sel = st.number_input("📆 Ano", min_value=2020, max_value=2035, value=hoje.year)

    # 1. Busca dados iniciais
    uid = st.session_state["usuario_id"]
    limite_geral = obter_limite_orcamento(uid)
    limites_dict = obter_limites_por_categoria(
        uid
    )  # Esperado dict { 'Categoria': limite } ou { 'Categoria': {'id': x, 'limite': y} }
    movs_todas = buscar_todas_movimentacoes(uid, "Todos", "Todos")

    # Processa total de gastos por categoria
    gastos_por_cat = {}
    if movs_todas:
        df_m = pd.DataFrame(
            movs_todas,
            columns=[
                "ID",
                "Data",
                "Conta",
                "Tipo",
                "Forma Pagto",
                "Descrição",
                "Valor",
                "Categoria",
            ],
        )
        df_despesas = df_m[df_m["Tipo"] == "Despesa"].copy()
        if not df_despesas.empty:
            # Converte a coluna Data para o formato datetime
            df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors="coerce")
            
            # Filtra conforme Mês e Ano selecionados
            df_despesas = df_despesas[
                (df_despesas["Data"].dt.month == mes_sel) & 
                (df_despesas["Data"].dt.year == ano_sel)
            ]
            
            df_despesas["Valor"] = pd.to_numeric(
                df_despesas["Valor"], errors="coerce"
            )
            gastos_por_cat = (
                df_despesas.groupby("Categoria")["Valor"].sum().to_dict()
            )

    # --- DASHBOARD VISUAL (MÉTRICAS GERAIS) ---
    total_orcado = sum(
        v if isinstance(v, (int, float)) else v.get("limite", 0.0)
        for v in limites_dict.values()
    )
    total_gasto = sum(
        gastos_por_cat.get(cat, 0.0) for cat in limites_dict.keys()
    )
    saldo_restante = total_orcado - total_gasto

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("🎯 Total Orçado", fmt_moeda(total_orcado))
    col_m2.metric("💸 Total Gasto", fmt_moeda(total_gasto))
    col_m3.metric(
        "💰 Saldo Restante",
        fmt_moeda(saldo_restante),
        delta=fmt_moeda(saldo_restante),
        delta_color="normal" if saldo_restante >= 0 else "inverse",
    )

    if limite_geral > 0:
        st.info(
            f"💡 Seu teto global cadastrado no sistema é de **{fmt_moeda(limite_geral)}**"
        )

    st.markdown("---")
    col_cad, col_vis = st.columns([1, 2])

    # --- PAINEL GRÁFICO (DASHBOARD) ---
    if limites_dict:
        st.subheader("📈 Visão Geral dos Orçamentos")

        # Prepara dados para o gráfico
        dados_grafico = []
        for cat, dados in limites_dict.items():
            lim = (
                float(dados.get("limite", 0.0))
                if isinstance(dados, dict)
                else float(dados)
            )
            gst = float(gastos_por_cat.get(cat, 0.0))
            dados_grafico.append(
                {"Categoria": cat, "Gasto Atual": gst, "Limite": lim}
            )

        df_chart = pd.DataFrame(dados_grafico)

        if not df_chart.empty:
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.markdown("**Comparativo: Gasto vs. Limite**")
                # Gráfico de barras lado a lado
                st.bar_chart(
                    df_chart.set_index("Categoria")[["Gasto Atual", "Limite"]],
                    height=250,
                )

            with col_g2:
                st.markdown("**Distribuição do Teto Orçado**")
                # Gráfico de rosca simples via st.bar_chart horizontal
                st.bar_chart(
                    df_chart.set_index("Categoria")["Limite"],
                    horizontal=True,
                    height=250,
                )

        st.markdown("---")

    # --- LADO ESQUERDO: FORMULÁRIO DE CADASTRO ---
    with col_cad:
        with st.form("form_orcamento", clear_on_submit=True):
            st.subheader("⚙️ Definir Limite")
            cat_orc = st.selectbox("Categoria", CATEGORIAS_DESPADREVAL)
            limite_val = st.number_input(
                "Teto Mensal (R$)", min_value=10.0, value=500.0, step=50.0
            )

            if st.form_submit_button(
                "Salvar Limite", use_container_width=True
            ):
                if salvar_orcamento_categoria(uid, cat_orc, limite_val):
                    st.cache_data.clear()
                    st.success(
                        f"Limite para '{cat_orc}' atualizado com sucesso!"
                    )
                    st.rerun()
                else:
                    st.error("Erro ao salvar limite no banco de dados.")

    # --- LADO DIREITO: ACOMPANHAMENTO, ALTERAÇÃO E EXCLUSÃO ---
    with col_vis:
        st.subheader("📈 Acompanhamento de Gastos")

        if not limites_dict:
            st.info(
                "Nenhum limite por categoria cadastrado ainda. Defina um no formulário ao lado!"
            )
        else:
            for cat_nome, dados_limite in limites_dict.items():
                # Trata estrutura caso o dict venha simples ou com ID para exclusão
                if isinstance(dados_limite, dict):
                    limite = float(dados_limite.get("limite", 0.0))
                    orc_id = dados_limite.get("id")
                else:
                    limite = float(dados_limite)
                    orc_id = cat_nome

                gasto_atual = float(gastos_por_cat.get(cat_nome, 0.0))
                porcentagem = min(gasto_atual / limite, 1.0) if limite > 0 else 0.0

                # Indicadores de Alerta
                if gasto_atual > limite:
                    status = f"🔴 **ESTOURADO!** Excedeu em {fmt_moeda(gasto_atual - limite)}"
                elif porcentagem >= 0.85:
                    status = f"🟡 **Atenção!** Restam apenas {fmt_moeda(limite - gasto_atual)}"
                else:
                    status = f"🟢 **Dentro do Limite.** Restam {fmt_moeda(limite - gasto_atual)}"

                # Bloco Interativo com Expander
                with st.expander(
                    f"📌 **{cat_nome}**: {fmt_moeda(gasto_atual)} / **{fmt_moeda(limite)}**"
                ):
                    st.progress(porcentagem)
                    st.caption(status)

                    st.markdown("---")
                    st.write("**Ações do Orçamento:**")
                    col_e1, col_e2 = st.columns(2)

                    # Novo Teto para Alteração rápida
                    novo_teto = col_e1.number_input(
                        "Alterar Limite (R$)",
                        min_value=10.0,
                        value=limite,
                        step=50.0,
                        key=f"edit_{cat_nome}",
                    )

                    if col_e1.button("💾 Salvar Alteração", key=f"btn_save_{cat_nome}"):
                        if salvar_orcamento_categoria(uid, cat_nome, novo_teto):
                            st.cache_data.clear()
                            st.success(f"Limite de {cat_nome} atualizado!")
                            st.rerun()
                        else:
                            st.error("Erro ao alterar limite.")

                    # Botão de Excluir
                    if col_e2.button(
                        "🗑️ Excluir Orçamento",
                        key=f"btn_del_{cat_nome}",
                        type="secondary",
                    ):
                        if excluir_orcamento_categoria(uid, cat_nome):
                            st.cache_data.clear()
                            st.success(f"Orçamento de {cat_nome} removido!")
                            st.rerun()
                        else:
                            st.error("Erro ao excluir orçamento.")
# --- ABA: PRÓXIMOS VENCIMENTOS ---
elif opcao == "📅 Próximos Vencimentos":
    st.title("📅 Próximos Vencimentos")
    st.caption(
        "Acompanhe despesas e contas com vencimento nos próximos dias e realize baixas rápidas."
    )

    # Controle deslizante
    dias_filtro = st.slider(
        "Visualizar vencimentos para os próximos (dias):",
        min_value=5,
        max_value=60,
        value=15,
        step=5,
    )

    # Busca os lançamentos
    vencimentos = buscar_vencimentos_proximos(
        st.session_state["usuario_id"], dias=dias_filtro
    )

    if not vencimentos:
        st.success(
            f"🎉 Nenhuma despesa registrada para os próximos {dias_filtro} dias!"
        )
    else:
        df_venc = pd.DataFrame(vencimentos)

        # Garante o campo de pago tratado
        if "pago" not in df_venc.columns:
            df_venc["pago"] = False
        else:
            df_venc["pago"] = df_venc["pago"].fillna(False)

        # Separa os dataframes entre Pendentes e Pagos
        df_pendentes = df_venc[df_venc["pago"] == False].copy()
        df_pagos = df_venc[df_venc["pago"] == True].copy()

        # --- CARDS RESUMO (KPIs) ---
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        with col_kpi1:
            st.metric(
                "Total Pendente no Período",
                fmt_moeda(df_pendentes["valor"].sum()) if not df_pendentes.empty else "R$ 0,00",
            )
        with col_kpi2:
            st.metric("Contas a Vencer", len(df_pendentes))
        with col_kpi3:
            st.metric("Contas Já Pagas", len(df_pagos))

        st.markdown("---")

        # --- SEÇÃO 1: CONTAS PENDENTES ---
        st.subheader(f"⏳ Contas Pendentes ({len(df_pendentes)})")

        if df_pendentes.empty:
            st.success("🎉 Nenhuma conta pendente para o período selecionado!")
        else:
            df_pendentes["Valor_Fmt"] = df_pendentes["valor"].apply(lambda v: fmt_moeda(v))
            df_pendentes["Data_Fmt"] = pd.to_datetime(df_pendentes["data"]).dt.strftime("%d/%m/%Y")
            hoje_dt = pd.to_datetime("today").normalize()
            df_pendentes["Dias_Restantes"] = (pd.to_datetime(df_pendentes["data"]) - hoje_dt).dt.days

            for _, row in df_pendentes.iterrows():
                id_lanc = row["id"]
                dias = int(row["Dias_Restantes"])

                if dias == 0:
                    badge = "⚠️ **VENCE HOJE!**"
                elif dias < 0:
                    badge = f"🚨 **VENCIDA HÁ {abs(dias)} DIA(S)!**"
                else:
                    badge = f"⏳ Vence em {dias} dia(s)"

                with st.expander(
                    f"📅 {row['Data_Fmt']} — {row['descricao']} | {row['Valor_Fmt']}"
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Categoria:** {row.get('categoria', 'Não informada')}")
                        st.write(f"**Forma de Pagamento:** {row.get('forma_pagamento', 'Não informada')}")
                    with c2:
                        st.write(f"**Status:** {badge}")

                    st.markdown("---")
                    col_btn_pago, col_btn_del, _ = st.columns([2, 1, 3])

                    with col_btn_pago:
                        if st.button(
                            "✅ Marcar como Pago",
                            key=f"pago_{id_lanc}",
                            type="primary",
                            use_container_width=True,
                        ):
                            if marcar_lancamento_como_pago(id_lanc):
                                st.cache_data.clear()
                                st.success("Lançamento baixado com sucesso!")
                                st.rerun()
                            else:
                                st.error("Erro ao registrar pagamento.")

                    with col_btn_del:
                        if st.button(
                            "🗑️ Excluir",
                            key=f"del_venc_{id_lanc}",
                            use_container_width=True,
                        ):
                            if excluir_lancamento_pendente(id_lanc):
                                st.cache_data.clear()
                                st.warning("Lançamento removido!")
                                st.rerun()
                            else:
                                st.error("Erro ao excluir lançamento.")

        # --- SEÇÃO 2: CONTAS JÁ PAGAS ---
        if not df_pagos.empty:
            st.markdown("---")
            with st.expander(f"✅ Ver Contas Já Pagas no Período ({len(df_pagos)})"):
                df_pagos["Valor_Fmt"] = df_pagos["valor"].apply(lambda v: fmt_moeda(v))
                df_pagos["Data_Fmt"] = pd.to_datetime(df_pagos["data"]).dt.strftime("%d/%m/%Y")

                for _, row in df_pagos.iterrows():
                    id_lanc = row["id"]
                    
                    col_info, col_btn = st.columns([3, 1])
                    
                    with col_info:
                        st.write(
                            f"✔️ **{row['Data_Fmt']}** — {row['descricao']} | **{row['Valor_Fmt']}**"
                        )
                    
                    with col_btn:
                        if st.button(
                            "↩️ Desfazer",
                            key=f"desfazer_{id_lanc}",
                            use_container_width=True,
                            help="Voltar esta conta para o status Pendente"
                        ):
                            if desfazer_pagamento_lancamento(id_lanc):
                                st.cache_data.clear()
                                st.warning("Pagamento estornado! Conta voltou para Pendentes.")
                                st.rerun()
                            else:
                                st.error("Erro ao desfazer pagamento.")                    


# --- ABA: CARTÕES & FATURAS ---
elif opcao == "💳 Cartões & Faturas":
    st.title("💳 Gestão de Cartões de Crédito & Faturas")

    tab_faturas, tab_novo_cartao, tab_gerenciar = st.tabs([
        "📄 Minhas Faturas", 
        "➕ Cadastrar Novo Cartão", 
        "⚙️ Gerenciar Cartões"
    ])

    user_id = st.session_state.get("usuario_id")
    cartoes = listar_cartoes(user_id)

# --- ABA 1: VISUALIZAR FATURAS ---
    with tab_faturas:
        if cartoes:
            c1, c2, c3 = st.columns(3)

            with c1:
                dict_cartoes = {c["id"]: c.get("nome_cartao") or c.get("nome") for c in cartoes}
                cartao_id_sel = st.selectbox(
                    "Escolha o Cartão",
                    options=list(dict_cartoes.keys()),
                    format_func=lambda x: dict_cartoes[x],
                    key="sel_cartao_fatura"
                )
                cartao_info = next(c for c in cartoes if c["id"] == cartao_id_sel)

            with c2:
                meses = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
                mes_fatura = st.selectbox("Mês da Fatura", meses, index=datetime.now().month - 1)

            with c3:
                ano_fatura = st.selectbox("Ano da Fatura", ["2026", "2027", "2028"], index=0)

            fatura_ref = f"{mes_fatura}/{ano_fatura}"
            st.markdown("---")

            # Busca gastos vinculados a essa fatura no banco
            compras = buscar_gastos_fatura(user_id, cartao_id_sel, fatura_ref)
            total_fatura = sum(float(item["valor"]) for item in compras) if compras else 0.0
            limite_total = float(cartao_info["limite"])
            limite_disponivel = limite_total - total_fatura

            st.info(f"💡 **Informações:** Fechamento todo **dia {cartao_info['dia_fechamento']}** | Vencimento todo **dia {cartao_info['dia_vencimento']}**")

            # Métricas em destaque
            m1, m2, m3 = st.columns(3)
            m1.metric("Total da Fatura", formatar_moeda_ptbr(total_fatura))
            m2.metric("Limite Disponível", formatar_moeda_ptbr(limite_disponivel))
            m3.metric("Limite Total", formatar_moeda_ptbr(limite_total))

            st.write(f"### 🛒 Compras da Fatura ({fatura_ref})")
            
            if compras:
                if st.button("✅ Dar Baixa / Pagar Fatura Completa", type="primary"):
                    if dar_baixa_fatura_completa(user_id, cartao_id_sel, fatura_ref):
                        st.success(f"Fatura {fatura_ref} marcada como paga com sucesso!")
                        st.rerun()

                st.dataframe(
                    compras,
                    column_order=["data", "descricao", "categoria", "tags", "valor", "pago"],
                    use_container_width=True
                )

                # --- FERRAMENTA DE EXCLUSÃO DE ITEM DA FATURA ---
                with st.expander("🗑️ Excluir um item desta fatura"):
                    # Cria um dicionário identificando cada compra
                    dict_compras_excluir = {
                        item["id"]: f"{item['data']} | {item['descricao']} - R$ {float(item['valor']):.2f}" 
                        for item in compras
                    }
                    
                    id_para_excluir = st.selectbox(
                        "Selecione o lançamento que deseja remover:",
                        options=list(dict_compras_excluir.keys()),
                        format_func=lambda x: dict_compras_excluir[x],
                        key="select_excluir_fatura_item"
                    )
                    
                    if st.button("Confirmar Exclusão do Item", type="secondary"):
                        if excluir_movimentacao(user_id, id_para_excluir): # <--- Passando user_id e o id da movimentação
                            st.success("Lançamento excluído com sucesso!")
                            st.rerun()
                        else:
                            st.error("Erro ao excluir o lançamento no banco de dados.")

            else:
                st.warning(f"Nenhum gasto encontrado para a fatura de {fatura_ref}.")

        else:
            st.info("Nenhum cartão cadastrado. Use a aba ao lado para cadastrar seu primeiro cartão!")

    # --- ABA 2: CADASTRO DE NOVO CARTÃO ---
    with tab_novo_cartao:
        st.subheader("➕ Adicionar Novo Cartão de Crédito")
        
        with st.form("form_cartao"):
            opcoes_bancos = [
                "260 - Nubank",
                "001 - Banco do Brasil",
                "341 - Itaú Unibanco",
                "237 - Bradesco",
                "033 - Santander",
                "104 - Caixa Econômica Federal",
                "336 - C6 Bank",
                "077 - Banco Inter",
                "380 - PicPay",
                "208 - BTG Pactual",
                "102 - XP Investimentos",
                "Outro"
            ]

            nome_cartao_selecionado = st.selectbox(
                "Nome do Cartão",
                options=opcoes_bancos,
                index=0
            )

            nome_outro = st.text_input("Se selecionou 'Outro', digite o nome do cartão:")

            if nome_cartao_selecionado == "Outro":
                nome_c = nome_outro
            else:
                nome_c = nome_cartao_selecionado

            limite_c = st.number_input("Limite de Crédito Total (R$)", min_value=0.0, value=1000.0, step=100.0)

            c_f, c_v = st.columns(2)
            with c_f:
                fechamento_c = st.number_input("Dia do Fechamento", min_value=1, max_value=31, value=20)
            with c_v:
                vencimento_c = st.number_input("Dia do Vencimento", min_value=1, max_value=31, value=30)

            btn_salvar = st.form_submit_button("Salvar Cartão")

            if btn_salvar:
                if nome_c.strip():
                    if cadastrar_cartao(user_id, nome_c, limite_c, fechamento_c, vencimento_c):
                        st.success(f"Cartão '{nome_c}' cadastrado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao cadastrar cartão no banco de dados.")
                else:
                    st.error("Por favor, informe ou digite o nome do cartão.")

    # --- ABA 3: GERENCIAR (ALTERAR LIMITE E EXCLUIR) ---
    with tab_gerenciar:
        st.subheader("⚙️ Alterar Limite ou Excluir Cartão")
        
        if cartoes:
            dict_cartoes_g = {c["id"]: c.get("nome_cartao") or c.get("nome") for c in cartoes}
            cartao_id_ger = st.selectbox(
                "Selecione o Cartão para Configurar",
                options=list(dict_cartoes_g.keys()),
                format_func=lambda x: dict_cartoes_g[x],
                key="sel_cartao_gerenciar"
            )
            
            cartao_sel_info = next(c for c in cartoes if c["id"] == cartao_id_ger)
            
            st.markdown("---")
            
            # --- Bloco 1: Alterar Limite ---
            col_lim1, col_lim2 = st.columns([2, 1])
            with col_lim1:
                novo_limite = st.number_input(
                    "Novo Limite Total (R$)",
                    min_value=0.0,
                    value=float(cartao_sel_info["limite"]),
                    step=100.0,
                    key="input_novo_limite"
                )
            with col_lim2:
                st.write("") # Espaçamento
                st.write("")
                if st.button("✏️ Atualizar Limite", use_container_width=True):
                    if atualizar_limite_cartao(user_id, cartao_id_ger, novo_limite):
                        st.success("Limite atualizado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar o limite.")

            st.markdown("---")

            # --- Bloco 2: Excluir Cartão ---
            st.warning("⚠️ **Zona de Perigo:** Excluir um cartão apaga as configurações dele.")
            if st.button("🗑️ Excluir Cartão", type="primary"):
                if excluir_cartao(user_id, cartao_id_ger):
                    st.success("Cartão excluído com sucesso!")
                    st.rerun()
                else:
                    st.error("Erro ao excluir o cartão.")
        else:
            st.info("Nenhum cartão para gerenciar.")