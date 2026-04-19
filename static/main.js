let currentData = null;
let priceChart = null;

// ── Position Sizing ───────────────────────────────────────────────────────────
function calcPositionSize() {
  const accountEl = document.getElementById('psAccount');
  const riskEl    = document.getElementById('psRisk');
  const results   = document.getElementById('psResults');
  const warning   = document.getElementById('psWarning');

  const account  = parseFloat(accountEl.value);
  const riskPct  = parseFloat(riskEl.value);

  // Save account size across sessions
  if (account) localStorage.setItem('swingEdgeAccount', account);

  if (!account || !riskPct || !currentData) { results.style.display = 'none'; return; }

  const price    = currentData.price;
  const stopLoss = currentData.trade_plan.stop_loss;
  const riskPerShare = price - stopLoss;

  if (riskPerShare <= 0) { results.style.display = 'none'; return; }

  const dollarRisk   = account * (riskPct / 100);
  const shares       = Math.floor(dollarRisk / riskPerShare);
  const positionSize = shares * price;
  const accountPct   = (positionSize / account) * 100;

  document.getElementById('psShares').textContent       = shares.toLocaleString() + ' shares';
  document.getElementById('psDollarRisk').textContent   = '$' + dollarRisk.toFixed(2);
  document.getElementById('psPositionSize').textContent = '$' + positionSize.toFixed(2);
  document.getElementById('psAccountPct').textContent   = accountPct.toFixed(1) + '%';

  // Warn if position is more than 25% of account
  warning.style.display = 'none';
  if (accountPct > 25) {
    warning.textContent = `⚠ This position is ${accountPct.toFixed(1)}% of your account — consider reducing risk % or splitting across more trades.`;
    warning.style.display = 'block';
  } else if (shares === 0) {
    warning.textContent = '⚠ Account size or risk % too small to buy even 1 share at this stop distance.';
    warning.style.display = 'block';
  }

  results.style.display = 'block';
}

// ── Utilities ────────────────────────────────────────────────────────────────
const fmt = n => n == null ? 'N/A' : n.toLocaleString();
const fmtB = n => {
  if (!n) return 'N/A';
  if (n >= 1e9) return '$' + (n/1e9).toFixed(2) + 'B';
  if (n >= 1e6) return '$' + (n/1e6).toFixed(1) + 'M';
  return '$' + n.toLocaleString();
};
const pct = (n, decimals=2) => n == null ? 'N/A' : (n > 0 ? '+' : '') + n.toFixed(decimals) + '%';
const colorClass = n => n > 0 ? 'pos' : n < 0 ? 'neg' : 'neu';
const yesNo = b => b == null ? 'N/A' : b ? '<span class="pos">✓ Yes</span>' : '<span class="neg">✗ No</span>';


function switchTab(name, el) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  el.classList.add('active');
}

// ── Analyze ──────────────────────────────────────────────────────────────────
async function analyze() {
  const ticker = document.getElementById('tickerInput').value.trim().toUpperCase();
  if (!ticker) return;

  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('results').style.display = 'none';
  document.getElementById('errorBox').style.display = 'none';
  document.getElementById('loading').style.display = 'block';

  try {
    const res = await fetch('/analyze', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ticker})
    });
    const d = await res.json();
    document.getElementById('loading').style.display = 'none';

    if (!d.success) {
      document.getElementById('errorBox').textContent = '⚠ ' + d.error;
      document.getElementById('errorBox').style.display = 'block';
      return;
    }
    currentData = d;
    renderAll(d);
    document.getElementById('results').style.display = 'block';
  } catch(e) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('errorBox').textContent = 'Network error: ' + e.message;
    document.getElementById('errorBox').style.display = 'block';
  }
}

document.getElementById('tickerInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') analyze();
});

async function randomTSX(attempt = 1) {
  const MAX = 6;
  const res = await fetch('/random-tsx');
  const { ticker } = await res.json();
  document.getElementById('tickerInput').value = ticker;

  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('results').style.display = 'none';
  document.getElementById('errorBox').style.display = 'none';
  document.getElementById('loading').style.display = 'block';
  document.getElementById('loading').textContent = `⏳ Fetching ${ticker}…`;

  try {
    const r = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker })
    });
    const d = await r.json();
    document.getElementById('loading').style.display = 'none';

    if (!d.success) {
      if (attempt < MAX) return randomTSX(attempt + 1);
      document.getElementById('errorBox').textContent = '⚠ Could not load a TSX stock after several tries. Please try again.';
      document.getElementById('errorBox').style.display = 'block';
      return;
    }
    currentData = d;
    renderAll(d);
    document.getElementById('results').style.display = 'block';
  } catch (e) {
    document.getElementById('loading').style.display = 'none';
    if (attempt < MAX) return randomTSX(attempt + 1);
  }
}

