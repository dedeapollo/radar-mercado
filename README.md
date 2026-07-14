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
                DeepSeek)          e monta o conteúdo)    export_dashboard.py → docs/data.json (GitHub Pages)
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
git remote add origin https://github.com/SEU-USUARIO/radar-mercado.git
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

### 4. Ativar o dashboard (GitHub Pages)

No GitHub: **Settings → Pages → Build and deployment → Source: Deploy from
a branch → Branch: `main`, pasta `/docs` → Save**. Em alguns minutos o
dashboard fica acessível em `https://SEU-USUARIO.github.io/radar-mercado/`.

Antes do primeiro run do workflow, o dashboard mostra dados de exemplo
(com um aviso "dados de exemplo" no canto) — assim que `docs/data.json`
for gerado pela primeira vez, ele passa a refletir dados reais.

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
