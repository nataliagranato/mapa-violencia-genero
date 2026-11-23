# Segurança e privacidade

Este projeto publica dados sobre violência de gênero. O risco principal não é
vazamento de credencial — é **exposição de pessoas** e **interpretação errada dos
números**. As regras abaixo são requisitos, não sugestões.

## Princípios (LGPD)

| Princípio | Como aparece no projeto |
|---|---|
| Minimização | Só `valor_absoluto` agregado por município/ano. Nenhum campo de vítima, agressor, endereço ou data do fato no banco |
| Finalidade | Indicadores para política pública e transparência (ODS 5.2 / 16) |
| Transparência | `fontes.nota_metodologica` obrigatório e exibido na UI; link para o dataset original em cada série |
| Segurança | API somente leitura, SQL parametrizado, sem credenciais no repositório |
| Não discriminação | Nota de subnotificação fixa no painel: registro baixo ≠ ausência de violência |

### Risco de reidentificação

Municípios pequenos + contagem pequena + ano → pode apontar para poucas pessoas.
Mitigação recomendada (ainda **não implementada**): supressão de células com
`valor_absoluto` entre 1 e 4 (ou publicação só de faixas) e proibição explícita de
cruzamento com data do fato. Hoje a API devolve o valor exato.

## Segurança física da usuária

Requisito funcional de segurança, não UX:

- Botão **Saída rápida** e tecla `Esc` → `window.location.replace()` para uma página neutra (previsão do tempo), sem deixar o mapa no histórico de navegação.
- Link do **Ligue 180** sempre visível na topbar.
- Nenhum campo de busca persistido em `localStorage`/cookie; nenhum analytics.
- Sem título de página alarmante em aba compartilhada — hoje o `<title>` descreve o projeto (avaliar se convém um título neutro).

## Superfície de ataque

| Vetor | Situação |
|---|---|
| SQL injection | Queries com placeholders `?`; nenhuma concatenação de entrada |
| XSS | `innerHTML` no painel com dados da API (base oficial, sem entrada livre). Sem escape explícito — aceitável hoje, a corrigir se qualquer campo passar a vir de fonte não confiável |
| Autenticação | Inexistente por desenho (leitura pública) |
| CORS | Sem headers; acesso esperado via proxy same-origin do Vite |
| Rate limiting | Inexistente — expor publicamente exige proxy com limite |
| Dependências | Go: 1 dependência (`modernc.org/sqlite`); JS: 2 (`leaflet`, `vite`); Python: stdlib pura |
| Segredos | Nenhum. Nenhuma chave, token ou `.env` no repositório |
| Container | Backend roda como root na imagem `alpine` (padrão); sem `read_only`, sem `no-new-privileges` |

## Dados de rede de apoio

`rede_apoio` armazena nome, endereço e telefone de **equipamentos públicos**
(DEAM, CREAS, Defensoria, Casa da Mulher). São dados institucionais, não pessoais
— mas exigem verificação de atualidade antes de publicar, porque um telefone
errado pode custar tempo em situação de risco. Tabela hoje vazia: só preencher com
fonte oficial conferida.

## Checklist antes de publicar uma nova versão

- [ ] Nenhum CSV bruto ou `.db` com dados individuais no commit.
- [ ] Nenhuma credencial em código, compose ou docs.
- [ ] `nota_metodologica` da nova fonte preenchida.
- [ ] Texto de subnotificação presente no painel.
- [ ] `Esc` e botão de saída rápida funcionando.
- [ ] Ligue 180 acessível na topbar.
- [ ] Se o município tiver menos de 5 casos, decidir sobre supressão.