// ── Render ───────────────────────────────────────────────────────────────────
function renderAll(d) {
  renderHero(d);
  renderMarket(d.market);
  renderTradePlan(d);
  renderMomentum(d);
  renderCatalyst(d);
  renderRisk(d);
  renderChart(d);
  loadWatchlist();
}

function renderHero(d) {
  const s = d.score;
  document.getElementById('rName').textContent = d.name;
  document.getElementById('rSub').textContent = d.ticker + ' · ' + d.sector + ' · ' + d.cap_tier;
  document.getElementById('rPrice').textContent = '$' + d.price;
  document.getElementById('rChg').innerHTML = `<span class="${colorClass(d.change_pct)}">${pct(d.change_pct)} today</span>`;

  const chips = [];
  if (d.rvol >= 1.5) chips.push(`<span class="chip chip-green">RVOL ${d.rvol}x</span>`);
  if (d.rsi) {
    if (d.rsi > 60) chips.push(`<span class="chip chip-yellow">RSI ${d.rsi}</span>`);
    else chips.push(`<span class="chip chip-blue">RSI ${d.rsi}</span>`);
  }
  if (d.week52_proximity_pct <= 10) chips.push(`<span class="chip chip-green">Near 52W High</span>`);
  if ((d.short_pct_float||0) >= 20) chips.push(`<span class="chip chip-yellow">Short ${d.short_pct_float}%</span>`);
  document.getElementById('rChips').innerHTML = chips.join('');

  const circle = document.getElementById('rCircle');
  circle.style.borderColor = s.color;
  circle.style.color = s.color;
  document.getElementById('rScore').textContent = s.total;
  document.getElementById('rRating').style.color = s.color;
  document.getElementById('rRating').textContent = s.rating;

  const bd = s.breakdown;
  const labels = {momentum:'Momentum',rvol:'RVOL',catalyst:'Catalyst',float:'Float',trend:'Trend',squeeze:'Squeeze'};
  const maxes  = {momentum:30,rvol:25,catalyst:15,float:10,trend:10,squeeze:10};
  document.getElementById('rBreakdown').innerHTML = Object.keys(bd).map(k =>
    `<div class="score-pill"><span>${labels[k]}</span>${bd[k]}/${maxes[k]}</div>`
  ).join('');
}

function toISODate(d) { return d.toISOString().split('T')[0]; }

function countTradingDays(entryD, exitD) {
  let n = 0;
  const c = new Date(entryD);
  while (c < exitD) { c.setDate(c.getDate() + 1); if (c.getDay() !== 0 && c.getDay() !== 6) n++; }
  return n;
}

