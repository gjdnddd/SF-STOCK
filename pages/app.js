(() => {
  'use strict';

  // 검색 범위 이름 -> data/ 소스 키 (scripts/build_pages.py 의 LIGHT/HEAVY 와 일치)
  const SCOPES = [
    ['코어테마', 'core'],
    ['전체테마', 'all'],
    ['기사', 'article'],
    ['대장이력', 'leader'],
    ['키워드요약', 'keyword'],
    ['기사본문', 'body'],
    ['K스윙 정리', 'kswing'],
  ];
  const SRC_OF = Object.fromEntries(SCOPES);
  const TABS = [
    ['📰 기사', 'article'],
    ['🎯 코어테마', 'core'],
    ['🥇 대장이력', 'leader'],
    ['💡 키워드요약', 'keyword'],
    ['🌐 전체테마', 'all'],
    ['📝 기사본문', 'body'],
    ['📊 K스윙', 'kswing'],
  ];
  const LIGHT = new Set(['core', 'all', 'leader']);
  const CHO = [...'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'];
  const CHO_SET = new Set([...CHO, ' ']);

  const state = {
    menu: 'filter',
    scope: new Set(['코어테마']),
    mode: 'contains',
    input: '',
    keyword: null,
    selectedStock: '',
    tab: 0,
  };
  let light = null;
  let themes = [];
  let indexOf = new Map();
  const colCache = {};
  let resultSeq = 0;
  let tabSeq = 0;
  let debounce = null;

  const $ = (id) => document.getElementById(id);

  async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} (${res.status})`);
    return res.json();
  }

  function getCol(src) {
    if (LIGHT.has(src)) return Promise.resolve(light[src]);
    if (!colCache[src]) {
      colCache[src] = fetchJson(`data/${src}.json`).catch((e) => {
        delete colCache[src];
        throw e;
      });
    }
    return colCache[src];
  }

  function chosung(text) {
    let out = '';
    for (const ch of String(text)) {
      const c = ch.charCodeAt(0);
      if (c >= 0xac00 && c <= 0xd7a3) out += CHO[Math.floor((c - 0xac00) / 588)];
      else out += ch.toLowerCase();
    }
    return out;
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function exactMatch(cell, keyword) {
    if (!cell) return false;
    const kw = keyword.toLowerCase();
    for (const item of cell.split(/[,.\s]+/)) {
      if (item.replace(/[0-9\-_]/g, '').trim().toLowerCase() === kw) return true;
    }
    return false;
  }

  function sortKey(core, keyword) {
    const m = core.replace(/ /g, '').match(new RegExp(escapeRegExp(keyword) + '(\\d+)'));
    return m ? parseInt(m[1], 10) : 0;
  }

  function setStatus(msg) {
    $('status').textContent = msg;
  }

  function fillSelect(select, values) {
    const frag = document.createDocumentFragment();
    for (const v of values) {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      frag.appendChild(opt);
    }
    select.replaceChildren(frag);
  }

  // ---- 메뉴 ----
  function showMenu(menu) {
    state.menu = menu;
    $('view-filter').hidden = menu !== 'filter';
    $('view-detail').hidden = menu !== 'detail';
    document.querySelectorAll('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.menu === menu));
    if (menu === 'detail') renderDetail();
    window.scrollTo(0, 0);
  }

  // ---- 테마 필터 ----
  function updateThemes() {
    const q = state.input;
    if (!q || state.scope.size === 0) {
      $('kw-wrap').hidden = true;
      $('results').hidden = true;
      setStatus('');
      return;
    }
    const isCho = [...q].every((ch) => CHO_SET.has(ch));
    const ql = q.toLowerCase();
    const filtered = themes.filter((t) => (isCho ? chosung(t).includes(q) : t.toLowerCase().includes(ql)));
    if (!filtered.includes(q)) filtered.unshift(q);

    fillSelect($('kw'), filtered);
    state.keyword = filtered.includes(state.keyword) ? state.keyword : filtered[0];
    $('kw').value = state.keyword;
    $('kw-wrap').hidden = false;
    updateResults();
  }

  async function updateResults() {
    const seq = ++resultSeq;
    const kw = state.keyword;
    if (!kw || state.scope.size === 0) {
      $('results').hidden = true;
      return;
    }
    setStatus('검색 중…');
    let cols;
    try {
      cols = await Promise.all([...state.scope].map((name) => getCol(SRC_OF[name])));
    } catch (e) {
      if (seq === resultSeq) setStatus(`데이터를 불러오지 못했습니다: ${e.message}`);
      return;
    }
    if (seq !== resultSeq) return;

    const exact = state.mode === 'exact';
    const kwl = kw.toLowerCase();
    const hits = [];
    for (let i = 0; i < light.names.length; i++) {
      for (const col of cols) {
        const cell = col[i];
        if (exact ? exactMatch(cell, kw) : cell.toLowerCase().includes(kwl)) {
          hits.push(i);
          break;
        }
      }
    }
    const keyed = hits.map((i) => [i, sortKey(light.core[i], kw)]);
    keyed.sort((a, b) => b[1] - a[1]);
    renderResults(keyed.map((k) => k[0]));
    setStatus('');
  }

  function renderResults(idxs) {
    $('results').hidden = false;
    $('empty').hidden = idxs.length > 0;
    $('tbl').hidden = idxs.length === 0;

    const target = $('target');
    fillSelect(target, ['선택 안함', ...idxs.map((i) => light.names[i])]);
    target.value = '선택 안함';

    const frag = document.createDocumentFragment();
    for (const i of idxs) {
      const tr = document.createElement('tr');
      for (const text of [light.names[i], light.core[i], light.all[i], light.leader[i]]) {
        const td = document.createElement('td');
        td.textContent = text;
        tr.appendChild(td);
      }
      frag.appendChild(tr);
    }
    $('tbl').tBodies[0].replaceChildren(frag);
  }

  // ---- 종목 상세 ----
  function renderDetail() {
    const sel = $('stock-select');
    if (sel.options.length === 0) fillSelect(sel, light.names);
    if (!indexOf.has(state.selectedStock)) state.selectedStock = light.names[0];
    sel.value = state.selectedStock;
    $('report-title').textContent = `🔍 ${state.selectedStock} 분석 리포트`;
    renderTabs();
    renderTabContent();
  }

  function renderTabs() {
    const wrap = $('tabs');
    if (wrap.childElementCount === 0) {
      TABS.forEach(([label], i) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'tab';
        b.textContent = label;
        b.addEventListener('click', () => {
          state.tab = i;
          renderTabs();
          renderTabContent();
        });
        wrap.appendChild(b);
      });
    }
    [...wrap.children].forEach((b, i) => b.classList.toggle('active', i === state.tab));
  }

  async function renderTabContent() {
    const seq = ++tabSeq;
    const box = $('tab-content');
    box.textContent = '불러오는 중…';
    try {
      const col = await getCol(TABS[state.tab][1]);
      if (seq !== tabSeq) return;
      box.textContent = (col[indexOf.get(state.selectedStock)] || '').trim() || '정보 없음';
    } catch (e) {
      if (seq === tabSeq) box.textContent = `데이터를 불러오지 못했습니다: ${e.message}`;
    }
  }

  // ---- 초기화 ----
  function bindEvents() {
    document.querySelectorAll('.nav-btn').forEach((b) => b.addEventListener('click', () => showMenu(b.dataset.menu)));

    const chips = $('scope-chips');
    for (const [name] of SCOPES) {
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = state.scope.has(name);
      cb.addEventListener('change', () => {
        if (cb.checked) state.scope.add(name);
        else state.scope.delete(name);
        updateThemes();
      });
      label.append(cb, name);
      chips.appendChild(label);
    }

    document.querySelectorAll('input[name="mode"]').forEach((r) =>
      r.addEventListener('change', () => {
        state.mode = r.value;
        updateResults();
      })
    );

    $('q').addEventListener('input', (e) => {
      state.input = e.target.value;
      clearTimeout(debounce);
      debounce = setTimeout(updateThemes, 200);
    });
    $('kw').addEventListener('change', (e) => {
      state.keyword = e.target.value;
      updateResults();
    });
    $('target').addEventListener('change', (e) => {
      if (e.target.value !== '선택 안함') state.selectedStock = e.target.value;
    });
    $('go-detail').addEventListener('click', () => {
      if (state.selectedStock) showMenu('detail');
    });
    $('back').addEventListener('click', () => showMenu('filter'));
    $('stock-select').addEventListener('change', (e) => {
      state.selectedStock = e.target.value;
      renderDetail();
    });
  }

  async function init() {
    try {
      [light, themes] = await Promise.all([fetchJson('data/light.json'), fetchJson('data/themes.json')]);
    } catch (e) {
      const box = $('fatal');
      box.hidden = false;
      box.textContent = `데이터를 불러오지 못했습니다: ${e.message}`;
      return;
    }
    light.names.forEach((n, i) => indexOf.set(n, i));
    $('built').textContent = `데이터 갱신: ${light.built}`;
    bindEvents();
  }

  init();
})();
