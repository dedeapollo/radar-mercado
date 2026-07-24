// common.js — constantes, helpers e acesso a dados compartilhados entre
// docs/index.html e docs/alertas.html. Nenhuma lógica de filtro/render de
// página específica mora aqui — só o que as duas páginas usam igual.

const AXES = ["RV/Trading", "Tecnologia", "Produtos Novos", "Risco/Regulação"];
const RISK_AXIS = "Risco/Regulação";
const COLOR_RED = "#EC0000";
const COLOR_DARK = "#1A1A1A";
const COMPETITOR_ORDER = ["XP/Clear/Rico", "BTG Pactual", "Itaú/Íon", "Bradesco/Ágora", "Genial", "Nubank/NuInvest"];
const AXIS_LABEL = {"RV/Trading":"RV/Trading", "Tecnologia":"Tecnologia", "Produtos Novos":"Produtos Novos", "Risco/Regulação":"Risco/Reg."};
const MONTHS_PT = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];

const AXIS_ICON = {
  "RV/Trading": (c) => `<svg viewBox="0 0 16 16" width="12" height="12" style="display:block;"><rect x="2" y="8" width="3" height="6" fill="${c}"></rect><rect x="6.5" y="4" width="3" height="10" fill="${c}"></rect><rect x="11" y="6" width="3" height="8" fill="${c}"></rect></svg>`,
  "Tecnologia": (c) => `<svg viewBox="0 0 16 16" width="12" height="12" style="display:block;"><rect x="4" y="4" width="8" height="8" rx="1" fill="none" stroke="${c}" stroke-width="1.3"></rect><line x1="8" y1="1" x2="8" y2="4" stroke="${c}" stroke-width="1.3"></line><line x1="8" y1="12" x2="8" y2="15" stroke="${c}" stroke-width="1.3"></line><line x1="1" y1="8" x2="4" y2="8" stroke="${c}" stroke-width="1.3"></line><line x1="12" y1="8" x2="15" y2="8" stroke="${c}" stroke-width="1.3"></line></svg>`,
  "Produtos Novos": (c) => `<svg viewBox="0 0 16 16" width="12" height="12" style="display:block;"><circle cx="8" cy="8" r="6.2" fill="none" stroke="${c}" stroke-width="1.3"></circle><line x1="8" y1="5" x2="8" y2="11" stroke="${c}" stroke-width="1.3"></line><line x1="5" y1="8" x2="11" y2="8" stroke="${c}" stroke-width="1.3"></line></svg>`,
  "Risco/Regulação": (c) => `<svg viewBox="0 0 16 16" width="12" height="12" style="display:block;"><path d="M8 2 L14.5 13.5 L1.5 13.5 Z" fill="none" stroke="${c}" stroke-width="1.3" stroke-linejoin="round"></path><line x1="8" y1="6.5" x2="8" y2="9.5" stroke="${c}" stroke-width="1.3"></line><circle cx="8" cy="11.3" r="0.6" fill="${c}"></circle></svg>`,
};

const PERIOD_OPTIONS = [{value:7, label:"7d"}, {value:30, label:"30d"}, {value:90, label:"90d"}, {value:99999, label:"tudo"}];

