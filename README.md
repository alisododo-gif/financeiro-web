# FinanceiroPro Web

Código atual do FinanceiroPro Web, consolidado a partir dos módulos em produção e das fontes locais atuais em 20/11/2026.

- Sistema: https://financeiroproweb.pages.dev/
- Apresentação: https://financeiroproweb.pages.dev/site
- Supabase: projeto `hkfyvhthfshnddduckjs`, conexão FinanceiroPro.
- Cloudflare Pages `financeiroproweb`: arquivos públicos estáticos e proxy para o Worker.
- Cloudflare Worker `financeiroproweb`: aplicação, sessão, autorizações e operações no banco.
- Bot Telegram: `bot_telegram.py`, `bot_ui.py`, `bot_flows.py`, `bot_repository.py` e alertas diários.

O antigo aplicativo Streamlit, arquivos de ambiente, credenciais e arquivos gerados foram retirados da árvore principal. O histórico de commits foi preservado. O site continua com publicação direta na Cloudflare. O bot tem integração automática com o Discloud: alterações enviadas à branch principal podem republicar o bot; confira o status `discloud/commit` no GitHub.

## Testes

Node.js 22 ou superior, sem dependências adicionais:

```sh
npm test
npm run build
```

Python 3.11 ou superior:

```sh
python -m unittest discover -p '*_test.py'
```

Os testes usam dados sintéticos e substitutos dos serviços. Não iniciam o bot nem enviam mensagens. Em Windows, instale `tzdata` para disponibilizar `America/Cuiaba`.

## Estrutura

`migration/release/worker.mjs` é a entrada do Worker; os módulos em `migration/` completam a aplicação. `migration/build-pages-static.mjs` gera os arquivos públicos em `migration/pages-dist/` e o manifesto de upload em `migration/qa/`. `migration/schema/` contém scripts de banco de diferentes etapas da implantação; não execute todos como instalador nem reaplique scripts históricos em produção.

Consulte [DEPLOYMENT.md](DEPLOYMENT.md) e [RELEASE-2026-11-20.md](RELEASE-2026-11-20.md).

Segredos devem ficar nas variáveis protegidas da Cloudflare e do serviço do bot. Nunca envie `.env`, chaves ou senhas ao repositório. A remoção de um arquivo da versão principal não remove cópias do histórico; credenciais que tenham sido publicadas precisam ser revogadas no provedor.