function recalcDates() {
  const entry = document.getElementById('tpEntry').value;
  const exit  = document.getElementById('tpExit').value;
  if (!entry || !exit || !currentData) return;

  const entryD = new Date(entry + 'T12:00:00');
  const exitD  = new Date(exit  + 'T12:00:00');
  if (exitD <= entryD) return;

  const tradingDays = countTradingDays(entryD, exitD);
  document.getElementById('tpDays').textContent = tradingDays + ' trading days';

  const price    = currentData.price;
  const score    = currentData.score.total;
  const mktMult  = (currentData.market && currentData.market.return_multiplier) || 1.0;
  const shortPct = currentData.short_pct_float || 0;
  const above50  = currentData.above_50ma;
  const above200 = currentData.above_200ma;
  const tp       = currentData.trade_plan;
  const probs    = tp.scenarios.map(s => s.probability);
  const diffMs   = exitD - entryD;

  const BASE_DAYS = 5;
  const dayScale  = Math.pow(tradingDays / BASE_DAYS, 0.65);

  const bullBase5d = 1.5 + (score / 100) * 8.0;
  let newBull = Math.round(bullBase5d * dayScale * mktMult * 10) / 10;
  if (shortPct >= 20) newBull = Math.round(newBull * 1.2 * 10) / 10;
  newBull = Math.min(newBull, 35);

  const baseFraction = (above50 === false || above200 === false) ? 0.38 : 0.45;
  const newBase = Math.round(newBull * baseFraction * 10) / 10;

  const bearBase5d = score >= 55 ? 2.5 : score >= 38 ? 3.5 : 5.0;
  const bearMktFactor = 1.0 + Math.max(0, (1.0 - mktMult) * 0.8);
  const newBear = -Math.round(bearBase5d * dayScale * bearMktFactor * 10) / 10;

  const newEV = Math.round(((probs[0]/100)*newBull + (probs[1]/100)*newBase + (probs[2]/100)*newBear) * 10) / 10;
  const newRR = newBear !== 0 ? Math.round(((newBull + newBase) / 2) / Math.abs(newBear) * 100) / 100 : 0;

  document.getElementById('tpEV').textContent = (newEV >= 0 ? '+' : '') + newEV + '%';
  document.getElementById('tpEV').className = 'value ' + (newEV > 0 ? 'pos' : newEV < 0 ? 'neg' : 'neu');
  document.getElementById('tpRR').textContent = newRR + ':1';
  document.getElementById('tpRR').className = 'value ' + (newRR >= 2 ? 'pos' : newRR >= 1 ? '' : 'neg');

  const cards = document.querySelectorAll('.scenario');
  [
    { gain: newBull, exitMult: 1.0 },
    { gain: newBase, exitMult: 0.7 },
    { gain: newBear, exitMult: 0.35 },
  ].forEach(({ gain, exitMult }, i) => {
    if (!cards[i]) return;
    const sign    = gain >= 0 ? '+' : '';
    const tgt     = Math.round(price * (1 + gain / 100) * 100) / 100;
    const scExit  = new Date(entryD.getTime() + diffMs * exitMult);
    const scLabel = scExit.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    cards[i].querySelector('.sc-gain').textContent  = sign + gain + '%';
    cards[i].querySelector('.sc-price').textContent = 'Target: $' + tgt;
    cards[i].querySelector('.sc-date').textContent  = 'Est. exit: ' + scLabel;
  });
}

function renderMarket(m) {
  if (!m || !m.spy_price) return;
  document.getElementById('mktBar').style.display = 'flex';
  document.getElementById('mktTrend').innerHTML =
    `<span class="mkt-tag" style="color:${m.trend_color};border-color:${m.trend_color}">${m.trend}</span>`;
  const spyChgCls = (m.spy_chg||0) >= 0 ? 'pos' : 'neg';
  document.getElementById('mktSpy').innerHTML =
    `$${m.spy_price} <span class="${spyChgCls}">(${m.spy_chg >= 0 ? '+' : ''}${m.spy_chg}%)</span>`;
  document.getElementById('mktSpyRsi').textContent = m.spy_rsi != null ? m.spy_rsi : 'N/A';
  const vixColor = m.vix >= 25 ? 'var(--red)' : m.vix >= 18 ? 'var(--yellow)' : 'var(--green)';
  document.getElementById('mktVix').innerHTML =
    `<span style="color:${vixColor}">${m.vix} <small style="font-weight:400">(${m.vix_label})</small></span>`;
  const qqqCls = (m.qqq_chg_1m||0) >= 0 ? 'pos' : 'neg';
  document.getElementById('mktQqq').innerHTML =
    `<span class="${qqqCls}">${m.qqq_chg_1m >= 0 ? '+' : ''}${m.qqq_chg_1m}%</span>`;
  const mMult = m.return_multiplier;
  const multColor = mMult >= 1.1 ? 'var(--green)' : mMult >= 0.9 ? 'var(--yellow)' : 'var(--red)';
  document.getElementById('mktMult').innerHTML =
    `<span style="color:${multColor}">${mMult}×</span>`;
  if (m.summary) document.getElementById('mktSummary').textContent = m.summary;
}

