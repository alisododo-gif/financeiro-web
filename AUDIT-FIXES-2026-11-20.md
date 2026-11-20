# Correções da auditoria de 20/11/2026

## Aplicação e segurança

A confirmação do lançamento parcelado voltou a exibir descrição, cartão, parcelas e total exato. O teste agora executa as três etapas e não fornece a função de arredondamento retirada, que mascarava a falha. A tela publicada foi conferida com R$ 100 divididos em três parcelas, sem salvar nenhum registro.

Cadastro, administração e login compartilham a regra de nome de usuário. O banco rejeita espaços e caracteres incompatíveis no cadastro; nomes antigos válidos continuam funcionando.

Cada conta possui `session_version`. Trocas de senha ou situação invalidam as sessões anteriores. O comando “Sair de todos os aparelhos” incrementa essa versão e encerra os acessos no servidor. As sessões anteriores à atualização foram encerradas uma vez na implantação.

As permissões residuais TRIGGER, REFERENCES e TRUNCATE de authenticated nas tabelas públicas foram retiradas. Os avisos informativos de RLS sem políticas permanecem intencionalmente: o acesso aos dados continua restrito ao backend. Índices pequenos ainda sem uso foram mantidos.

## Banco e recuperação

As operações financeiras, a integração TV e a exclusão administrativa usam o mesmo bloqueio por proprietário. O antigo bloqueio exclusivo de todas as tabelas foi retirado; consultas de fatura não entram nessa fila de gravação. Sequências e chaves de idempotência continuam protegendo identificadores e repetições. O teste isolado envia 60 pedidos, verifica registros, repetição e isolamento. O PostgreSQL embarcado usado nesse teste tem execução interna serial; isso valida contratos, não constitui medição de capacidade do Supabase com 60 conexões reais.

O backup V2 usa um único snapshot consistente e cobre as 16 tabelas atuais da aplicação nos schemas public e financeiropro_operacoes, incluindo permissões, testes gratuitos, integrações, funções, views, gatilhos, índices e sequências. Continua criptografado com a frase do administrador. Não é cópia dos serviços Auth/Storage do provedor nem dos segredos da Cloudflare.

Uma restauração em um segundo PostgreSQL isolado recuperou dados sintéticos, configurações, rotinas e contagens. O programa recusa um destino que já contenha tabelas. A verificação V1 de arquivos antigos continua disponível, mas a recuperação completa requer V2. Consulte `RECOVERY.md`.

## Bot, administração e publicação

O bot já utilizava threads para as consultas dos fluxos; o gargalo identificado era o processamento global de atualizações. Agora até 16 usuários podem ter atualizações em processamento, mantendo uma fila ordenada para cada usuário. Isso é um limite de processamento configurado, não uma promessa de 16 gravações simultâneas no banco.

Alertas registram confirmação, falha, nova tentativa ou entrega incerta. Rejeições explícitas por limite de envio permitem até três tentativas; entregas incertas não são repetidas automaticamente. O painel administrativo mostra os resultados do dia, sem expor mensagens ou tokens. Reservas antigas sem resultado foram preservadas como incertas. O horário diário das 10h de Cuiabá foi mantido.

A vinculação de telefone percorre páginas de usuários ativos. A administração carrega todas as páginas e calcula totais sobre o conjunto completo, sem o antigo corte em 200. A lista de clientes e sua paginação permanecem como estavam.

As dependências Python diretas e indiretas foram fixadas por versão e hash em requirements.lock. A resolução foi validada para Python 3.11/Linux; 34 pacotes foram consultados no OSV sem avisos retornados nessa consulta. As dependências Node possuem package-lock e `npm ci` na validação. Isso não garante ausência futura de vulnerabilidades.

O Worker mantém os segredos existentes e passou a remover parâmetros de URL dos logs. Tracing foi habilitado com amostra de 1%, sem trocar de plano ou ativar um serviço pago. A separação dos arquivos estáticos no Pages foi preservada.

## Validação e limite restante

87 testes Node.js e 69 testes Python, incluindo migrações reais em PostgreSQL isolado, recuperação, sessões, revisão do formulário, administração e falhas simuladas de entrega. O site, os arquivos públicos, o login e os avisos administrativos foram conferidos. Não houve envio de mensagem, pagamento, exclusão de cliente real ou recálculo de registros antigos.

Arquivos de credenciais antigos continuam no histórico público do GitHub. Não foi feita reescrita destrutiva desse histórico nem lidos os valores. É necessário confirmar no provedor a revogação de eventuais chaves antigas; apagar um arquivo não revoga sua chave. Essa ação depende do acesso às configurações protegidas do provedor.
