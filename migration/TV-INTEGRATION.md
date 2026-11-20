# TV — integração gratuita exclusiva do proprietário

## Estado

- FinanceiroPro Web: https://financeiroproweb.pages.dev/
- Origem: https://painel.newbr.top/#/customers — conta já autorizada no navegador.
- Supabase: projeto hkfyvhthfshnddduckjs.
- Proprietário configurado: financeiropro_operacoes.tv_integration_owner; atualmente usuario_id 1, informado pelo usuário no link do atalho e conferido na sessão.
- Em 16/10/2026 foram importados 43 IDs únicos, um com WhatsApp e 42 sem. Os 18 cadastros anteriores foram preservados. Nenhum registro foi importado para outro usuário.
- API paga de Revenda recusada pelo usuário. Não ativar nem contratar.
- A leitura diária pelo navegador foi reativada em 18/10/2026 por nova solicitação do proprietário. Automação atualizar-clientes-de-tv-do-alison ativa diariamente às 09:00 (America/Cuiaba), com prévia e escopo exclusivo do proprietário. Piloto Discloud excluído; não reativar. API paga continua recusada.

## Sincronização diária autorizada

1. Leia este arquivo e as skills aplicáveis. Use somente o navegador autorizado para consultar o painel. Não leia cookies, senha, tokens, playlists ou estado interno do aplicativo.
2. Se a sessão expirou, pare e peça que o usuário entre novamente. Não contorne proteções. Não ative integrações pagas. Não renove, pague, exclua, migre ou altere clientes na origem.
3. Abra Clientes; mude para tabela. No controle visível items-per-page, selecione 100, ou percorra todas as páginas se a quantidade superar o limite. Confira quantidade total e IDs únicos. Nunca trate uma página parcial como a lista completa.
4. No DOM renderizado, cada linha de cliente tem um link #/customers/edit/ID na primeira célula; extraia o ID, o usuário, o plano, a situação de origem, o valor e o primeiro vencimento da segunda célula. Converta dd/mm/aaaa em aaaa-mm-dd. Não confunda com a data de criação. Leia contatos apenas para clientes novos, se necessário; telefones personalizados existentes serão preservados.
5. Payload permitido: array com origem_id, nome (usuário da origem), telefone (string vazia se ausente), valor numérico com centavos, data_vencimento, plano, situacao_origem. Não inclua href, credenciais ou dados fora dessa lista.
6. Consulte o proprietário configurado, confira que é o autorizado e use public.fp_clientes_tv_v1(p_usuario,p_registros,false) como prévia via conector Supabase. O servidor e a função rejeitam outros usuários. Se novos=0, atualizados=0 e não houver exclusões confirmadas, não aplique nem notifique.
7. Havendo mudanças, use a mesma função com p_aplicar=true. Essa atualização de cadastros foi autorizada para a rotina diária. Ela preserva id local, nome, telefone, status de pagamento e conta; atualiza vencimento, valor e referência de origem; cria novos clientes pendentes. Nunca crie receitas/despesas ou marque pagamentos automaticamente.
8. Confira contagem de IDs únicos, owner e resultado. Por nova autorização explícita de 18/10/2026, clientes importados excluídos na origem devem ser excluídos no FinanceiroPro, seguindo as verificações abaixo. Avise somente mudanças aplicadas ou impedimentos; nunca envie cobranças pelo WhatsApp ou Telegram.

## Web e atalho

- Só o proprietário vê Importar / atualizar TV em Clientes. Há prévia antes de gravar.
- POST /api/clientes/importar-tv exige sessão, origem, módulo Clientes, integração habilitada e validação do lote. GET /api/clientes/integracao-tv retorna apenas enabled.
- Cada card mantém o ID FinanceiroPro e referencia_tv.id/usuario. A edição de nome/telefone é local; telefone pode ficar vazio nos importados. Cadastros sem telefone não entram na cobrança de TV.
- A URL clientes_cobrar_amanha e as colunas nome,telefone,valor foram preservadas. Para todos os clientes, a consulta considera a data completa de amanhã e exige telefone válido preenchido. Não há repetição automática pelo dia do mês. Não tornar consultas públicas nem expor service_role para permitir atalhos.
- Outros links informados pelo usuário permanecem: usuarios, faturas_vencendo_hoje, movimentacoes_hoje, recebimentos_hoje. O envio pelo atalho do iPhone não foi executado neste trabalho.

## Verificação

78 testes web passaram, incluindo rejeição de outro usuário no endpoint. migration/tv-import.test.sql usa transação e ROLLBACK para prévia sem escrita, idempotência, detecção de registros inalterados, preservação das personalizações, usuários distintos e bloqueio. A edição de nome com telefone vazio foi validada em transação revertida. Não publicar dados reais dos clientes em repositórios ou logs.

## Piloto Discloud em 18/10/2026