// Dados de exemplo — usados quando data.json ainda não existe (antes do
// primeiro run do GitHub Actions) ou não pôde ser carregado. Baseados em
// itens reais validados durante a construção do radar.
const SAMPLE_DATA = {
  generated_at: null,
  items: [
    {competitor_group:"XP/Clear/Rico", title:"Clear relança plataforma com execução abaixo de 50ms e alavancagem intraday de até 300x", link:"#", source:"InfoMoney", published_at:"2026-07-08T12:00:00+00:00", why_it_matters:"A Clear eleva o padrão de velocidade e alavancagem, pressionando concorrentes a acompanharem ou perderem traders de alta frequência.", axes:["RV/Trading","Tecnologia","Produtos Novos","Risco/Regulação"], daily_trigger:true, relevance:"alta", also_reported_by:[]},
    {competitor_group:"BTG Pactual", title:"BTG Pactual lança BTG Trends, plataforma de mercados de previsão", link:"#", source:"Money Times", published_at:"2026-07-09T09:00:00+00:00", why_it_matters:"O BTG inova com derivativos binários, produto novo que pode atrair clientes sofisticados, com alcance inicial limitado por restrição a investidores qualificados.", axes:["Produtos Novos","Risco/Regulação"], daily_trigger:true, relevance:"alta", also_reported_by:[{source:"Seu Dinheiro", link:"#"}]},
    {competitor_group:"Genial", title:"Genial eleva alavancagem para até 312x e lança assistente de IA QINV", link:"#", source:"Seu Dinheiro", published_at:"2026-07-10T15:00:00+00:00", why_it_matters:"Genial supera a concorrência em alavancagem máxima, atraindo day traders agressivos e aumentando o risco de escrutínio regulatório.", axes:["RV/Trading","Tecnologia","Produtos Novos","Risco/Regulação"], daily_trigger:true, relevance:"alta", also_reported_by:[]},
    {competitor_group:"Itaú/Íon", title:"CVM publica Ofício-Circular esclarecendo regras de alavancagem em fundos de investimento", link:"#", source:"gov.br/CVM", published_at:"2026-07-11T10:00:00+00:00", why_it_matters:"Reduz incertezas sobre margens, beneficiando corretoras que oferecem alavancagem, mas exige compliance mais rigoroso.", axes:["Risco/Regulação"], daily_trigger:true, relevance:"alta", also_reported_by:[]},
    {competitor_group:"XP/Clear/Rico", title:"Relatório do BTG aponta pivô estratégico da XP para crédito corporativo; CFO é trocado", link:"#", source:"Finsiders Brasil", published_at:"2026-07-06T18:50:00+00:00", why_it_matters:"A troca de CFO e o foco em crédito corporativo indicam reorientação estratégica que pode abrir espaço para concorrentes focados em varejo.", axes:["Produtos Novos"], daily_trigger:false, relevance:"média", also_reported_by:[]},
  ]
};

function fmtShort(iso){
  const d = new Date(iso);
  const day = String(d.getDate()).padStart(2, '0');
  return `${day} ${MONTHS_PT[d.getMonth()]}`;
}

function fmtUpdated(iso){
  const d = new Date(iso);
  return `${fmtShort(iso)} ${d.getFullYear()}`;
}