function renderTradePlan(d) {
  const tp = d.trade_plan;
  // Restore saved account size
  const saved = localStorage.getItem('swingEdgeAccount');
  if (saved) { document.getElementById('psAccount').value = saved; }
  const entryD = new Date(); entryD.setHours(12,0,0,0);
  const exitD  = new Date(entryD);
  let added = 0;
  while (added < tp.hold_days) {
    exitD.setDate(exitD.getDate() + 1);
    if (exitD.getDay() !== 0 && exitD.getDay() !== 6) added++;
  }
  document.getElementById('tpEntry').value = toISODate(entryD);
  document.getElementById('tpExit').value  = toISODate(exitD);
  document.getElementById('tpDays').textContent = tp.hold_days + ' trading days';
  document.getElementById('tpStop').textContent = '$' + tp.stop_loss;
  document.getElementById('tpStopPct').textContent = tp.stop_pct + '%';
  const rr = tp.rr_ratio;
  const rrEl = document.getElementById('tpRR');
  rrEl.textContent = rr + ':1';
  rrEl.className = 'value ' + (rr >= 2 ? 'pos' : rr >= 1 ? '' : 'neg');
  const ev = tp.expected_value;
  const evEl = document.getElementById('tpEV');
  evEl.textContent = (ev >= 0 ? '+' : '') + ev + '%';
  evEl.className = 'value ' + (ev > 0 ? 'pos' : ev < 0 ? 'neg' : 'neu');
  document.getElementById('tpConviction').textContent = tp.conviction;

  document.getElementById('tpScenarios').innerHTML = tp.scenarios.map(s => {
    const sign = s.gain_pct >= 0 ? '+' : '';
    return `<div class="scenario" style="border-color:${s.color};background:${s.color}14">
      <div class="sc-label" style="color:${s.color}">${s.label}</div>
      <div class="sc-prob">${s.probability}% probability</div>
      <div class="sc-gain" style="color:${s.color}">${sign}${s.gain_pct}%</div>
      <div class="sc-price">Target: $${s.price_target}</div>
      <div class="sc-date">Est. exit: ${s.exit_date}</div>
      <div class="sc-desc">${s.description}</div>
    </div>`;
  }).join('');

  const flags    = d.score.red_flags || [];
  const penalties = d.score.penalties || 0;
  let flagHtml = '';
  if (penalties > 0) flagHtml += `<div class="red-flag">⚠ ${penalties} penalty points applied to score</div>`;
  flags.forEach(f => { flagHtml += `<div class="red-flag">🚩 ${f}</div>`; });
  document.getElementById('tpRedFlags').innerHTML = flagHtml;
  calcPositionSize();
}

function renderMomentum(d) {
  const rvol = d.rvol || 0;
  document.getElementById('mRvol').textContent = rvol ? rvol + 'x' : 'N/A';
  document.getElementById('mRvol').className = rvol >= 1.5 ? 'pos' : rvol >= 1 ? '' : 'neg';
  document.getElementById('mRvolBar').style.width = Math.min(rvol / 3 * 100, 100) + '%';
  document.getElementById('mRvolBar').style.background = rvol >= 3 ? 'var(--green)' : rvol >= 1.5 ? 'var(--blue)' : 'var(--red)';
  const rvolNotes = rvol >= 3 ? '🔥 Exceptional volume — institutions likely active' : rvol >= 2 ? '✅ Strong unusual volume — good sign' : rvol >= 1.5 ? '👍 Above average — worth watching' : rvol >= 1 ? '😐 Normal volume — no edge yet' : '⚠ Below average volume — low conviction';
  document.getElementById('mRvolNote').textContent = rvolNotes;
  document.getElementById('mVol').textContent = fmt(d.volume);
  document.getElementById('mAvgVol').textContent = fmt(d.avg_volume);

  const rsi = d.rsi;
  document.getElementById('mRsi').textContent = rsi != null ? rsi : 'N/A';
  document.getElementById('mRsi').className = rsi > 70 ? 'neg' : rsi >= 55 ? 'pos' : rsi >= 40 ? '' : 'neg';
  if (rsi != null) document.getElementById('mRsiNeedle').style.left = (rsi / 100 * 100) + '%';
  const rsiNote = rsi > 75 ? 'Overbought — consider waiting for pullback' : rsi >= 60 ? 'Momentum zone — breakout territory' : rsi >= 40 ? 'Sweet spot — pullback in uptrend' : 'Weak momentum — potential oversold bounce';
  document.getElementById('mRsiNote').textContent = rsiNote || '';

  document.getElementById('mChg').innerHTML = `<span class="${colorClass(d.change_pct)}">${pct(d.change_pct)}</span>`;
  document.getElementById('mGap').innerHTML = `<span class="${colorClass(d.gap_pct)}">${pct(d.gap_pct)}</span>`;
  document.getElementById('mOpen').textContent = '$' + d.open_price;
  document.getElementById('mPrevClose').textContent = '$' + d.prev_close;

  document.getElementById('mMa50').textContent = d.ma50 ? '$' + d.ma50 : 'N/A';
  document.getElementById('mMa200').textContent = d.ma200 ? '$' + d.ma200 : 'N/A';
  document.getElementById('mA50').innerHTML = yesNo(d.above_50ma);
  document.getElementById('mA200').innerHTML = yesNo(d.above_200ma);
  document.getElementById('mWH').textContent = '$' + d.week_high;
  document.getElementById('mWL').textContent = '$' + d.week_low;
  document.getElementById('mProx').innerHTML = d.week52_proximity_pct != null
    ? `<span class="${d.week52_proximity_pct <= 10 ? 'pos' : ''}">${d.week52_proximity_pct}% below high</span>` : 'N/A';

  document.getElementById('mUpVol').textContent = fmt(d.avg_up_vol);
  document.getElementById('mDnVol').textContent = fmt(d.avg_dn_vol);
  const vr = d.vol_ratio;
  document.getElementById('mVolRatio').innerHTML = vr != null ? `<span class="${vr >= 1.5 ? 'pos' : vr < 1 ? 'neg' : ''}">${vr}x</span>` : 'N/A';
  document.getElementById('mVolStructNote').textContent = vr >= 1.5 ? '✅ Volume heavier on up days — bullish structure' : vr >= 1 ? 'Balanced — neutral volume structure' : '⚠ Heavier volume on down days — distribution signal';
}

