# Recuperação do banco da aplicação

1. Na administração, exporte uma cópia criptografada V2. Guarde arquivo e frase em locais separados. Não envie nenhum deles ao GitHub.
2. Prepare Node.js 22+, execute `npm ci` e escolha uma pasta local NOVA, privada, para o banco isolado.
3. Configure a frase em `FP_BACKUP_PASSPHRASE`, sem incluí-la nos argumentos ou em arquivos versionados.
4. Execute `node tools/verify-restore.mjs arquivo.fpbackup NOVA_PASTA_LOCAL`. O programa verifica a autenticação criptográfica, restaura o banco da aplicação e confere as contagens. Não usa rede nem se conecta à produção. Uma pasta existente é recusada.
5. Depois, remova a variável da frase da sessão do terminal. A pasta restaurada contém dados privados descriptografados; controle o acesso e elimine essa cópia quando não for mais necessária.

O ambiente isolado cria apenas referências mínimas para os identificadores de Auth, quando existentes. Isso NÃO restaura contas do Supabase Auth, arquivos de Storage, chaves, configurações da Cloudflare ou outros serviços do provedor. A autenticação própria do FinanceiroPro está nas tabelas da aplicação.

Para recuperação hospedada, use um projeto Supabase separado e vazio, com pgcrypto no schema extensions, os papéis padrão e auth.users disponíveis. Um profissional deve validar permissões e integrações antes de substituir a produção. A função `restoreApplication` aceita um adaptador PostgreSQL e sempre exige um destino sem tabelas da aplicação. Depois de uma recuperação, troque SESSION_SECRET e invalide sessões antigas; não reaproveite cookies de um estado anterior.

Os testes automatizados restauram somente dados sintéticos em dois bancos PostgreSQL locais e não fazem cópias dos dados reais dos usuários. Uma cópia V1 antiga é uma exportação parcial e não substitui o backup V2.
