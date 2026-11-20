# Publicação do FinanceiroPro

Use os projetos existentes. Não crie novos endereços de produção.

## Worker

A configuração está em `migration/wrangler.jsonc`. A entrada é `release/worker.mjs`, relativa a esse arquivo. Configure `SUPABASE_BACKEND_KEY` (chave secreta moderna do projeto FinanceiroPro) e `SESSION_SECRET` pelas variáveis protegidas. Preserve o limitador de login `LOGIN_LIMITER` e a variável `FINANCIAL_WRITES_ENABLED`. Nunca copie valores secretos para arquivos versionados.

Após testes, publique o Worker `financeiroproweb` com essa configuração. Por API, envie todos os módulos como multipart, `main_module=release/worker.mjs`, preserve as configurações existentes e use `keep_bindings=["secret_text"]` para preservar os segredos. Não volte a uma versão anterior à migração de senhas sem compatibilidade com bcrypt.

## Cloudflare Pages

Execute `npm run build`. Envie os 21 arquivos públicos com seus hashes ao armazenamento de assets do Pages usando uma autorização temporária de upload. Depois publique no projeto `financeiroproweb`, branch `main`, o manifesto gerado e `_worker.js`, `_routes.json` e `_headers`.

A configuração de produção do Pages deve preservar o binding de serviço `FINANCEIRO_APP` para o Worker `financeiroproweb`. Os caminhos estáticos excluídos em `_routes.json` continuam fora das invocações do Worker. Não inclua páginas privadas ou respostas personalizadas no manifesto.

Confira o sucesso da implantação, o endereço oficial e os hashes dos assets antes de encerrar a publicação. Os arquivos de saída não são versionados.

## Senhas: ordem das migrações

1. Aplicar `migration/schema/20261120_01_password-functions.sql` no projeto FinanceiroPro.
2. Publicar o Worker com os novos RPCs de verificação e troca de senha.
3. Aplicar `migration/schema/20261120_02_password-upgrade.sql` uma vez. Ele instala o trigger e converte os resumos antigos.
4. Conferir contagens, privilégios e testes sintéticos com rollback. Não consultar valores de senhas.

As duas migrações já foram aplicadas na produção em 20/11/2026. O segundo script cria um trigger e não deve ser reaplicado como se fosse novo.

## Bot

As fontes Python e `discloud.config` ficam na raiz. Configure `TELEGRAM_TOKEN`, `SUPABASE_URL` e `SUPABASE_KEY` exclusivamente no ambiente protegido do serviço. O bot usa o mesmo projeto FinanceiroPro. Publicar o site não publica o bot, mas o repositório possui integração automática com o Discloud para a branch principal. Confira o status `discloud/commit` após enviar mudanças. Na consolidação de 20/11/2026, essa integração informou “Aplicação atualizada com sucesso” para o bot existente. Não reative o antigo piloto de TV.

## Sincronização da TV

Preserve o processo e o proprietário definidos em [migration/TV-INTEGRATION.md](migration/TV-INTEGRATION.md). Os ajustes desta entrega não alteram clientes, telefones personalizados, pagamentos ou agendamento de sincronização.