function renderCatalyst(d) {
  const cats = d.catalysts || [];
  document.getElementById('cCatalysts').innerHTML = cats.length
    ? cats.map(c => `<span class="catalyst-tag ${c}">${c}</span>`).join('')
    : '<span style="color:var(--muted);font-size:13px">No specific catalysts detected in recent news</span>';

  document.getElementById('cRec').innerHTML = `<span class="${d.recommendation === 'BUY' || d.recommendation === 'STRONG_BUY' ? 'pos' : d.recommendation === 'SELL' ? 'neg' : ''}">${d.recommendation}</span>`;
  document.getElementById('cAna').textContent = d.analyst_count || 'N/A';
  document.getElementById('cTarget').textContent = d.target_price ? '$' + d.target_price : 'N/A';
  document.getElementById('cSector').textContent = d.sector;
  document.getElementById('cIndustry').textContent = d.industry;
  document.getElementById('cDesc').textContent = d.description;

  document.getElementById('cNews').innerHTML = d.news.length
    ? d.news.map(n => `
      <div class="news-item">
        <div class="news-title">${n.url ? `<a href="${n.url}" target="_blank">${n.title}</a>` : n.title}</div>
        <div class="news-meta"><span>${n.date || ''}</span><span>${n.source || ''}</span></div>
      </div>`).join('')
    : '<span style="color:var(--muted)">No recent news found</span>';

  document.getElementById('cInsiders').innerHTML = d.insider_trades.length
    ? d.insider_trades.map(i => `<div class="insider-item"><span>${i.name}</span><span style="color:var(--muted)">${i.date}</span></div>`).join('')
    : '<span style="color:var(--muted);font-size:13px">No recent Form 4 filings found</span>';
}

