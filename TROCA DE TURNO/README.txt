POSIÇÃO DE CAMPO - VERSÃO MULTIUSUÁRIO COM ADMINISTRADOR

REQUISITO
- Python 3.10 ou superior.
- Não há dependências externas para instalar.

PRIMEIRA CONFIGURAÇÃO NO WINDOWS
1. Extraia a pasta completa do projeto.
2. Execute criar-admin.bat no computador servidor.
3. Informe o nome do Administrador e a senha.
   - Não há exigência de complexidade.
   - A senha não pode ficar vazia.
4. Execute iniciar-servidor.bat.
5. Abra http://localhost:8000 no navegador.
6. Entre com a conta de Administrador.
7. No menu Usuários, crie as contas dos demais usuários.

IMPORTANTE
- Não existe cadastro público.
- /register redireciona para o login.
- /api/auth/register está desativada.
- Somente o Administrador pode criar, ativar/desativar, redefinir senha ou excluir contas.
- Usuários comuns não veem o menu Usuários e a API também bloqueia esse acesso no servidor.
- Todos os usuários ativos continuam podendo preencher PPT, NRD, RBR e PST.
- O botão de backup manual é exclusivo do Administrador.
- As senhas são armazenadas com PBKDF2 + salt, nunca em texto puro.
- Não abra index.html diretamente por file://. Use o servidor Python.

ADMINISTRADOR
- Para criar o primeiro Administrador: criar-admin.bat
- O mesmo arquivo também pode redefinir/promover uma conta existente para Administrador.
- A redefinição encerra sessões antigas daquela conta.
- O Administrador não pode excluir/desativar a própria conta pelo painel.

USUÁRIOS
- Criados somente pelo Administrador.
- A senha pode ser simples, mas deve estar preenchida.
- O Administrador pode:
  - criar conta;
  - ativar/desativar conta;
  - redefinir senha;
  - excluir conta.
- Ao desativar ou redefinir a senha, sessões existentes daquele usuário são encerradas.

RECURSOS
- Login e sessão no servidor.
- Perfis Administrador e Usuário.
- SQLite compartilhado.
- Preenchimento das quatro unidades.
- Histórico de cada salvamento com usuário, unidade, versão e horário.
- Controle de edição concorrente para evitar sobrescrita silenciosa.
- Backup automático diário em data/backups/.
- Backup manual exclusivo do Administrador.
- Retenção automática de backups por 30 dias.
- Servidor HTTP com threads para acessos simultâneos em rede local.
- SQLite com WAL e busy_timeout.
- Limite de tentativas de login.
- Verificação de origem em operações de gravação.
- Cabeçalhos básicos de segurança no navegador.

BANCO DE DADOS
- Principal: data/posicao_campo.db
- Backups: data/backups/posicao_campo-AAAA-MM-DD.db
- Migrações de role/is_active são aplicadas automaticamente em bancos existentes.
- Contas antigas continuam como Usuário comum; execute criar-admin.bat para definir o Administrador.

ESTRUTURA PRINCIPAL
- server.py                   -> servidor multiusuário
- criar-admin.bat             -> configuração local do Administrador
- iniciar-servidor.bat        -> inicia o servidor
- backend/app.py              -> rotas HTTP/API e autorizações
- backend/database.py         -> SQLite, usuários, histórico e backups
- backend/security.py         -> hash de senha e tokens
- backend/config.py           -> configurações
- backend/create_admin.py     -> utilitário local do Administrador
- login.html                  -> tela de login
- index.html                  -> painel operacional
- css/                        -> estilos
- js/                         -> scripts do frontend
- assets/                     -> recursos visuais
- data/                       -> banco e backups

ROTAS DE ACESSO
- /login
- /
- /api/auth/login
- /api/auth/logout
- /api/auth/me
- /api/units
- /api/history

ROTAS EXCLUSIVAS DO ADMINISTRADOR
- GET/POST /api/users
- DELETE /api/users/{id}
- PUT /api/users/{id}/active
- PUT /api/users/{id}/password
- POST /api/backup

REDE LOCAL
O servidor escuta em 0.0.0.0:8000 por padrão.
Em outro computador da mesma rede, use o IP do computador servidor, por exemplo:
http://192.168.1.50:8000

O Firewall do Windows pode solicitar autorização na primeira execução.

INTERNET
Esta versão é destinada à rede local. Antes de expor na internet, configure HTTPS e um servidor/proxy apropriado.