- Aplicação separada FinanceiroPro-TV-Teste, ID 1792366263740, RAM 512 MB; o bot 1784854305068 foi ajustado de 1024 para 512 MB para caber no plano Gold existente de 1024 MB, sem upgrade. Consumo do bot antes do ajuste: 56,39 MB.
- Pacote migration/financeiropro-tv-piloto.zip, código migration/tv-probe/. Apenas leitura, sem Supabase, credenciais ou agendamento. Uma tentativa por reinício.
- Chromium/Selenium instalados pelo APT oficial selenium. Inicialização falhou com No usable sandbox. Adicionar chromium-sandbox ao APT no pacote não resolveu. Nenhuma credencial foi lida e nenhum cliente importado.
- O processo do piloto apenas aguarda após o diagnóstico; não tenta logar novamente. O proprietário autorizou explicitamente o teste com --no-sandbox em 18/10/2026, somente neste piloto separado e sem conexão ao bot ou banco. CAPTCHA e bloqueios continuam sendo motivo de interrupção.
- A automação diária GPT permanece excluída. Se o piloto for cancelado, parar a aplicação e solicitar confirmação para excluir a hospedagem de teste, liberando a reserva; depois restaurar 1024 MB do bot.


- Teste autorizado sem sandbox publicado: Chromium iniciou; página carregou, mas nenhum campo de senha ou link de cliente apareceu durante a espera. Encerramento por TimeoutException às 19:46:43 no painel Discloud. Sem credenciais inseridas, sem leitura de clientes e sem escrita. Evidência: migration/qa/piloto-tv-sem-sandbox.png. Piloto permanece sem agendamento, aguardando intervenção manual; sincronização automática ainda NÃO validada.

## Piloto cancelado pelo proprietário em 18/10/2026
Aplicativo FinanceiroPro-TV-Teste 1792366263740 parado e excluído permanentemente, com confirmação explícita. Memória do FinanceiroBot restaurada para 1024 MB. A rotina GPT continua excluída; não recriar nem republicar o piloto sem nova solicitação. Nenhuma alteração de dados ou credenciais no Supabase foi feita pelo piloto. Os arquivos locais são apenas histórico de diagnóstico, sem execução agendada.

## Retomada pelo navegador em 18/10/2026
A pedido do proprietário, a automação diária deste chat foi recriada. Esta autorização substitui somente a orientação anterior de não recriar a rotina GPT; o piloto Discloud continua cancelado. Preservar todas as regras de isolamento, prévia, dados personalizados e interrupção por sessão expirada.

## Validação real em 18/10/2026
Leitura pelo navegador autorizada e concluída: 44 IDs únicos, lista 1 a 44 de 44, sem filtros. Um cadastro era teste gratuito de 4 horas sem preço; ficou fora da importação/cobrança, sem inventar valor. Para testes explicitamente identificados sem preço, contabilizar separadamente e manter fora do lote financeiro até definição de valor; qualquer ausência de valor em cliente comum continua bloqueando a aplicação.
Prévia: 43 existentes, nenhum novo. Diferenças: 3 valores, 2 vencimentos e normalização de plano/situação que antes continham textos concatenados. Aplicação fp_clientes_tv_v1 exclusiva usuario_id 1: 43 atualizados. Nova prévia confirmou 43 inalterados e zero alterações pendentes. Hashes antes/depois confirmaram nomes, telefones, conta, status de pagamento e registros de outros usuários inalterados. Nenhuma cobrança enviada e nenhuma alteração na origem.


## Espelhamento de exclusões autorizado em 18/10/2026
- Inclusões e mudanças de valor/vencimento continuam por fp_clientes_tv_v1. Nomes e telefones personalizados ficam preservados.
- A rotina também exclui cadastros locais importados que sumiram da origem. Nunca excluir clientes manuais ou de outros usuários.
- Antes de excluir: confirmar nenhum filtro, paginação completa, total e IDs únicos; fazer uma segunda leitura completa e exigir os mesmos IDs. Se lista vazia, parcial, inconsistente ou sessão expirada, não excluir nada.
- A lista de existência inclui TODOS os IDs, inclusive testes gratuitos sem preço. O lote financeiro de 43 clientes não pode ser usado como lista de existência quando há 44 registros na origem.
- Prévia: SELECT id, referencia_tv->>'id' FROM public.clientes WHERE usuario_id=<proprietário conferido> AND referencia_tv->>'origem'='painel.newbr.top' AND referencia_tv->>'id' ausente dos IDs completos confirmados.
- Havendo ausências confirmadas, excluir via conector Supabase com exatamente o mesmo escopo por proprietário, origem e IDs; conferir RETURNING, quantidade e prévia seguinte vazia. Não usar CASCADE, não excluir históricos financeiros e parar se surgirem vínculos dependentes.
- Em 18/10/2026 a prévia com os 44 IDs completos identificou zero exclusões pendentes. O banco não possuía chaves estrangeiras apontando para public.clientes nesta verificação.

Execução manual solicitada após ativar espelhamento: duas leituras completas da origem, sem filtros, 44 IDs únicos idênticos (43 com valor e 1 teste gratuito). Prévia exclusiva proprietário 1: novos=0, atualizados=0, inalterados=43, exclusões=0. Nenhuma escrita necessária; não foram criados ou excluídos clientes fictícios para forçar teste de exclusão.