function renderRisk(d) {
  document.getElementById('rMcap').textContent = fmtB(d.market_cap);
  document.getElementById('rTier').textContent = d.cap_tier;
  const floatM = d.float_shares ? (d.float_shares / 1e6).toFixed(1) + 'M' : 'N/A';
  document.getElementById('rFloat').textContent = floatM;
  const fl = d.float_shares ? d.float_shares / 1e6 : null;
  document.getElementById('rFloatNote').textContent = fl
    ? fl < 20 ? '🔥 Micro float — can move fast and violently. High risk/reward.'
      : fl < 50 ? '⚡ Small float — good swing trading candidate'
      : fl < 100 ? '📊 Mid float — smoother moves, more liquidity'
      : '🏦 Large float — needs stronger catalyst to move significantly'
    : '';

  const sq = d.score.breakdown.squeeze || 0;
  document.getElementById('sqScore').textContent = sq + '/10';
  document.getElementById('sqScore').style.color = sq >= 7 ? 'var(--green)' : sq >= 4 ? 'var(--yellow)' : 'var(--muted)';

  document.getElementById('rShortPct').innerHTML = d.short_pct_float != null
    ? `<span class="${d.short_pct_float >= 20 ? 'pos' : ''}">${d.short_pct_float}%</span>` : 'N/A';
  document.getElementById('rDtc').textContent = d.days_to_cover != null ? d.days_to_cover + 'd' : 'N/A';
  document.getElementById('rBorrow').textContent = d.borrow_fee != null ? d.borrow_fee + '%' : 'N/A (broker feed needed)';
  document.getElementById('rUtil').textContent = d.utilization != null ? d.utilization + '%' : 'N/A (broker feed needed)';
  const sp = d.short_pct_float || 0;
  document.getElementById('rShortNote').textContent = sp >= 30 ? '🔥 Very high short interest — squeeze candidate. Watch for catalysts.'
    : sp >= 20 ? '⚡ Elevated short interest — squeeze possible on positive news'
    : sp >= 10 ? '📊 Moderate short interest — some squeeze potential'
    : '✅ Low short interest — move driven by fundamentals/momentum';

  document.getElementById('rAtr').textContent = d.atr ? '$' + d.atr : 'N/A';
  document.getElementById('rAvgVol').textContent = fmt(d.avg_volume);
  document.getElementById('rPe').textContent = d.pe_ratio || 'N/A';

  const risks = [];
  if ((d.float_shares||0) < 20e6) risks.push({level:'warn', text:'Low float — expect wide spreads and fast moves. Use limit orders.'});
  if ((d.short_pct_float||0) >= 20) risks.push({level:'info', text:'High short interest — positive catalyst could trigger squeeze.'});
  if ((d.rvol||0) < 1) risks.push({level:'warn', text:'Below average volume — lower conviction setup.'});
  if ((d.rsi||50) > 75) risks.push({level:'warn', text:'RSI overbought — consider waiting for pullback entry.'});
  if (d.above_50ma === false) risks.push({level:'danger', text:'Below 50-day MA — counter-trend trade, higher risk.'});
  if (d.above_200ma === false) risks.push({level:'warn', text:'Below 200-day MA — not in established uptrend.'});
  if (!risks.length) risks.push({level:'info', text:'No major red flags detected based on available data.'});
  document.getElementById('rRiskSummary').innerHTML = risks.map(r =>
    `<div style="padding:8px 12px;margin:6px 0;border-radius:6px;font-size:13px;background:${r.level==='danger'?'rgba(248,113,113,.1)':r.level==='warn'?'rgba(251,191,36,.08)':'rgba(96,165,250,.08)'};border-left:3px solid ${r.level==='danger'?'var(--red)':r.level==='warn'?'var(--yellow)':'var(--blue)'}">${r.text}</div>`
  ).join('');

  const bd = d.score.breakdown;
  const labels = {momentum:'Momentum (30)',rvol:'Rel Volume (25)',catalyst:'Catalyst (15)',float:'Float (10)',trend:'Trend (10)',squeeze:'Squeeze (10)'};
  const maxes  = {momentum:30,rvol:25,catalyst:15,float:10,trend:10,squeeze:10};
  document.getElementById('rScoreDetail').innerHTML = Object.keys(bd).map(k => {
    const pctFill = (bd[k] / maxes[k]) * 100;
    const col = pctFill >= 75 ? 'var(--green)' : pctFill >= 50 ? 'var(--blue)' : 'var(--yellow)';
    return `<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
        <span style="color:var(--muted)">${labels[k]}</span><span style="font-weight:700">${bd[k]}/${maxes[k]}</span>
      </div>
      <div class="gauge-bar"><div class="gauge-fill" style="width:${pctFill}%;background:${col}"></div></div>
    </div>`;
  }).join('');
}

function renderChart(d) {
  if (priceChart) { priceChart.destroy(); priceChart = null; }
  const ctx = document.getElementById('priceChart').getContext('2d');
  const labels = d.chart.map(c => c.date);
  const prices = d.chart.map(c => c.close);
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: prices,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.08)',
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        tension: 0.3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#7c8db5', maxTicksLimit: 6, font: {size:10} }, grid: { color: '#2a3045' } },
        y: { ticks: { color: '#7c8db5', font: {size:10} }, grid: { color: '#2a3045' } }
      }
    }
  });
}

// ── Perplexity ────────────────────────────────────────────────────────────────
function savePerpInput() {
  const text = document.getElementById('perpInput').value.trim();
  if (!text) return;
  const out = document.getElementById('perpOutput');
  out.textContent = text;
  out.style.display = 'block';
}

