# Radar de Mercado — Concorrência (Investimentos)

Monitoramento diário automatizado de XP/Clear/Rico, BTG Pactual, Itaú/Íon,
Bradesco/Ágora e Genial Investimentos, organizado em 4 eixos (RV/Trading,
Tecnologia, Produtos Novos, Risco/Regulação) e entregue em 3 tranches:

- 🔴 **Diário** — só quando há gatilho real (mudança de risco/alavancagem,
  comunicado a cliente, lançamento na mídia, ação regulatória)
- 🟡 **Semanal** — toda segunda-feira, cobertura ampla da semana
- 🟢 **Mensal** — todo dia 1, panorama completo + sinais transversais

## Como funciona (visão geral)

```
collect.py  →  synthesize.py  →  report.py  →  e-mail (Resend)
(RSS grátis)   (classifica c/     (decide a tranche          ↘
                DeepSeek)          e monta o conteúdo)    export_dashboard.py → docs/data.json (Cloudflare Pages)
```

O GitHub Actions roda essa cadeia todo dia sozinho, sem você precisar abrir
nada. O histórico (`data/history.json`) é commitado de volta no repositório
a cada execução — é assim que o semanal/mensal "lembram" do que já
aconteceu, mesmo o runner sendo descartado a cada rodada.

## Setup — passo a passo

### 1. Colocar o código no GitHub

Se você ainda não tem um repositório pra isso:

```bash
cd radar-mercado
git init
git add .
git commit -m "Primeira versão do radar de mercado"
```

No GitHub.com: crie um repositório novo (pode ser privado — recomendado,
já que o conteúdo é estratégia de concorrentes), sem README/gitignore
(vamos usar os que já existem aqui). Depois:

```bash
git remote add origin https://github.com/dedeapollo/radar-mercado.git
git branch -M main
git push -u origin main
```

### 2. Criar as chaves de API

- **DeepSeek**: https://platform.deepseek.com/api_keys
- **Resend**: https://resend.com/api-keys (você já tem uma — se foi a que
  usamos no teste, gere uma nova antes de colocar em produção)

### 3. Adicionar os segredos no repositório

No GitHub: **Settings → Secrets and variables → Actions → New repository
secret**. Criar três:

| Nome | Valor |
|---|---|
| `DEEPSEEK_API_KEY` | sua chave do DeepSeek |
| `RESEND_API_KEY` | sua chave do Resend |
| `EMAIL_RECIPIENTS` | e-mails separados por vírgula, ex: `voce@empresa.com,lideranca@empresa.com` |

**Restrição importante**: sem verificar um domínio próprio no Resend
(resend.com/domains), só é possível enviar para o e-mail associado à sua
conta Resend. Pra mandar de verdade pra lideranças com e-mails da empresa,
você vai precisar verificar o domínio da empresa lá — o que normalmente
exige acesso ao DNS (pode precisar de TI só pra esse passo específico).
Até lá, use seu próprio e-mail em `EMAIL_RECIPIENTS` pra validar o fluxo
inteiro.

### 4. Ativar o dashboard — Cloudflare Pages + Access (não GitHub Pages)

**Por quê não GitHub Pages**: no plano gratuito, só funciona com repositório
público. E mesmo pagando o GitHub Pro pra manter o repo privado, o site
publicado continua acessível por qualquer pessoa com o link — sem login.
Não é o que queremos (só você + lideranças escolhidas).

**Caminho gratuito que restringe de verdade**:

**4a. Cloudflare Pages via GitHub Actions** (evita a integração Git do
Cloudflare, que costuma travar no "cloning" por permissão do app do GitHub —
se você já tentou "Connect to Git" e deu erro nesse passo, pode ignorar
esse projeto quebrado, vamos publicar por outro caminho)

1. Criar conta grátis em cloudflare.com (se ainda não tiver)
2. Pegar seu **Account ID**: dashboard do Cloudflare → barra lateral direita
   da página inicial, ou em `dash.cloudflare.com` → qualquer domínio →
   "Account ID" aparece na barra lateral
3. Criar um **API Token**: dashboard → ícone de usuário → **My Profile →
   API Tokens → Create Token** → template **Edit Cloudflare Workers**
   (esse token também cobre Pages) → Continue → Create Token → copia o
   valor (só aparece uma vez)
4. No GitHub, adiciona dois novos secrets (mesmo lugar dos outros três):

| Nome | Valor |
|---|---|
| `CLOUDFLARE_API_TOKEN` | o token que você acabou de criar |
| `CLOUDFLARE_ACCOUNT_ID` | o Account ID do passo 2 |

5. Pronto — o workflow já tem a etapa `Publica dashboard no Cloudflare
   Pages`, que cria o projeto `radar-mercado` no Cloudflare automaticamente
   na primeira execução (não precisa criar nada manualmente no dashboard
   do Cloudflare antes). A URL fica em `radar-mercado.pages.dev` (ou
   similar — o Cloudflare avisa o endereço exato no log dessa etapa,
   dentro da aba Actions do GitHub).

**4b. Cloudflare Access** (restringe quem pode abrir essa URL)
1. No mesmo painel: **Zero Trust** (ativa de graça na primeira vez)
2. **Access → Applications → Add an application → Self-hosted**
3. Aponta pro domínio `radar-mercado.pages.dev`
4. Cria uma política: regra **Include → Emails** → lista seu e-mail e o das
   lideranças que vão acompanhar
5. Salvar

A partir daí, só quem está nessa lista de e-mails consegue abrir o
dashboard — ao acessar, recebe um código de uso único por e-mail pra
entrar. Sem senha, sem conta, e ninguém fora da lista consegue ver nada.

Toda vez que o GitHub Actions rodar, ele já publica a versão mais nova
direto no Cloudflare Pages como parte do próprio workflow — não depende
de o Cloudflare "perceber" um push, é uma etapa explícita (`wrangler pages
deploy`) que roda sempre.

### 5. Testar manualmente

Na aba **Actions** do repositório → **Radar de Mercado** → botão
**Run workflow**. Acompanhe o log de cada etapa ali mesmo. Se dar tudo
certo, o e-mail chega e `data/history.json` aparece commitado no repo.

Depois disso, ele roda sozinho todo dia às 07h (horário de Brasília) —
sem precisar abrir nada.

## Ajustando o escopo

Concorrentes, eixos e critérios de gatilho diário ficam em `src/sources.py`
— editar esse arquivo é a forma principal de ajustar o radar.

## Limitações conhecidas desta versão

- Coleta é só via Google News RSS por enquanto. CVM e changelog de app
  store (fontes de alto sinal identificadas nas notícias que já vimos)
  ainda não estão automatizados — próxima iteração natural.
- `collect.py` não foi testado com internet real ainda (só a lógica de
  parsing, com um feed simulado) — o primeiro "Run workflow" real vai ser
  o primeiro teste de ponta a ponta com dados ao vivo.
- O dashboard busca `docs/data.json` no mesmo diretório — se o GitHub
  Pages não estiver servindo esse arquivo (Pages desativado ou pasta
  errada), ele cai automaticamente nos dados de exemplo.