function escapeHtml(str){
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function escapeAttr(str){
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function axisIconsHtml(item, baseColor){
  return AXES.filter(a => item.axes.includes(a))
    .map(a => AXIS_ICON[a](a === RISK_AXIS ? COLOR_RED : baseColor))
    .join('');
}

async function loadData(){
  try{
    const res = await fetch('./data.json', {cache:'no-store'});
    if(!res.ok) throw new Error('sem data.json');
    const json = await res.json();
    if(!json.items || !json.items.length) throw new Error('data.json vazio');
    return {items:json.items, results:json.results || [], generatedAt:json.generated_at, sample:false};
  }catch(e){
    return {items:SAMPLE_DATA.items, results:[], generatedAt:null, sample:true};
  }
}

// Cria uma lista de botões no estilo do sidebar (label + contagem opcional),
// mantendo a classe "active" sincronizada com o Set no clique — evita o bug
// de chips que filtravam mas não atualizavam o destaque visual.
function buildSidebarList(container, values, activeSet, onToggle, counts){
  container.innerHTML = '';
  values.forEach(v => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sidebar-item' + (activeSet.has(v) ? ' active' : '');
    const count = counts ? (counts[v] ?? 0) : null;
    btn.innerHTML = `<span>${escapeHtml(v)}</span>${count !== null ? `<span class="count">${count}</span>` : ''}`;
    btn.onclick = () => {
      onToggle(v);
      btn.classList.toggle('active', activeSet.has(v));
      if(typeof window.render === 'function') window.render();
    };
    container.appendChild(btn);
  });
}

function sourceHtml(item){
  const extra = item.also_reported_by || [];
  const primary = `<a href="${escapeAttr(item.link)}" target="_blank" rel="noopener">${escapeHtml(item.source)}</a>`;
  if(!extra.length) return `${primary} · ${fmtShort(item.published_at)}`;
  const extraLinks = extra.map(s => `<a href="${escapeAttr(s.link)}" target="_blank" rel="noopener">${escapeHtml(s.source)}</a>`).join(', ');
  return `${primary} <span style="color:var(--grey-500)">também:</span> ${extraLinks} · ${fmtShort(item.published_at)}`;
}

function itemCardHtml(item){
  const isRisk = item.axes.includes(RISK_AXIS);
  const axisLabel = AXIS_LABEL[item.axes[0]] || item.axes[0];
  return `
    <div class="signal-card ${isRisk ? 'risk' : ''}">
      <div class="signal-main">
        <div class="signal-competitor">${escapeHtml(item.competitor_group)}</div>
        <div class="signal-title"><a href="${escapeAttr(item.link)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a></div>
        <div class="signal-why">${escapeHtml(item.why_it_matters)}</div>
      </div>
      <div class="signal-meta">
        <div class="signal-date">${sourceHtml(item)}</div>
        <div class="signal-badges">
          ${item.daily_trigger ? '<span class="action-badge">AÇÃO</span>' : ''}
          <span class="axis-pill ${isRisk ? 'risk' : ''}">${axisIconsHtml(item, '#4A4A4A')}${escapeHtml(axisLabel)}</span>
        </div>
      </div>
    </div>
  `;
}

const COPY_LABEL_TEXT = {copiar:"copiar", observar:"observar", ignorar:"ignorar"};

function copyBadgeHtml(label){
  const cls = COPY_LABEL_TEXT[label] ? label : 'observar';
  return `<span class="copy-badge ${cls}">${COPY_LABEL_TEXT[cls]}</span>`;
}

function listOrNull(values){
  const clean = (values || []).map(v => String(v).trim()).filter(Boolean);
  return clean.length ? clean : null;
}

function resultSectionHtml(title, values){
  const list = listOrNull(values);
  if(!list) return '';
  return `
    <div class="result-section-title">${escapeHtml(title)}</div>
    <ul class="result-list">${list.map(v => `<li>${escapeHtml(v)}</li>`).join('')}</ul>
  `;
}

function resultCardHtml(item){
  const periodo = item.periodo && item.periodo !== 'não informado' ? item.periodo : '';
  return `
    <div class="result-card">
      <div class="result-head">
        <div>
          <span class="result-competitor">${escapeHtml(item.competitor_group)}</span>
          ${periodo ? `<span class="result-periodo">${escapeHtml(periodo)}</span>` : ''}
        </div>
        ${copyBadgeHtml(item.copiar_ou_observar)}
      </div>
      <p class="result-summary">${escapeHtml(item.resumo_estrategico || '')}</p>
      ${resultSectionHtml('Onde colocam energia', item.onde_colocam_energia)}
      ${resultSectionHtml('Movimentos concretos', item.movimentos_concretos)}
      ${resultSectionHtml('Onde deixam a desejar', item.onde_deixam_a_desejar)}
      <div class="result-highlight">
        <div class="result-section-title">Oportunidade para nós</div>
        <div class="result-highlight-text">${escapeHtml(item.oportunidade_para_nos || 'nenhuma clara')}</div>
        <div class="result-section-title" style="margin-top:10px;">Leitura para o Santander</div>
        <div class="result-highlight-text">${escapeHtml(item.leitura_para_o_santander || '')}</div>
      </div>
      <div class="result-meta">
        <span class="result-axes">${axisIconsHtml({axes: item.eixos || []}, '#4A4A4A')}</span>
        ${sourceHtml(item)}
      </div>
    </div>
  `;
}

function buildCompetitorSummaries(items){
  const counts = {};
  const byComp = {};
  COMPETITOR_ORDER.forEach(c => { counts[c] = 0; byComp[c] = []; });
  items.forEach(i => {
    if(counts[i.competitor_group] === undefined) return;
    counts[i.competitor_group]++;
    byComp[i.competitor_group].push(i);
  });
  const maxCount = Math.max(...Object.values(counts), 1);

  return COMPETITOR_ORDER.map(name => {
    const its = byComp[name].slice().sort((a,b) => new Date(b.published_at) - new Date(a.published_at));
    return {
      name,
      count: its.length,
      active: its.length > 0,
      barWidth: Math.round((its.length / maxCount) * 100),
      highlights: its.slice(0, 2),
    };
  });
}