// ── Watchlist ─────────────────────────────────────────────────────────────────
async function addToWatchlist() {
  if (!currentData) return;
  await fetch('/watchlist/add', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ticker: currentData.ticker})
  });
  loadWatchlist();
}

async function removeFromWatchlist(ticker) {
  await fetch('/watchlist/remove', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ticker})
  });
  loadWatchlist();
}

async function loadWatchlist() {
  const res = await fetch('/watchlist');
  const wl = await res.json();
  const el = document.getElementById('wlList');
  if (!wl.length) { el.innerHTML = '<div class="wl-empty">No stocks saved yet</div>'; return; }
  el.innerHTML = wl.map(w => `
    <div class="wl-item">
      <div onclick="loadTicker('${w.ticker}')" style="flex:1">
        <div class="wl-ticker">${w.ticker}</div>
        <div class="wl-date">${w.added}</div>
      </div>
      <span class="wl-remove" onclick="removeFromWatchlist('${w.ticker}')">×</span>
    </div>`).join('');
}

function loadTicker(ticker) {
  document.getElementById('tickerInput').value = ticker;
  analyze();
}

loadWatchlist();

// ── Scanner ───────────────────────────────────────────────────────────────────
async function openScanner() {
  const modal = document.getElementById('scanModal');
  modal.style.display = 'flex';
  document.getElementById('scanLoading').style.display = 'block';
  document.getElementById('scanResults').style.display = 'none';
  document.getElementById('scanSubtitle').textContent = 'Scanning 60 stocks across US & TSX…';

  try {
    const res  = await fetch('/scan?min_score=70');
    const data = await res.json();
    document.getElementById('scanLoading').style.display = 'none';

    if (!data.success || !data.results.length) {
      document.getElementById('scanResults').innerHTML =
        '<div style="text-align:center;padding:40px;color:var(--muted)">No stocks scored 70+ right now. Market conditions may be weak.</div>';
      document.getElementById('scanResults').style.display = 'block';
      return;
    }

    document.getElementById('scanSubtitle').textContent =
      `Found ${data.results.length} setup${data.results.length !== 1 ? 's' : ''} out of ${data.scanned} stocks scanned`;

    document.getElementById('scanResults').innerHTML = data.results.map(r => {
      const chgCls  = r.change_pct >= 0 ? 'pos' : 'neg';
      const chgSign = r.change_pct >= 0 ? '+' : '';
      return `
        <div onclick="loadTicker('${r.ticker}'); closeScanner();"
          style="display:flex;align-items:center;gap:16px;padding:12px;border-radius:8px;border:1px solid var(--border);margin-bottom:8px;cursor:pointer;background:var(--card)"
          onmouseover="this.style.borderColor='${r.color}'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="min-width:52px;text-align:center">
            <div style="font-size:22px;font-weight:900;color:${r.color}">${r.score}</div>
            <div style="font-size:9px;color:var(--muted);text-transform:uppercase">/100</div>
          </div>
          <div style="flex:1;min-width:0">
            <div style="font-weight:800;font-size:14px">${r.ticker} <span style="font-weight:400;color:var(--muted);font-size:12px">${r.name}</span></div>
            <div style="font-size:11px;color:var(--muted);margin-top:2px">${r.sector} · ${r.cap_tier}</div>
          </div>
          <div style="text-align:right;min-width:90px">
            <div style="font-weight:700">$${r.price}</div>
            <div class="${chgCls}" style="font-size:12px">${chgSign}${r.change_pct?.toFixed(2)}%</div>
          </div>
          <div style="text-align:right;min-width:70px">
            <div style="font-size:11px;color:var(--muted)">RVOL</div>
            <div style="font-weight:700;color:${(r.rvol||0)>=2?'var(--green)':'var(--text)'}">${r.rvol ?? 'N/A'}x</div>
          </div>
          <div style="min-width:90px;text-align:right">
            <div style="font-size:11px;font-weight:700;color:${r.color};border:1px solid ${r.color};border-radius:20px;padding:3px 10px;display:inline-block">${r.rating}</div>
          </div>
        </div>`;
    }).join('');

    document.getElementById('scanResults').style.display = 'block';
  } catch (e) {
    document.getElementById('scanLoading').innerHTML =
      `<div style="color:var(--red)">Scan failed: ${e.message}</div>`;
  }
}

function closeScanner() {
  document.getElementById('scanModal').style.display = 'none';
}
