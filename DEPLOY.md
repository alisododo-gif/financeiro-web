FinanceiroPro Web - Telegram v2

# FinanceiroPro Web pelo Telegram

O bot usa os mesmos usuários, vínculos e dados do Supabase. Todo atendimento ocorre na conversa privada. O vínculo ativo é revalidado em cada mensagem e botão; a própria função financeira valida o proprietário novamente ao gravar.

## Jornada de uma despesa

Enviar `10` inicia uma despesa. Botões escolhem Pix, débito, boleto, crédito ou dinheiro. Pix/débito/boleto/dinheiro usam contas do usuário (seleção automática se houver somente uma). Crédito sempre mostra os cartões do usuário. As opções seguintes são à vista, parcelado no crédito, ou fixo/recorrente. O usuário preenche descrição, data, categoria e tags opcionais; lançamentos únicos perguntam se já estão pagos. Parcelados e recorrentes começam pendentes. Nada é gravado sem a confirmação final, que informa valores e arredondamento.

## Módulos

Menu: receitas, despesas, lançamentos, cartões/faturas, recebimentos, clientes, contas, metas, orçamentos, resumo e vencimentos. Cadastros e alterações possuem perguntas guiadas, listagem paginada, busca e confirmação. Lançamentos permitem alterar descrição, valor, data, categoria, tags, pagamento e conta/cartão; o banco recalcula a competência quando necessário. Faturas mostram gasto por competência e limite disponível com todas as parcelas pendentes. A baixa registra pagamento no sistema, sem executar pagamento bancário.

Lembretes de 9h/15h e resumo mensal permanecem na mesma instância do Discloud, com os horários existentes. As consultas de lembretes exigem vínculo ativo e consistente. Não há API de inteligência artificial paga nem obrigação de acessar o site para as operações financeiras.

## Proteções

- Backend fixo `public.fp_financeiro_v1`, igual ao web; ID do proprietário nunca vem do texto ou do botão.
- Confirmações com versão do registro e UUID: repetição após falha de rede não duplica gravações.
- Botões têm token de conversa e revisão, expiram após duas horas ou reinício, e são invalidados após cada passo.
- Contatos de terceiros/encaminhados, grupos, contas inativas e vínculos ambíguos são recusados.
- Nenhuma senha, token ou resposta completa do banco aparece em logs ou botões.
- Administração global, credenciais, exportação e restauração completa de banco permanecem no acesso administrativo existente; não são expostos no chat do bot.

Código anterior conservado em `migration/bot_before_buttons.py` e pacote anterior protegido como rollback. O pacote novo não inclui `.env` ou dados de usuários. Testes de fluxo usam repositório simulado, sem enviar mensagens ou alterar registros reais. A inicialização no Discloud valida a RPC apenas em leitura.
