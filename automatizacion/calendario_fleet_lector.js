/* Lector del calendario de la Fleet Tool (https://fleet.glovoapp.com/calendar) para la pestaña Capacidad.
   Se pega en la consola / javascript_tool estando en la página del calendario con la sesión iniciada.
   1) Este bloque instala window.__calLeer(ciudad, fechas) y window.__calExport().
   2) await window.__calLeer('GRA', ['2026-11-02', ...])  -> lee cada día (todas las páginas de riders)
   3) window.__calExport()                                  -> texto compacto, una línea por ciudad-día:
        CIU AAAA-MM-DD tot=N b=48 números separados por comas nc=idx:n,... ev=idx:n,...
      b = media hora reservada y presentada · nc = reservada sin registro (no show) · ev = en evaluación.
      tot = suma de b+nc+ev (control: calendario_fleet_json.py lo comprueba).
   No lee ni guarda credenciales: solo escucha las respuestas que la propia página pide a su API. */
(() => {
  const RX = /3pl\/fleet\/cities\/[A-Z]+\/couriers/;
  window.__cap = window.__cap || [];
  window.__AGG = window.__AGG || {};
  if (!window.__patched) {
    window.__patched = 1;
    const of = window.fetch;
    window.fetch = async function (...a) {
      const r = await of.apply(this, a);
      try { const u = (a[0] && a[0].url) || String(a[0]); if (RX.test(u)) r.clone().text().then(t => window.__cap.push({ u, t })); } catch (e) {}
      return r;
    };
    const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u, ...x) { this.__u = u; return oo.call(this, m, u, ...x); };
    XMLHttpRequest.prototype.send = function (...x) {
      this.addEventListener('load', () => { if (RX.test(this.__u)) window.__cap.push({ u: this.__u, t: this.responseText }); });
      return os.apply(this, x);
    };
  }
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const waitFor = async (pred, ms = 15000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (pred()) return true; await sleep(200); } return false; };
  const fmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });

  window.__calLeer = async (CITY, DATES) => {
    const log = [];
    const match = (c, D) => c.u.includes('date=' + D) && c.u.includes('cities/' + CITY + '/') && c.u.includes('pageSize=50');
    const csel = () => document.querySelector('select[aria-label="Selector de ciudades"]');
    if (!csel()) return 'ERROR: no estoy en el calendario (¿sesión caducada?)';
    if (csel().value !== CITY) { const n0 = window.__cap.length; csel().value = CITY; csel().dispatchEvent(new Event('change', { bubbles: true })); await waitFor(() => window.__cap.length > n0); await sleep(500); }
    const lis = () => document.querySelectorAll('.easy-data-table__rows-selector li');
    if (!lis()[1].classList.contains('selected')) { const n0 = window.__cap.length; lis()[1].click(); await waitFor(() => window.__cap.length > n0); await sleep(300); }
    for (const D of DATES) {
      window.__cap = [];
      const inp = document.querySelector('[data-test="dp-input"]');
      const want = D.split('-').reverse().join('/');
      if (inp.value !== want) {
        let cell = null;
        for (let t = 0; t < 4 && !cell; t++) {
          if (!document.getElementById(D)) {
            if (!document.querySelector('.dp__calendar_item')) { inp.click(); await sleep(600); }
            else { const navs = document.querySelectorAll('.dp__inner_nav'); if (navs.length) navs[navs.length - 1].click(); await sleep(500); }
          }
          cell = document.getElementById(D);
        }
        if (!cell) { log.push(D + ': sin celda'); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); continue; }
        (cell.querySelector('.dp__cell_inner') || cell).click();
        if (!await waitFor(() => window.__cap.some(c => match(c, D)))) { log.push(D + ': sin respuesta'); continue; }
      } else {
        let n0 = window.__cap.length; lis()[0].click(); await waitFor(() => window.__cap.length > n0);
        n0 = window.__cap.length; lis()[1].click(); await waitFor(() => window.__cap.some(c => match(c, D)));
      }
      await sleep(300);
      const got = () => { const s = {}; let all = 1; for (const c of window.__cap) if (match(c, D)) { const j = JSON.parse(c.t); s[j.pageNumber] = j; all = j.allPages; } return [s, all]; };
      let g = 0;
      while (g++ < 15) {
        const [s, all] = got(); const have = Object.keys(s).map(Number);
        const missing = [...Array(all).keys()].map(i => i + 1).filter(p => !have.includes(p));
        if (!missing.length) break;
        const curPage = Math.floor((parseInt(document.querySelector('.pagination__items-index').innerText) - 1) / 50) + 1;
        const btn = missing[0] < curPage ? document.querySelector('.previous-page__click-button') : document.querySelector('.next-page__click-button');
        const n0 = window.__cap.length; btn.click(); await waitFor(() => window.__cap.length > n0); await sleep(250);
      }
      const [s, all] = got();
      if (Object.keys(s).length < all) { log.push(D + ': INCOMPLETO ' + Object.keys(s).length + '/' + all); continue; }
      const b = Array(48).fill(0), nc = Array(48).fill(0), ev = Array(48).fill(0); let n = 0;
      for (const j of Object.values(s)) for (const co of j.couriers) for (const sl of co.slots || []) {
        const p = Object.fromEntries(fmt.formatToParts(new Date(sl.startTime)).map(x => [x.type, x.value]));
        if (p.year + '-' + p.month + '-' + p.day !== D) continue;
        const i = (+p.hour % 24) * 2 + (+p.minute >= 30 ? 1 : 0);
        if (String(sl.status).startsWith('BEING_EVALUATED')) ev[i]++;
        else if (sl.notCheckedIn) nc[i]++;
        else b[i]++;
        n++;
      }
      window.__AGG[CITY + '|' + D] = { b, nc, ev, n };
      log.push(D + ': ' + n);
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    }
    return CITY + ' · ' + log.join(' · ');
  };

  /* ---- Demanda (página https://fleet.glovoapp.com/demand): riders y pedidos forecast por media hora ----
     await window.__demLeer('GRA', [...fechas])  ·  window.__demExport() -> líneas
        DEM CIU AAAA-MM-DD r=48 números (total_rider_demand) o=48 números (forecasted_orders) tot=suma r otot=suma o
     Si la ciudad tiene varias zonas, se suman. */
  window.__DEM = window.__DEM || {};
  window.__dm = window.__dm || [];
  if (!window.__patchedDem) {
    window.__patchedDem = 1;
    const RD = /rider_demand\/v2\//;
    const of2 = window.fetch;
    window.fetch = async function (...a) {
      const r = await of2.apply(this, a);
      try { const u = (a[0] && a[0].url) || String(a[0]); if (RD.test(u)) r.clone().text().then(t => window.__dm.push({ u, t })); } catch (e) {}
      return r;
    };
    const oo2 = XMLHttpRequest.prototype.open, os2 = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u, ...x) { this.__u2 = u; return oo2.call(this, m, u, ...x); };
    XMLHttpRequest.prototype.send = function (...x) {
      this.addEventListener('load', () => { if (RD.test(this.__u2 || '')) window.__dm.push({ u: this.__u2, t: this.responseText }); });
      return os2.apply(this, x);
    };
  }
  window.__demLeer = async (CITY, DATES) => {
    const log = [];
    const csel = () => document.querySelector('select[aria-label="Selector de ciudades"]');
    const zsel = () => document.querySelector('select[aria-label="Zones selector"]');
    if (!csel() || !location.pathname.startsWith('/demand')) return 'ERROR: no estoy en la página de Demanda (¿sesión caducada?)';
    window.__dm = [];
    if (csel().value === CITY) {   // forzar una petición nueva de la fecha que ya está elegida
      const otra = [...csel().options].map(x => x.value).find(v => v !== CITY);
      const n0 = window.__dm.length; csel().value = otra; csel().dispatchEvent(new Event('change', { bubbles: true })); await waitFor(() => window.__dm.length > n0); await sleep(400);
      window.__dm = [];
    }
    { const n0 = window.__dm.length; csel().value = CITY; csel().dispatchEvent(new Event('change', { bubbles: true })); await waitFor(() => window.__dm.length > n0); await sleep(600); }
    const zonas = zsel() ? [...zsel().options].map(o => o.value) : [null];
    for (const D of DATES) {
      const r = Array(48).fill(0), o = Array(48).fill(0); let ok = true;
      for (const Z of zonas) {
        if (Z && zsel().value !== Z) { const n0 = window.__dm.length; zsel().value = Z; zsel().dispatchEvent(new Event('change', { bubbles: true })); await waitFor(() => window.__dm.length > n0); await sleep(300); }
        const rx = new RegExp('rider_demand/v2/' + CITY + '/' + (Z || '[^/]+') + '/' + D);
        if (!window.__dm.some(c => rx.test(c.u))) {
          const inp = document.querySelector('[data-test="dp-input"]');
          let cell = null;
          for (let t = 0; t < 4 && !cell; t++) {
            if (!document.getElementById(D)) {
              if (!document.querySelector('.dp__calendar_item')) { inp.click(); await sleep(600); }
              else { const navs = document.querySelectorAll('.dp__inner_nav'); if (navs.length) navs[navs.length - 1].click(); await sleep(500); }
            }
            cell = document.getElementById(D);
          }
          if (!cell) { ok = false; log.push(D + ': sin celda'); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); break; }
          (cell.querySelector('.dp__cell_inner') || cell).click();
          if (!await waitFor(() => window.__dm.some(c => rx.test(c.u)))) {
            // misma fecha ya seleccionada: forzar recarga cambiando de zona/ciudad no es necesario si ya hay captura
            ok = false; log.push(D + ': sin respuesta'); break;
          }
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        }
        const c = [...window.__dm].reverse().find(x => rx.test(x.u));
        let j; try { j = JSON.parse(c.t); } catch (e) { ok = false; log.push(D + ': respuesta no válida'); break; }
        for (const it of j.items || []) {
          const m = String(it.slot_id).match(/^(\d\d):(\d\d)/); if (!m) continue;
          const i = (+m[1]) * 2 + (+m[2] >= 30 ? 1 : 0);
          r[i] += +it.total_rider_demand || 0; o[i] += +it.forecasted_orders || 0;
        }
      }
      if (!ok) continue;
      window.__DEM[CITY + '|' + D] = { r, o };
      log.push(D + ': ' + r.reduce((a, b) => a + b, 0) / 2 + ' h');
    }
    return 'DEM ' + CITY + ' · ' + log.join(' · ');
  };
  window.__demExport = () => Object.entries(window.__DEM).sort().map(([k, v]) => {
    const [c, d] = k.split('|');
    return `DEM ${c} ${d} r=${v.r.join(',')} o=${v.o.join(',')} tot=${v.r.reduce((a, b) => a + b, 0)} otot=${Math.round(v.o.reduce((a, b) => a + b, 0) * 10) / 10}`;
  }).join('\n');

  window.__calExport = () => Object.entries(window.__AGG).sort().map(([k, v]) => {
    const [c, d] = k.split('|');
    const sp = a => a.map((x, i) => x ? i + ':' + x : '').filter(Boolean).join(',');
    return `${c} ${d} tot=${v.n} b=${v.b.join(',')} nc=${sp(v.nc)} ev=${sp(v.ev)}`;
  }).join('\n');
  return 'lector instalado';
})();
