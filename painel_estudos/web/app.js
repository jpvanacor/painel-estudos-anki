/* Painel de Estudos: the page. It asks Python for data through pycmd("pe:" + JSON). */
(() => {
  "use strict";

  const S = {
    base: "",
    view: "home",
    args: {},
    busy: false,
    syncing: false,
    card: null, // current card, as sent by Python
    phase: null, // "question", "answer" (normal cards) or "result" (after choosing)
    answer: null,
    result: null,
    enter: false, // animate the next card in
    fx: { sound: true, volume: 0.7, motion: true },
    reduceMotion: false,
    ro: null, // the Roleta, as sent by Python: {state, decks, can_undo, fx}
    roTab: "hist",
    roFilter: "all",
    roQuery: "",
    roCounts: null, // cards per topic of one matéria: {cat, counts: {tid: {n, ambiguous}}}
    reason: null, // why the current card was missed, chosen after a wrong answer
    returnTo: null, // where Encerrar goes after a topic or error session
    errDays: 7,
  };

  // ---------------------------------------------------------------- helpers
  const appEl = () => document.getElementById("app");
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const pct = (x) => (x == null ? "sem dados" : `${Math.round(x * 100)}%`);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
  const round = (n) => Math.round(Number(n) || 0);
  const norm = (s) =>
    String(s ?? "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();

  function fmtWhen(ts) {
    if (!ts || ts < 1e12) return "";
    const d = new Date(ts);
    const now = new Date();
    const diff = (now - d) / 1000;
    const p = (n) => String(n).padStart(2, "0");
    const hm = p(d.getHours()) + ":" + p(d.getMinutes());
    if (diff < 60) return "agora";
    if (diff < 3600) return "há " + Math.floor(diff / 60) + " min";
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const dd = Math.round((day(now) - day(d)) / 864e5);
    if (dd === 0) return "hoje, " + hm;
    if (dd === 1) return "ontem, " + hm;
    if (dd > 1 && dd < 7) return "há " + dd + " dias";
    return p(d.getDate()) + "/" + p(d.getMonth() + 1) + (d.getFullYear() !== now.getFullYear() ? "/" + d.getFullYear() : "");
  }

  function api(m, a = {}, opts = {}) {
    return new Promise((resolve, reject) => {
      const send = () => {
        if (typeof window.pycmd !== "function") return setTimeout(send, 25);
        window.pycmd("pe:" + JSON.stringify({ m, a }), (res) => {
          if (res && res.error) {
            if (!opts.quiet) toast(res.error, { error: true });
            reject(new Error(res.error));
          } else resolve(res);
        });
      };
      send();
    });
  }

  async function guarded(fn) {
    if (S.busy) return;
    S.busy = true;
    try {
      await fn();
    } catch (err) {
      /* the error is already shown */
    } finally {
      S.busy = false;
    }
  }

  let toastTimer;
  function toast(message, opts = {}) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      el.innerHTML = '<span class="toast-msg"></span><button class="toast-act" type="button" hidden></button>';
      document.body.appendChild(el);
    }
    el.querySelector(".toast-msg").textContent = message;
    const act = el.querySelector(".toast-act");
    act.hidden = !opts.action;
    act.onclick = null;
    if (opts.action) {
      act.textContent = opts.action.label;
      act.onclick = () => {
        el.hidden = true;
        opts.action.fn();
      };
    }
    el.classList.toggle("error", !!opts.error);
    el.hidden = false;
    animate(el, "toast-in");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), opts.error || opts.action ? 6500 : 2800);
  }

  const ICON = (() => {
    const svg = (d, s = 18, w = 2) =>
      `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
    return {
      soundOn: svg('<path d="M11 5 6 9H3v6h3l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>'),
      soundOff: svg('<path d="M11 5 6 9H3v6h3l5 4V5z"/><path d="m22 9-6 6M16 9l6 6"/>'),
      note: svg('<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>', 16),
      undo: svg('<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>', 16),
      trash: svg('<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/>', 16),
      edit: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>', 16),
      x: svg('<path d="M18 6 6 18M6 6l12 12"/>', 16),
    };
  })();

  // ---------------------------------------------------------------- sound
  // Sounds are made with the Web Audio API, no files. The Roleta's are the same as in the app.
  const SOUNDS = {
    spin: () => [{ f: 170, d: 0.32, type: "sawtooth", g: 0.04, slide: 50 }],
    tick: (i = 0) => [{ f: 980 + (i % 5) * 45, d: 0.028, type: "triangle", g: 0.05 }],
    reveal: () => [523.25, 659.25, 783.99].map((f, i) => ({ f, d: 0.34, g: 0.085, at: i * 0.11 })),
    cycle: () => [523.25, 659.25, 783.99, 1046.5].map((f, i) => ({ f, d: 0.42, g: 0.08, at: i * 0.1 })),
    reset: () => [392, 294, 392].map((f, i) => ({ f, d: 0.2, type: "triangle", g: 0.06, at: i * 0.14 })),
    mark: () => [
      { noise: true, d: 0.035, filter: "bandpass", fq: 3600, q: 1.4, g: 0.07 },
      { f: 1250, d: 0.03, type: "triangle", g: 0.025 },
    ],
    right: () => [
      { f: 659.25, d: 0.15, g: 0.07, at: 0.02 },
      { f: 987.77, d: 0.26, g: 0.075, at: 0.1 },
    ],
    wrong: () => [
      { f: 246.94, d: 0.26, type: "triangle", g: 0.08, slide: 207.65 },
      { f: 164.81, d: 0.32, g: 0.05, at: 0.06 },
    ],
    flip: () => [{ noise: true, d: 0.1, filter: "bandpass", fq: 1900, q: 0.6, g: 0.03, attack: 0.02 }],
    next: () => [{ noise: true, d: 0.16, filter: "bandpass", fq: 2600, q: 0.5, g: 0.035, attack: 0.03 }],
    undo: () => [
      { f: 660, d: 0.16, type: "triangle", g: 0.05, slide: 440 },
      { noise: true, d: 0.08, filter: "bandpass", fq: 1600, q: 0.7, g: 0.025 },
    ],
    goal: () =>
      [523.25, 659.25, 783.99, 1046.5, 1318.51]
        .map((f, i) => ({ f, d: 0.36, g: 0.07, at: i * 0.09 }))
        .concat([
          { noise: true, d: 0.1, filter: "lowpass", fq: 420, q: 0.7, g: 0.16, at: 0.5 },
          { f: 98, d: 0.14, g: 0.08, at: 0.5 },
        ]),
    done: () => [659.25, 830.61, 987.77, 1318.51].map((f, i) => ({ f, d: 0.4, g: 0.07, at: i * 0.1 })),
  };

  function schedule(ctx, dest, notes, t0) {
    for (const n of notes) {
      const t = t0 + (n.at || 0);
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(n.g || 0.06, t + (n.attack || 0.004));
      gain.gain.exponentialRampToValueAtTime(0.0001, t + n.d);
      gain.connect(dest);
      if (n.noise) {
        const length = Math.max(1, Math.floor(ctx.sampleRate * n.d));
        const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        const filter = ctx.createBiquadFilter();
        filter.type = n.filter || "bandpass";
        filter.frequency.value = n.fq || 2000;
        filter.Q.value = n.q || 0.8;
        source.connect(filter);
        filter.connect(gain);
        source.start(t);
        source.stop(t + n.d + 0.02);
      } else {
        const osc = ctx.createOscillator();
        osc.type = n.type || "sine";
        osc.frequency.setValueAtTime(n.f, t);
        if (n.slide) osc.frequency.exponentialRampToValueAtTime(n.slide, t + n.d);
        osc.connect(gain);
        osc.start(t);
        osc.stop(t + n.d + 0.03);
      }
    }
  }

  let audio = null;
  function audioOut() {
    if (!S.fx.sound) return null;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try {
      if (!audio) {
        const ctx = new AC();
        const master = ctx.createGain();
        master.connect(ctx.destination);
        audio = { ctx, master };
      }
      audio.master.gain.value = S.fx.volume;
      if (audio.ctx.state === "suspended") audio.ctx.resume();
      return audio;
    } catch (err) {
      return null;
    }
  }

  function play(name, arg) {
    const out = audioOut();
    if (!out || !SOUNDS[name]) return;
    try {
      schedule(out.ctx, out.master, SOUNDS[name](arg), out.ctx.currentTime + 0.01);
    } catch (err) {
      /* no sound, no harm */
    }
  }

  // For tests: renders a sound offline and measures it (peak and RMS level).
  async function renderSound(name, arg) {
    const notes = SOUNDS[name](arg);
    const seconds = Math.max(...notes.map((n) => (n.at || 0) + n.d)) + 0.1;
    const rate = 44100;
    const ctx = new OfflineAudioContext(1, Math.ceil(rate * seconds), rate);
    schedule(ctx, ctx.destination, notes, 0);
    const data = (await ctx.startRendering()).getChannelData(0);
    let peak = 0;
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      peak = Math.max(peak, Math.abs(data[i]));
      sum += data[i] * data[i];
    }
    return { name, seconds: +seconds.toFixed(2), peak: +peak.toFixed(3), rms: +Math.sqrt(sum / data.length).toFixed(4) };
  }

  // ---------------------------------------------------------------- motion
  // Anki's own "reduce motion" option starts switched on for everyone, so it is not taken as a
  // choice here; the panel's Animações switch and the system setting decide.
  function motionOK() {
    const reduced = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false;
    return S.fx.motion && !reduced;
  }

  function applyFx() {
    document.documentElement.classList.toggle("no-motion", !motionOK());
  }

  function animate(el, cls) {
    if (!el || !motionOK()) return;
    el.classList.remove(cls);
    void el.offsetWidth; // restart the animation
    el.classList.add(cls);
    // children animations bubble up here too; only the element's own ending removes the class
    const done = (ev) => {
      if (ev.target !== el) return;
      el.classList.remove(cls);
      el.removeEventListener("animationend", done);
    };
    el.addEventListener("animationend", done);
  }

  function soundButton() {
    return `<button class="btn quiet icon" data-act="toggle-sound" aria-pressed="${S.fx.sound}" title="${S.fx.sound ? "Som ligado: clique para desligar" : "Som desligado: clique para ligar"}">${S.fx.sound ? ICON.soundOn : ICON.soundOff}<span class="sr-only">Som</span></button>`;
  }

  async function setFx(changes) {
    const res = await api("set_fx", changes);
    S.fx = res.fx;
    applyFx();
    document.querySelectorAll('[data-act="toggle-sound"]').forEach((b) => (b.outerHTML = soundButton()));
    return res;
  }

  // ---------------------------------------------------------------- safe content
  // Alternatives are shown in the page itself, so only harmless formatting is kept.
  const ALLOWED = new Set(["B", "I", "U", "EM", "STRONG", "SUB", "SUP", "BR", "SPAN", "SMALL", "MARK", "IMG"]);
  function safeHTML(html) {
    const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
    const out = document.createElement("div");
    const copy = (from, to) => {
      for (const node of from.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) to.appendChild(document.createTextNode(node.nodeValue));
        else if (node.nodeType === Node.ELEMENT_NODE) {
          if (ALLOWED.has(node.tagName)) {
            const el = document.createElement(node.tagName);
            if (node.tagName === "IMG") {
              const src = (node.getAttribute("src") || "").trim();
              if (!src || /^(javascript|data):/i.test(src)) continue;
              el.setAttribute("src", src);
              el.setAttribute("alt", node.getAttribute("alt") || "");
            }
            copy(node, el);
            to.appendChild(el);
          } else if (!["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "TEMPLATE"].includes(node.tagName)) {
            copy(node, to);
          }
        }
      }
    };
    copy(doc.body, out);
    return out.innerHTML;
  }

  // Card content goes in a sandboxed frame: its styles stay apart from the page and its scripts don't run.
  function mountFrame(container, html, css, extraClass = "") {
    const night = document.documentElement.classList.contains("night-mode");
    const scheme = night ? "dark" : "light"; // must match the page, or Chromium paints the frame opaque
    const frame = document.createElement("iframe");
    frame.className = "cardframe";
    frame.setAttribute("sandbox", "allow-same-origin");
    frame.setAttribute("title", "Conteúdo do cartão");
    frame.srcdoc =
      `<!doctype html><html class="${night ? "night-mode" : ""}"><head><meta charset="utf-8">` +
      `<meta name="color-scheme" content="${scheme}"><base href="${esc(S.base)}">${css || ""}<style>` +
      `:root{color-scheme:${scheme}}html,body{margin:0;padding:0;background:transparent!important;overflow:hidden}` +
      `.card{background:transparent!important}img{max-width:100%;height:auto}` +
      `.pe-left{text-align:left!important}` +
      (night ? `body.card{color:#e6e8ee!important}a{color:#7fa6e8}` : "") +
      `</style></head><body class="card ${night ? "nightMode night_mode" : ""} ${extraClass}">${html}</body></html>`;
    // Sized to its content when it loads, when its images and fonts arrive, and when the window
    // changes width. A ResizeObserver across documents loops in Chromium.
    frame._fit = () => fitFrame(frame);
    frame.addEventListener("load", () => {
      frame._loaded = true;
      frame._fit();
      const doc = frame.contentDocument;
      if (!doc || !doc.body) return;
      doc.querySelectorAll("img").forEach((img) => img.addEventListener("load", frame._fit));
      if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(frame._fit);
    });
    container.appendChild(frame);
    return frame;
  }

  function fitFrame(frame, tries = 0) {
    const doc = frame.contentDocument;
    if (!doc || !doc.body) return;
    // offsetHeight of <html> keeps the margins of the first and last paragraphs, which collapse through <body>
    const height = Math.ceil(Math.max(doc.body.scrollHeight, doc.documentElement.offsetHeight));
    if (Math.abs(height - frame.offsetHeight) <= 1) return;
    frame.style.height = height + "px";
    if (tries < 3) requestAnimationFrame(() => fitFrame(frame, tries + 1));
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      document.querySelectorAll("iframe.cardframe").forEach((f) => f._fit && f._fit());
      if (S.view === "roleta") sizeWheel();
    }, 120);
  });

  // ---------------------------------------------------------------- dialogs
  const overlays = [];

  function overlay(html) {
    const el = document.createElement("div");
    el.className = "overlay";
    el.innerHTML = html;
    el.addEventListener("mousedown", (ev) => {
      if (ev.target === el) closeOverlay(el);
    });
    document.body.appendChild(el);
    overlays.push({ el, focus: document.activeElement });
    animate(el.firstElementChild, "dialog-in");
    const first = el.querySelector("textarea, input, select, .btn.primary, button");
    setTimeout(() => first && first.focus(), 40);
    return el;
  }

  function topOverlay(from) {
    if (from) return from.closest(".overlay");
    return overlays.length ? overlays[overlays.length - 1].el : null;
  }

  function closeOverlay(el = topOverlay()) {
    const i = overlays.findIndex((o) => o.el === el);
    if (i < 0) return;
    const { focus } = overlays.splice(i, 1)[0];
    el.remove();
    if (el._resolve) el._resolve(false);
    if (el._onClose) el._onClose();
    if (focus && focus.isConnected) focus.focus();
  }

  function closeAllOverlays() {
    while (overlays.length) closeOverlay(overlays[overlays.length - 1].el);
  }

  function ask({ title, msg, ok = "Confirmar", danger = false }) {
    return new Promise((resolve) => {
      const el = overlay(`<div class="dialog small-dialog" role="alertdialog" aria-modal="true" aria-labelledby="ask-title">
        <h3 id="ask-title">${esc(title)}</h3><p class="muted">${esc(msg)}</p>
        <div class="actions end"><button class="btn" data-act="dlg-close">Cancelar</button>
        <button class="btn ${danger ? "danger-solid" : "primary"}" data-act="ask-ok">${esc(ok)}</button></div></div>`);
      el._resolve = resolve;
    });
  }

  // A dialog with one name to type. submit(value) runs on Enter or the button; if it fails, the
  // dialog stays open with the message shown, so the name can be fixed.
  function askName({ title, value = "", ok = "Salvar", submit }) {
    const el = overlay(`<div class="dialog small-dialog" role="dialog" aria-modal="true" aria-labelledby="ask-title">
      <h3 id="ask-title">${esc(title)}</h3>
      <label class="field"><span>Nome</span><input class="input" id="ask-name" value="${esc(value)}" autocomplete="off" spellcheck="false"></label>
      <div class="actions end top-gap"><button class="btn" data-act="dlg-close">Cancelar</button>
      <button class="btn primary" data-act="ask-name-ok">${esc(ok)}</button></div></div>`);
    el._submit = async () => {
      const input = el.querySelector("#ask-name");
      if (el._busy || !input) return;
      el._busy = true;
      try {
        await submit(input.value);
        closeOverlay(el);
      } catch (err) {
        input.focus();
      } finally {
        el._busy = false;
      }
    };
    setTimeout(() => {
      const input = el.querySelector("#ask-name");
      if (input) input.select();
    }, 60);
    return el;
  }

  // ---------------------------------------------------------------- frame and navigation
  const NAV = [
    ["home", "Hoje"],
    ["materias", "Matérias"],
    ["roleta", "Roleta"],
    ["erros", "Caderno de erros"],
    ["ajustes", "Ajustes"],
  ];
  const ANKI = [
    ["add", "Adicionar cartões"],
    ["browse", "Procurar"],
    ["stats", "Estatísticas"],
    ["import", "Importar arquivo"],
    ["sync", "Sincronizar"],
  ];

  function rail() {
    const current = S.view === "materia" ? "materias" : S.view;
    return `<nav class="rail" aria-label="Seções">
      <div class="brand"><span class="bubble full" aria-hidden="true"></span>Painel de Estudos</div>
      ${NAV.map(([v, label]) => `<button class="nav-item" data-go="${v}" ${current === v ? 'aria-current="page"' : ""}>${label}</button>`).join("")}
      <div class="rail-sep"></div>
      <div class="rail-group">Janelas do Anki</div>
      ${ANKI.map(([w, label]) => `<button class="nav-item" data-open="${w}">${w === "sync" && S.syncing ? "Sincronizando…" : label}</button>`).join("")}
      <div class="rail-bottom">
        <button class="nav-item" data-open="anki">Usar a interface do Anki<span class="hint">Volte por Ferramentas, Abrir o Painel</span></button>
      </div>
    </nav>`;
  }

  function page(content) {
    const app = appEl();
    app.className = "app";
    app.innerHTML = `${rail()}<main class="main" id="main" tabindex="-1">${content}</main>`;
  }

  const VIEWS = {
    home: viewHome,
    materias: viewMaterias,
    materia: (a) => viewMateria(a.did),
    roleta: viewRoleta,
    erros: viewErros,
    ajustes: viewAjustes,
  };

  async function go(view, args = {}) {
    if (!VIEWS[view]) view = "home";
    stopSpin();
    closeAllOverlays();
    S.view = view;
    S.args = args;
    S.card = null;
    try {
      await VIEWS[view](args);
    } catch (err) {
      /* shown already */
    }
    const main = document.getElementById("main");
    if (main) main.focus({ preventScroll: true });
  }

  function rerender() {
    if (S.view === "study") return api("current").then(showStudy).catch(() => {});
    if (S.view === "done") return;
    if (S.view === "roleta") {
      if (WHEEL.spin || overlays.length) return;
      return api("roleta")
        .then((res) => {
          S.ro = res;
          renderRoleta();
        })
        .catch(() => {});
    }
    const main = document.getElementById("main");
    const top = main ? main.scrollTop : 0;
    return go(S.view, S.args).then(() => {
      const again = document.getElementById("main");
      if (again) again.scrollTop = top;
    });
  }

  function openAnki(what, did) {
    return api("open", did ? { what, did } : { what }).catch(() => {});
  }

  // ---------------------------------------------------------------- shared pieces
  const count = (n, kind) => `<span class="${n ? "n-" + kind : "zero"}">${n}</span>`;

  function accCell(acc, answers) {
    if (acc == null) return `<span class="muted">sem respostas</span>`;
    const level = acc < 0.6 ? "low" : acc < 0.8 ? "mid" : "high";
    return `<span class="acc lvl-${level}" title="${plural(answers, "resposta", "respostas")}"><span class="acc-bar"><i style="--w:${Math.round(acc * 100)}%"></i></span><span class="pct num">${pct(acc)}</span></span>`;
  }

  function goalBubbles(g) {
    let per = g.unit === "cards" ? 10 : 5;
    let total = Math.max(1, Math.ceil(g.value / per));
    if (total > 30) {
      per = Math.ceil(g.value / 30);
      total = Math.ceil(g.value / per);
    }
    let out = "";
    for (let i = 0; i < total; i++) {
      const fill = Math.max(0, Math.min(1, (g.done - i * per) / per));
      out += `<span class="bubble ${fill >= 1 ? "full" : fill > 0 ? "part" : ""}" style="--p:${fill.toFixed(3)};--i:${i}"></span>`;
    }
    return out;
  }

  function unitWord(unit, n) {
    return unit === "cards" ? (n === 1 ? "cartão" : "cartões") : n === 1 ? "minuto" : "minutos";
  }

  const aboutMinutes = (n) => (n <= 1 ? "cerca de 1 minuto" : `uns ${n} minutos`);

  function maturityBar(m, wide = false) {
    const total = Math.max(1, m.total);
    const seg = (n, cls) => (n ? `<i class="${cls}" style="width:${((n / total) * 100).toFixed(2)}%"></i>` : "");
    const title = `${m.new} novos, ${m.learning} aprendendo, ${m.young} jovens, ${m.mature} maduros, ${m.suspended} suspensos`;
    return `<span class="matbar" style="${wide ? "width:100%;height:12px;margin:0" : ""}" title="${title}">${seg(m.new, "seg-new")}${seg(m.learning, "seg-learn")}${seg(m.young, "seg-young")}${seg(m.mature, "seg-mature")}${seg(m.suspended, "seg-susp")}</span>`;
  }

  const LEGEND = `<div class="legend"><span style="--c:var(--new)">Novos</span><span style="--c:var(--learn)">Aprendendo</span><span style="--c:var(--young)">Jovens</span><span style="--c:var(--review)">Maduros, com intervalo de 21 dias ou mais</span><span style="--c:var(--form)">Suspensos</span></div>`;

  const NO_DECKS = `<div class="empty"><p>Nenhum baralho encontrado.</p><p class="muted">Importe seus cartões com Importar arquivo, no menu ao lado.</p></div>`;

  const roletaLine = (r) => (r ? `<div class="muted sub-line">Roleta: ${r.seen} de ${r.total} tópicos vistos neste ciclo</div>` : "");

  // ---------------------------------------------------------------- Hoje
  async function viewHome() {
    const d = await api("home");
    const g = d.goal;
    const left = Math.max(0, g.value - g.done);
    const notes = [];
    if (g.done >= g.value) notes.push("Meta de hoje cumprida.");
    else if (g.unit === "cards")
      notes.push(`Faltam ${plural(round(left), "cartão", "cartões")}, ${aboutMinutes(Math.max(1, round((left * g.avg_secs) / 60)))} no seu ritmo.`);
    else notes.push(`Faltam ${plural(Math.ceil(left), "minuto", "minutos")}.`);
    if (g.streak > 0) notes.push(`${plural(g.streak, "dia seguido", "dias seguidos")} batendo a meta.`);

    const plan = d.plan;
    const planHtml = plan.length
      ? `<table class="grid"><thead><tr><th>Matéria</th><th>Novos</th><th>Aprender</th><th>Revisar</th><th>Acerto em 30 dias</th><th><span class="sr-only">Estudar</span></th></tr></thead><tbody>
        ${plan
          .map(
            (r) => `<tr class="clickable" data-go="materia" data-did="${r.did}">
            <td><span class="cell-name">${esc(r.name)}</span>${roletaLine(r.roleta)}</td>
            <td>${count(r.new, "new")}</td><td>${count(r.learn, "learn")}</td><td>${count(r.review, "review")}</td>
            <td>${accCell(r.acc, r.answers)}</td>
            <td>${r.due ? `<button class="btn" data-act="study" data-did="${r.did}">Estudar</button>` : `<span class="muted">em dia</span>`}</td>
          </tr>`
          )
          .join("")}</tbody></table>`
      : NO_DECKS;

    page(`<div class="page">
      <p class="date">${esc(cap(d.date))}</p>
      <h1>Hoje</h1>
      <div class="goal">
        <p class="goal-line"><strong class="num">${round(g.done)}</strong> de <span class="num">${round(g.value)}</span> ${unitWord(g.unit, g.value)}</p>
        <div class="bubbles goal-bubbles" role="img" aria-label="${round(g.done)} de ${round(g.value)} ${unitWord(g.unit, g.value)}">${goalBubbles(g)}</div>
        ${notes.map((n) => `<p class="goal-note">${esc(n)}</p>`).join("")}
      </div>
      <div class="start">${
        d.due
          ? `<button class="btn primary" data-act="study">Estudar tudo</button><span class="muted">${plural(d.due, "cartão", "cartões")} para hoje, ${aboutMinutes(Math.max(1, d.eta_min))}. A matéria mais fraca vem primeiro.</span>`
          : `<span class="muted">Nada para revisar agora.</span>`
      }</div>
      ${d.erros7 ? `<p class="start-note muted">Caderno de erros: ${plural(d.erros7, "cartão errado", "cartões errados")} nos últimos 7 dias. <button class="link" data-go="erros">Abrir o caderno</button></p>` : ""}
      <section class="section">
        <div class="section-head"><h2>Matérias de hoje</h2><span class="muted">da mais fraca para a mais forte</span></div>
        ${planHtml}
      </section>
      <section class="section">
        <div class="section-head"><h2>Roleta</h2>${d.roleta.has ? `<span class="muted">${esc(d.roleta.scope)}: ${d.roleta.counts.seen} de ${d.roleta.counts.total} vistos neste ciclo</span>` : ""}</div>
        ${roletaToday(d.roleta)}
      </section>
    </div>`);
    animate(document.querySelector(".goal-bubbles"), "fill");
  }

  function roletaToday(r) {
    if (!r.has) {
      return `<div class="empty"><p>A roleta está vazia.</p>
        <p class="muted">Na página Roleta, cole o bloco JSON da skill exportar-roleta ou um backup da sua Roleta de Estudos.</p>
        <button class="btn" data-go="roleta">Abrir a Roleta</button></div>`;
    }
    const last = r.last;
    const when = last ? fmtWhen(last.seen) : "";
    return `<div class="draw">
      ${
        last
          ? `<p class="draw-where">Último sorteado${when ? ", " + esc(when) : ""}: ${esc(last.path)}</p><p class="draw-topic">${esc(last.t)}</p>${last.note ? `<p class="note-preview">${esc(last.note)}</p>` : ""}`
          : `<p class="draw-empty muted">Nenhum tópico sorteado ainda em ${esc(r.scope)}.</p>`
      }
      <div class="actions"><button class="btn primary" data-go="roleta" data-spin="1">Girar a roleta</button>
      ${topicStudyButton(last && last.cards, last && last.deck, last && last.id)}</div>
    </div>`;
  }

  const topicStudyLabel = (n) => (n === 1 ? "Estudar o cartão deste tópico" : `Estudar os ${n} cartões deste tópico`);

  function topicStudyButton(info, deck, tid) {
    if (info && info.count && !info.ambiguous) return `<button class="btn" data-act="ro-study-topic" data-tid="${esc(tid)}">${topicStudyLabel(info.count)}</button>`;
    return deck ? `<button class="btn" data-act="study" data-did="${deck}">Estudar os cartões dessa matéria</button>` : "";
  }

  // ---------------------------------------------------------------- estudo
  function showStudy(res) {
    if (!res) return;
    if (res.view === "card") {
      if (!S.card || S.card.id !== res.id) S.reason = null;
      S.card = res;
      S.phase = "question";
      S.answer = null;
      S.result = null;
      if (res.answer) {
        S.phase = "answer";
        S.answer = res.answer;
      }
      if (res.result) {
        S.phase = "result";
        S.result = res.result;
      }
      renderCard();
      if (res.session.goal_reached) stampOverlay("Meta cumprida");
    } else if (res.view === "done") renderDone(res);
    else go("home");
  }

  function tools(c) {
    return `<div class="tools">
      <button class="btn quiet" data-act="edit" title="Abre o cartão no Procurar do Anki">Editar</button>
      <button class="btn quiet" data-act="bury" title="Esconde o cartão até amanhã">Enterrar</button>
      <button class="btn quiet" data-act="suspend" title="Tira o cartão das revisões até você reativá-lo">Suspender</button>
      <button class="btn quiet" data-act="undo" ${c.can_undo ? "" : "disabled"} title="Ctrl+Z">Desfazer</button>
      ${c.audio ? `<button class="btn quiet" data-act="replay" title="Tecla R">Ouvir</button>` : ""}
    </div>`;
  }

  function gradeButtons(labels, ratings) {
    const names = { 1: "De novo", 2: "Difícil", 3: "Bom", 4: "Fácil" };
    return ratings
      .map(
        (r) =>
          `<button class="btn grade ${r === 3 ? "primary" : ""} ${r === 1 ? "again" : ""}" data-act="rate" data-r="${r}" title="Tecla ${r}"><span>${names[r]}</span><small>${esc(labels[r - 1])}</small></button>`
      )
      .join("");
  }

  function choicesHtml() {
    const c = S.card;
    const r = S.result;
    const cls = (v) =>
      r ? [r.choice === v ? "chosen" : "", r.correct === v ? "is-correct" : "", r.choice === v && !r.right ? "is-wrong" : ""].join(" ") : "";
    if (c.mode === "ce") {
      return `<div class="ce" role="group" aria-label="Julgue o item">${["CERTO", "ERRADO"]
        .map(
          (v) =>
            `<button class="ce-opt ${cls(v)}" data-act="choose" data-choice="${v}" ${r ? "disabled" : ""}><span class="mark" aria-hidden="true">${v[0]}</span>${v === "CERTO" ? "Certo" : "Errado"}</button>`
        )
        .join("")}</div>`;
    }
    if (c.mode === "mc") {
      return `<ol class="mc" aria-label="Alternativas">${c.options
        .map(
          (o) =>
            `<li><button class="mc-opt ${cls(o.letter)}" data-act="choose" data-choice="${o.letter}" ${r ? "disabled" : ""}><span class="mark" aria-hidden="true">${o.letter}</span><span><span class="sr-only">Alternativa ${o.letter}: </span>${safeHTML(o.html)}</span></button></li>`
        )
        .join("")}</ol>`;
    }
    return "";
  }

  function renderCard() {
    const c = S.card;
    S.view = "study";
    const app = appEl();
    app.className = "app focus";
    const s = c.session;
    app.innerHTML = `<div class="study">
      <header class="study-top">
        <button class="btn quiet" data-act="end" title="Esc">Encerrar</button>
        <div class="study-deck">${esc(c.deck)}</div>
        <div class="study-counts num" title="Novos, aprendendo e revisões que faltam">${count(c.counts.new, "new")}${count(c.counts.learn, "learn")}${count(c.counts.review, "review")}</div>
        <div class="study-goal num">${round(s.goal_done)} de ${round(s.goal_value)} ${s.goal_unit === "cards" ? "hoje" : "min hoje"}</div>
        ${soundButton()}
      </header>
      <div class="study-body" id="study-body"><div class="study-col" id="study-col">
        <div class="sheet" id="q"></div>
        <div id="choices">${choicesHtml()}</div>
        <div id="after"></div>
      </div></div>
      <footer class="study-bar" id="bar"></footer>
    </div>`;
    const q = document.getElementById("q");
    if (S.phase === "answer") mountFrame(q, S.answer.html, c.css);
    else mountFrame(q, c.front, c.css, c.mode === "mc" ? "pe-left" : "");
    if (S.phase === "result") renderAfter(false, false);
    renderBar();
    if (S.enter) {
      S.enter = false;
      animate(document.getElementById("study-col"), "enter");
    }
  }

  function renderAfter(scroll = true, fresh = true) {
    const r = S.result;
    const after = document.getElementById("after");
    const gabarito = S.card.mode === "ce" ? (r.correct === "CERTO" ? "Certo" : "Errado") : r.correct;
    after.innerHTML = `<p class="verdict ${r.right ? "right" : "wrong"}" role="status"><span class="verdict-word">${r.right ? "Você acertou." : "Você errou."}</span><span class="muted">Gabarito: ${esc(gabarito)}</span></p>${r.right ? "" : reasonsHtml()}<div class="sheet" id="back"></div>`;
    mountFrame(document.getElementById("back"), r.back, S.card.css);
    if (r.trap) markTrap(document.querySelector("#q iframe"), r.trap, fresh);
    if (fresh) {
      animate(after.querySelector(".verdict-word"), "stamp");
      animate(after.querySelector(".reasons"), "rise");
      animate(document.getElementById("back"), "enter");
    }
    if (scroll) after.scrollIntoView({ block: "start", behavior: motionOK() ? "smooth" : "auto" });
  }

  // Why a card was missed: optional, one tap or one key after a wrong answer.
  const REASONS = [
    ["nao_sabia", "Não sabia", "n"],
    ["confundi", "Confundi", "c"],
    ["atencao", "Falta de atenção", "a"],
    ["pegadinha", "Pegadinha", "p"],
  ];

  function reasonsHtml() {
    return `<div class="reasons" role="group" aria-label="Por que você errou? Opcional"><span class="reasons-q">Por quê?</span>${REASONS.map(
      ([code, label, key]) =>
        `<button class="reason ${S.reason === code ? "on" : ""}" data-act="reason" data-code="${code}" aria-pressed="${S.reason === code}" title="Tecla ${key.toUpperCase()}"><kbd>${key.toUpperCase()}</kbd>${label}</button>`
    ).join("")}</div>`;
  }

  function setReason(code) {
    S.reason = S.reason === code ? null : code;
    document.querySelectorAll('[data-act="reason"]').forEach((b) => {
      const on = b.dataset.code === S.reason;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    if (S.reason) {
      play("mark");
      animate(document.querySelector(`[data-act="reason"][data-code="${S.reason}"] kbd`), "pop");
    }
  }

  // The words an ERRADO item changed, marked inside the statement with the law's version beside
  // them. The match ignores accents, case and spacing; when the words aren't there as written,
  // the statement stays as it was (the back still shows the 🔁 line).
  function foldMap(s) {
    let out = "";
    const map = [];
    let space = false;
    for (let i = 0; i < s.length; i++) {
      let ch = s[i];
      if (/\s/.test(ch)) {
        if (space) continue;
        space = true;
        ch = " ";
      } else space = false;
      const f = ch.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      for (let j = 0; j < f.length; j++) {
        out += f[j];
        map.push(i);
      }
    }
    return { out, map };
  }

  const TRAP_CSS =
    ".pe-trap{text-decoration:line-through;text-decoration-thickness:2px;text-decoration-color:#c23b32;background:rgba(194,59,50,.1);border-radius:3px;-webkit-box-decoration-break:clone;box-decoration-break:clone}" +
    ".pe-fix{display:inline;margin-left:.3em;padding:0 .3em;border-radius:4px;background:rgba(35,122,87,.14);color:#1d6b4b;font-weight:600;-webkit-box-decoration-break:clone;box-decoration-break:clone}" +
    "html.night-mode .pe-trap{text-decoration-color:#f08a80;background:rgba(240,138,128,.16)}" +
    "html.night-mode .pe-fix{background:rgba(110,200,155,.18);color:#86dab0}" +
    ".pe-anim .pe-trap{animation:pe-trap .45s ease-out both}.pe-anim .pe-fix{animation:pe-fix .4s ease-out .2s both}" +
    "@keyframes pe-trap{from{text-decoration-color:transparent;background-color:transparent}}" +
    "@keyframes pe-fix{from{opacity:0}}";

  function markTrap(frame, trap, animateIt) {
    if (!frame || !trap || !trap.from) return;
    const run = () => {
      const doc = frame.contentDocument;
      if (!doc || !doc.body || doc.querySelector(".pe-trap")) return;
      const nodes = [];
      let text = "";
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        nodes.push({ node: walker.currentNode, start: text.length });
        text += walker.currentNode.nodeValue;
      }
      const hay = foldMap(text);
      const needle = foldMap(String(trap.from).trim()).out;
      const at = needle ? hay.out.indexOf(needle) : -1;
      if (at < 0) return;
      const start = hay.map[at];
      const end = hay.map[at + needle.length - 1] + 1;
      const point = (idx, isEnd) => {
        for (const n of nodes) {
          const len = n.node.nodeValue.length;
          if (isEnd ? idx <= n.start + len : idx < n.start + len) return [n.node, idx - n.start];
        }
        const last = nodes[nodes.length - 1];
        return [last.node, last.node.nodeValue.length];
      };
      const range = doc.createRange();
      range.setStart(...point(start, false));
      range.setEnd(...point(end, true));
      const mark = doc.createElement("span");
      mark.className = "pe-trap";
      try {
        range.surroundContents(mark);
      } catch (err) {
        mark.appendChild(range.extractContents());
        range.insertNode(mark);
      }
      const fix = doc.createElement("span");
      fix.className = "pe-fix";
      fix.textContent = trap.to;
      fix.setAttribute("aria-label", "Na lei: " + trap.to);
      mark.after(fix);
      if (!doc.getElementById("pe-trap-css")) {
        const style = doc.createElement("style");
        style.id = "pe-trap-css";
        style.textContent = TRAP_CSS;
        doc.head.appendChild(style);
      }
      if (animateIt && motionOK()) doc.body.classList.add("pe-anim");
      if (frame._fit) frame._fit();
    };
    if (frame._loaded) run();
    else frame.addEventListener("load", run, { once: true });
  }

  function renderBar() {
    const c = S.card;
    let main = "";
    let hint = "";
    if (c.mode === "basic") {
      if (S.phase === "question") main = `<button class="btn primary grade" data-act="reveal"><span>Mostrar resposta</span><small>Espaço</small></button>`;
      else {
        main = gradeButtons(S.answer.labels, [1, 2, 3, 4]);
        hint = "Teclas 1 a 4, Espaço para Bom.";
      }
    } else if (S.phase === "question") {
      hint =
        c.mode === "ce"
          ? "Tecle C para Certo ou E para Errado."
          : `Tecle a letra da alternativa, de A a ${c.options[c.options.length - 1].letter}.`;
    } else if (S.result.right) {
      main = gradeButtons(S.result.labels, [2, 3, 4]);
      hint = "Acertou com dúvida? Escolha Difícil.";
    } else {
      main = `<button class="btn primary grade" data-act="rate" data-r="1"><span>Continuar</span><small>De novo, ${esc(S.result.labels[0])}</small></button>`;
      hint = "Espaço para continuar.";
    }
    const bar = document.getElementById("bar");
    bar.innerHTML = `${tools(c)}<div class="main-actions">${hint ? `<span class="hint">${esc(hint)}</span>` : ""}${main}</div>`;
    if (S.phase !== "question") animate(bar.querySelector(".main-actions"), "rise");
  }

  function markChoices(r) {
    document.querySelectorAll("[data-choice]").forEach((btn) => {
      const v = btn.dataset.choice;
      btn.disabled = true;
      btn.classList.toggle("is-correct", v === r.correct);
      btn.classList.toggle("is-wrong", v === r.choice && !r.right);
      if (v === r.choice) btn.classList.add("chosen");
    });
  }

  function stampOverlay(text) {
    const el = document.createElement("div");
    el.className = "stamp-overlay";
    el.setAttribute("role", "status");
    el.innerHTML = `<div class="stamp-mark">${esc(text)}</div>`;
    document.body.appendChild(el);
    play("goal");
    const stay = motionOK() ? 1700 : 1300;
    setTimeout(() => el.classList.add("out"), stay);
    setTimeout(() => el.remove(), stay + 400);
  }

  const startStudy = (did) =>
    guarded(async () => {
      closeAllOverlays();
      stopSpin();
      S.enter = true;
      S.returnTo = null;
      showStudy(await api("start", did ? { did } : {}));
    });

  // The cards of a Roleta topic, in a session of their own.
  const studyTopic = (tid) =>
    guarded(async () => {
      const from = S.view === "roleta" ? "roleta" : "home";
      const res = await api("study_topic", { tid });
      closeAllOverlays();
      stopSpin();
      S.enter = true;
      S.returnTo = from;
      showStudy(res);
    });

  // The cards missed in a period (one matéria or all), again.
  const studyErrors = (days, did) =>
    guarded(async () => {
      const res = await api("study_errors", did ? { days, did } : { days });
      S.enter = true;
      S.returnTo = "erros";
      showStudy(res);
    });

  const choose = (choice) =>
    guarded(async () => {
      if (S.view !== "study" || S.phase !== "question") return;
      play("mark");
      const res = await api("choose", { choice });
      S.phase = "result";
      S.result = res;
      markChoices(res);
      play(res.right ? "right" : "wrong");
      if (!res.right) animate(document.querySelector(`[data-choice="${res.choice}"]`), "shake");
      animate(document.querySelector(`[data-choice="${res.correct}"] .mark`), "pop");
      renderAfter();
      renderBar();
    });

  const reveal = () =>
    guarded(async () => {
      if (S.view !== "study" || S.phase !== "question" || S.card.mode !== "basic") return;
      S.answer = await api("reveal");
      S.phase = "answer";
      play("flip");
      const q = document.getElementById("q");
      q.innerHTML = "";
      mountFrame(q, S.answer.html, S.card.css);
      animate(q, "flip-in");
      renderBar();
    });

  const rate = (rating) =>
    guarded(async () => {
      if (S.view !== "study") return;
      const c = S.card;
      if (c.mode === "basic" ? S.phase !== "answer" : S.phase !== "result") return;
      if (c.mode !== "basic") {
        if (!S.result.right) rating = 1;
        else if (rating < 2) return;
      }
      const args = { rating };
      if (c.mode !== "basic" && !S.result.right && S.reason) args.reason = S.reason;
      const res = await api("answer", args);
      play("next");
      S.enter = true;
      showStudy(res);
    });

  const cardAction = (method) =>
    guarded(async () => {
      const res = await api(method);
      play(method === "undo" ? "undo" : "next");
      S.enter = true;
      showStudy(res);
    });

  const endStudy = () =>
    guarded(async () => {
      await api("stop");
      const back = S.returnTo || "home";
      S.returnTo = null;
      await go(back);
    });

  function renderDone(d) {
    S.view = "done";
    S.card = null;
    const headline =
      d.kind === "topic" ? "Cartões do tópico estudados." : d.kind === "errors" ? "Erros refeitos." : d.deck ? `Tudo em dia em ${d.deck}.` : "Tudo em dia por hoje.";
    const buttons =
      d.kind === "topic"
        ? `<button class="btn primary" data-go="roleta">Voltar para a Roleta</button><button class="btn" data-go="home">Voltar para Hoje</button>`
        : d.kind === "errors"
          ? `<button class="btn primary" data-go="erros">Voltar ao caderno</button><button class="btn" data-go="home">Voltar para Hoje</button>`
          : `<button class="btn primary" data-go="home">Voltar para Hoje</button><button class="btn" data-go="roleta">Girar a roleta</button>`;
    const s = d.session;
    const goalText =
      s.goal_done >= s.goal_value
        ? `Meta de hoje cumprida: ${round(s.goal_done)} de ${round(s.goal_value)} ${unitWord(s.goal_unit, s.goal_value)}.`
        : `Meta de hoje: ${round(s.goal_done)} de ${round(s.goal_value)} ${unitWord(s.goal_unit, s.goal_value)}.`;
    const results = d.results || [];
    page(`<div class="page done">
      ${d.kind && d.deck ? `<p class="kicker">${esc(d.deck)}</p>` : ""}
      <h1>${esc(headline)}</h1>
      <p class="lede">${
        d.answered
          ? `${plural(d.answered, "cartão", "cartões")} nesta sessão, ${d.right} certos (${pct(d.right / d.answered)}), em ${plural(Math.max(1, d.minutes), "minuto", "minutos")}.`
          : "Não havia cartões para estudar."
      }</p>
      ${results.length ? `<div class="bubbles session-bubbles" role="img" aria-label="Respostas da sessão, em ordem: preenchida é certa, vermelha é errada">${results.map((ok, i) => `<span class="bubble ${ok ? "right" : "wrong"}" style="--i:${i}"></span>`).join("")}</div>` : ""}
      <p class="goal-note">${esc(goalText)}</p>
      <div class="actions" style="margin-top:28px">${buttons}</div>
    </div>`);
    const strip = document.querySelector(".session-bubbles");
    if (strip && motionOK()) {
      animate(strip, "cascade");
      const ticks = Math.min(results.length, 24);
      for (let i = 0; i < ticks; i++) setTimeout(() => play("tick", i), i * 60);
      setTimeout(() => play("done"), ticks * 60 + 120);
    } else if (results.length) play("done");
    if (s.goal_reached) setTimeout(() => stampOverlay("Meta cumprida"), motionOK() ? 900 : 0);
  }

  // ---------------------------------------------------------------- matérias
  async function viewMaterias() {
    const d = await api("materias");
    const table = d.rows.length
      ? `<table class="grid"><thead><tr><th>Matéria</th><th>Hoje</th><th>Cartões</th><th>Estágio dos cartões</th><th>Acerto em 30 dias</th></tr></thead><tbody>
        ${d.rows
          .map(
            (r) => `<tr class="clickable" data-go="materia" data-did="${r.did}">
            <td><span class="cell-name">${esc(r.name)}</span>${roletaLine(r.roleta)}</td>
            <td>${r.due ? `<strong>${r.due}</strong>` : `<span class="zero">0</span>`}</td>
            <td>${r.maturity.total}</td>
            <td>${maturityBar(r.maturity)}</td>
            <td>${accCell(r.acc, r.answers)}</td></tr>`
          )
          .join("")}</tbody></table>${LEGEND}`
      : NO_DECKS;
    page(`<div class="page"><h1>Matérias</h1>
      <p class="lede">Cada baralho é uma matéria. O acerto conta as respostas dos últimos 30 dias que não foram De novo.</p>
      ${table}</div>`);
  }

  function roletaTopics(cat) {
    const named = cat.subs.some((s) => s.name);
    return cat.subs
      .map(
        (sub) => `${named ? `<div class="group-name">${esc(sub.name || "Geral")}</div>` : ""}<ul class="topics">${sub.topics
          .map(
            (t) => `<li class="topic">
              <button class="topic-toggle" data-act="ro-toggle" data-tid="${esc(t.id)}" aria-pressed="${!!t.seen}" title="${t.seen ? "Voltar ao sorteio" : "Marcar como visto"}"><span class="bubble ${t.seen ? "full" : ""}"></span></button>
              <span class="topic-name">${esc(t.t)}</span>
              <span class="times">${t.seen ? esc(fmtWhen(t.seen) || "visto") : ""}</span>
            </li>`
          )
          .join("")}</ul>`
      )
      .join("");
  }

  async function viewMateria(did) {
    const d = await api("materia", { did });
    const due = d.counts.new + d.counts.learn + d.counts.review;
    const accText =
      d.acc30 == null
        ? "Ainda não há respostas nesta matéria nos últimos 30 dias."
        : `Acertou ${pct(d.acc30)} nos últimos 30 dias (${plural(d.n30, "resposta", "respostas")})` +
          (d.acc7 == null ? "." : ` e ${pct(d.acc7)} nos últimos 7 (${plural(d.n7, "resposta", "respostas")}).`);
    const weak = d.weak.length
      ? `<ul class="weak">${d.weak.map((w) => `<li><span title="${esc(w.path)}">${esc(w.label)}</span>${accCell(w.acc, w.n)}</li>`).join("")}</ul>`
      : `<p class="muted">Aparece aqui quando uma etiqueta tiver 5 respostas ou mais nos últimos 90 dias.</p>`;
    const r = d.roleta;
    page(`<div class="page">
      <button class="crumb" data-go="materias">Matérias</button>
      <h1>${esc(d.name)}</h1>
      <p class="lede">${due ? `Para hoje: ${count(d.counts.new, "new")} novos, ${count(d.counts.learn, "learn")} aprendendo e ${count(d.counts.review, "review")} revisões.` : "Em dia por hoje."}</p>
      <div class="actions">
        ${due ? `<button class="btn primary" data-act="study" data-did="${d.did}">Estudar ${esc(d.name)}</button>` : ""}
        <button class="btn" data-open="add" data-did="${d.did}">Adicionar cartões</button>
        <button class="btn" data-open="browse" data-did="${d.did}">Procurar</button>
        <button class="btn" data-open="options" data-did="${d.did}">Opções do baralho</button>
        <button class="btn" data-open="stats" data-did="${d.did}">Estatísticas</button>
        <button class="btn" data-act="deck-rename" data-did="${d.did}" data-name="${esc(d.name)}">Renomear</button>
      </div>
      <section class="section"><div class="section-head"><h2>Acerto</h2></div><p style="margin:12px 0 0">${esc(accText)}</p></section>
      <section class="section"><div class="section-head"><h2>Cartões</h2><span class="muted">${plural(d.maturity.total, "cartão", "cartões")}</span></div>
        <div style="margin-top:14px">${maturityBar(d.maturity, true)}</div>${LEGEND}</section>
      ${subdecksSection(d)}
      <section class="section"><div class="section-head"><h2>Temas</h2><span class="muted">do mais fraco para o mais forte, pelas etiquetas, nos últimos 90 dias</span></div>${weak}</section>
      ${
        r
          ? `<section class="section"><div class="section-head"><h2>Roleta</h2><span class="muted">${r.counts.seen} de ${r.counts.total} tópicos vistos neste ciclo</span></div>
          ${roletaTopics(r.cat)}
          <div class="actions" style="margin-top:16px"><button class="btn" data-act="ro-open" data-cat="${esc(r.cat.id)}">Abrir na Roleta</button></div></section>`
          : ""
      }
      ${
        d.can_delete
          ? `<div class="page-foot"><button class="link danger" data-act="deck-delete" data-matter="1" data-did="${d.did}" data-name="${esc(d.name)}" data-cards="${d.maturity.total}" data-kids="${d.decks.length}">Excluir o baralho ${esc(d.name)}</button></div>`
          : ""
      }
    </div>`);
  }

  // The decks inside a matéria (the Roleta makes one per topic studied), each with its own actions.
  function subdecksSection(d) {
    if (!d.decks.length) return "";
    const rows = d.decks
      .map(
        (k) => `<tr>
        <td><span class="deck-name" style="--depth:${k.depth - 1}">${esc(k.name)}</span></td>
        <td>${k.due ? `<strong>${k.due}</strong>` : `<span class="zero">0</span>`}</td>
        <td>${k.cards}</td>
        <td class="row-acts">${k.due ? `<button class="btn" data-act="study" data-did="${k.did}">Estudar</button>` : ""}<button class="btn quiet" data-open="browse" data-did="${k.did}">Procurar</button><button class="icon-btn" data-act="deck-rename" data-did="${k.did}" data-name="${esc(k.name)}" title="Renomear" aria-label="Renomear ${esc(k.name)}">${ICON.edit}</button><button class="icon-btn del" data-act="deck-delete" data-did="${k.did}" data-name="${esc(k.name)}" data-cards="${k.cards}" data-kids="${k.kids}" title="Excluir" aria-label="Excluir ${esc(k.name)}">${ICON.trash}</button></td>
      </tr>`
      )
      .join("");
    return `<section class="section"><div class="section-head"><h2>Baralhos dentro de ${esc(d.name)}</h2><span class="muted">${plural(d.decks.length, "baralho", "baralhos")}</span></div>
      <table class="grid decks-grid"><thead><tr><th>Baralho</th><th>Hoje</th><th>Cartões</th><th><span class="sr-only">Ações</span></th></tr></thead><tbody>${rows}</tbody></table></section>`;
  }

  function renameDeck(did, name) {
    askName({
      title: "Renomear baralho",
      value: name,
      ok: "Renomear",
      submit: async (value) => {
        const res = await api("deck_rename", { did, name: value });
        toast(`Nome salvo: ${res.name}.`);
        rerender();
      },
    });
  }

  async function deleteDeck(t) {
    const did = Number(t.dataset.did);
    const name = t.dataset.name;
    const cards = Number(t.dataset.cards || 0);
    const kids = Number(t.dataset.kids || 0);
    const matter = !!t.dataset.matter;
    const kidsText = kids === 1 ? "o baralho que está dentro dele" : `os ${kids} baralhos que estão dentro dele`;
    const cardsText = cards === 1 ? "o único cartão" : `os ${cards} cartões`;
    let what = `O baralho ${name} está vazio.`;
    if (kids && cards) what = `O baralho ${name} é excluído com ${kidsText} e ${cardsText}, como no Anki.`;
    else if (cards) what = `O baralho ${name} é excluído com ${cardsText}, como no Anki.`;
    else if (kids) what = `O baralho ${name} é excluído com ${kidsText}, que não têm cartões.`;
    const ok = await ask({ title: `Excluir ${name}?`, msg: `${what} Dá para desfazer logo em seguida.`, ok: "Excluir", danger: true });
    if (!ok) return;
    let res;
    try {
      res = await api("deck_delete", { did });
    } catch (err) {
      return;
    }
    await (matter ? go("materias") : rerender());
    const lost = res.cards ? `, com ${plural(res.cards, "cartão", "cartões")}` : "";
    toast(`Baralho excluído: ${res.name}${lost}.`, { action: { label: "Desfazer", fn: undoDeckDelete } });
  }

  async function undoDeckDelete() {
    try {
      await api("deck_undo");
    } catch (err) {
      return;
    }
    toast("Exclusão desfeita.");
    rerender();
  }

  // ---------------------------------------------------------------- caderno de erros
  const PERIODS = [
    [1, "Hoje"],
    [7, "7 dias"],
    [30, "30 dias"],
  ];
  const periodText = (days) => (days === 1 ? "hoje" : `nos últimos ${days} dias`);
  const gabaritoWord = (g) => (g === "CERTO" ? "Certo" : g === "ERRADO" ? "Errado" : g || "");

  async function viewErros(args = {}) {
    const days = args.days || S.errDays || 7;
    S.errDays = days;
    const d = await api("erros", { days });
    const seg = PERIODS.map(([v, label]) => `<button class="${v === d.days ? "on" : ""}" data-act="err-days" data-days="${v}" aria-pressed="${v === d.days}">${label}</button>`).join("");
    const summary = d.cards ? `${plural(d.misses, "erro", "erros")} em ${plural(d.cards, "cartão", "cartões")} ${periodText(d.days)}.` : `Nenhum erro ${periodText(d.days)}.`;
    const redo = d.available
      ? `<button class="btn primary" data-act="err-redo" data-days="${d.days}">${d.available === 1 ? "Refazer o cartão" : `Refazer os ${d.available} cartões`}</button>`
      : "";
    page(`<div class="page">
      <h1>Caderno de erros</h1>
      <p class="lede">Os cartões que você errou, por matéria e por lei, com a correção. Refazer monta uma sessão só com eles, e as respostas contam como revisões normais.</p>
      <div class="err-bar"><div class="seg" role="group" aria-label="Período">${seg}</div>${redo}</div>
      <p class="err-summary">${esc(summary)}</p>
      ${d.cards ? reasonsSummary(d) : ""}
      ${d.groups.map((g) => errGroup(g, d.days)).join("")}
    </div>`);
  }

  function reasonsSummary(d) {
    const marked = d.reasons.reduce((n, r) => n + r.n, 0);
    if (!marked)
      return `<p class="muted small err-hint">Quando errar um cartão, marque o motivo logo abaixo do gabarito: Não sabia, Confundi, Falta de atenção ou Pegadinha. O resumo aparece aqui.</p>`;
    const max = Math.max(1, ...d.reasons.map((r) => r.n));
    return `<section class="section err-reasons"><div class="section-head"><h2>Por que você errou</h2><span class="muted">${plural(marked, "erro com motivo", "erros com motivo")}, de ${d.misses}</span></div>
      <div class="reason-bars">${d.reasons
        .map((r) => `<div class="reason-row"><span>${esc(r.label)}</span><span class="rbar"><i style="--w:${Math.round((r.n / max) * 100)}%"></i></span><span class="num">${r.n}</span></div>`)
        .join("")}</div></section>`;
  }

  function errGroup(g, days) {
    const withLaw = g.items.some((it) => it.law);
    let law = null;
    let rows = "";
    for (const it of g.items) {
      if (withLaw && it.law !== law) {
        law = it.law;
        rows += `<li class="err-law">${esc(law || "Sem etiqueta de lei")}</li>`;
      }
      rows += errItem(it);
    }
    const redo = g.did && g.available ? `<button class="btn small" data-act="err-redo" data-days="${days}" data-did="${g.did}">Refazer</button>` : "";
    return `<section class="section err-group"><div class="section-head"><h2>${esc(g.name)}</h2><div class="head-actions"><span class="muted">${plural(g.items.length, "cartão", "cartões")}</span>${redo}</div></div>
      <ul class="err-list">${rows}</ul></section>`;
  }

  function errItem(it) {
    const reason = it.reason ? REASONS.find((r) => r[0] === it.reason) : null;
    const meta = [it.n > 1 ? `errou ${it.n} vezes` : "errou 1 vez", `última: ${fmtWhen(it.last)}`, reason ? reason[1] : "", it.suspended ? "suspenso" : ""]
      .filter(Boolean)
      .join(" · ");
    const trap = it.trap
      ? ` <span class="trap-from">${esc(it.trap.from)}</span> <span class="trap-arrow" aria-label="na lei">→</span> <span class="trap-to">${esc(it.trap.to)}</span>`
      : "";
    return `<li class="err-item">
      <button class="err-main" data-act="err-open" data-cid="${it.cid}" aria-expanded="false">
        <span class="bubble wrong" aria-hidden="true"></span>
        <span class="err-body"><span class="err-text">${esc(it.text)}</span><span class="err-meta">${esc(meta)}</span></span>
      </button>
      <div class="err-detail" hidden>
        ${it.correct ? `<p class="err-gab">Gabarito: <strong>${esc(gabaritoWord(it.correct))}</strong>${trap ? `<span class="err-trap">${trap}</span>` : ""}</p>` : ""}
        <div class="sheet err-sheet"></div>
        <div class="actions"><button class="btn quiet" data-act="edit-card" data-cid="${it.cid}">Editar no Anki</button></div>
      </div></li>`;
  }

  async function toggleErr(btn) {
    const li = btn.closest(".err-item");
    const detail = li.querySelector(".err-detail");
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!open));
    li.classList.toggle("open", !open);
    detail.hidden = open;
    if (open) return;
    animate(detail, "rise");
    if (detail.dataset.loaded) return;
    detail.dataset.loaded = "1";
    try {
      const card = await api("erro_card", { cid: Number(btn.dataset.cid) });
      mountFrame(detail.querySelector(".err-sheet"), card.back, card.css);
    } catch (err) {
      detail.dataset.loaded = "";
    }
  }

  // ---------------------------------------------------------------- roleta: data
  const roState = () => (S.ro ? S.ro.state : null);
  const subLabel = (s) => s.name || "Geral";
  const hasNamedSubs = (c) => c.subs.some((s) => s.name);

  function roCat() {
    const st = roState();
    if (!st || !st.cats.length) return null;
    return st.cats.find((c) => c.id === st.ui.cat) || st.cats[0];
  }

  function scopeOf(cat) {
    if (!cat || !cat.subs.length) return { subs: [], all: false };
    if (cat.subs.length > 1 && (cat.sel === "_all" || !cat.subs.some((s) => s.id === cat.sel))) return { subs: cat.subs, all: true };
    const sub = cat.subs.find((s) => s.id === cat.sel) || cat.subs[0];
    return { subs: [sub], all: false };
  }

  function itemsOf(subs) {
    const items = [];
    for (const s of subs) for (const t of s.topics) items.push({ t, s });
    return items;
  }

  const countSeen = (items) => items.reduce((n, it) => n + (it.t.seen ? 1 : 0), 0);
  const pathOf = (cat, sub) => (hasNamedSubs(cat) ? `${cat.name} › ${subLabel(sub)}` : cat.name);

  function scopeName(cat) {
    const sc = scopeOf(cat);
    if (sc.all) return `${cat.name}, todos os tópicos`;
    return sc.subs[0] ? pathOf(cat, sc.subs[0]) : cat.name;
  }

  function findTopic(id) {
    const st = roState();
    if (!st) return null;
    for (const cat of st.cats)
      for (const sub of cat.subs) {
        const i = sub.topics.findIndex((t) => t.id === id);
        if (i >= 0) return { cat, sub, topic: sub.topics[i], index: i };
      }
    return null;
  }

  const COUNT_CHANGES = /^roleta_(rename|add|import|save_cat|remove|clear|undo|link|delete_cat)$/;

  async function roCall(method, args = {}, opts = {}) {
    if (COUNT_CHANGES.test(method)) S.roCounts = null;
    const res = await api(method, args, opts);
    if (COUNT_CHANGES.test(method)) S.roCounts = null;
    if (res && res.state) S.ro = res;
    if (opts.refresh !== false && S.view === "roleta") refreshRoleta();
    if (res && res.toast) toast(res.toast, opts.undo ? { action: { label: "Desfazer", fn: roUndo } } : {});
    return res;
  }

  const roUndo = () =>
    roCall("roleta_undo").then(() => {
      if (S.view === "roleta") renderRoleta();
      else rerender();
    });

  // ---------------------------------------------------------------- roleta: wheel
  const TAU = Math.PI * 2;
  const MAX_LABELED = 24; // up to this many topics the wheel shows the names, as in the app
  const DECOR_SEGS = 16;
  const PALETTE = {
    light: ["#d6e0ee", "#dfe9d8", "#efe1c9", "#ecd8df", "#d5e6ea", "#e6e1cc", "#ddd6ec", "#eedbd0"],
    dark: ["#2a3953", "#2c4535", "#4b3f27", "#4a2f38", "#27444a", "#45402a", "#383252", "#4b342b"],
  };
  const WHEEL_FONT = '"Barlow Semi Condensed", "Barlow", "Segoe UI", sans-serif';
  const WHEEL = { px: 0, rotation: 0, spin: null, hideId: null, hitId: null };
  const fitCache = new Map();
  const labelCache = new Map();
  const LABEL_MAX = 15;
  const LABEL_MIN = 11.5;

  function clearTextCaches() {
    fitCache.clear();
    labelCache.clear();
  }

  // How a topic's name fits its slice: one line, with the type shrinking down to LABEL_MIN,
  // or two lines where the slice is wide enough. Two lines keep apart long names that start
  // alike ("Crimes contra a pessoa", "Crimes contra o patrimônio").
  function labelLayout(ctx, text, R, hubR, seg) {
    const key = [text, R, hubR, seg.toFixed(5)].join("|");
    if (labelCache.has(key)) return labelCache.get(key);
    const font = (fs) => "600 " + fs.toFixed(1) + "px " + WHEEL_FONT;
    const outer = R - 14;
    const inner = hubR + 10;
    const base = Math.max(LABEL_MIN, Math.min(LABEL_MAX, seg * R * 0.42));
    let out = null;
    for (let fs = base; fs >= LABEL_MIN; fs -= 0.5) {
      ctx.font = font(fs);
      if (ctx.measureText(text).width <= outer - inner) {
        out = { font: font(fs), lines: [text], lh: 0 };
        break;
      }
    }
    if (!out) {
      ctx.font = font(LABEL_MIN);
      const one = fitText(ctx, text, outer - inner);
      out = { font: font(LABEL_MIN), lines: [one], lh: 0 };
      const fs2 = Math.max(LABEL_MIN, Math.min(13, base));
      const lh = fs2 * 1.15;
      const half = seg >= Math.PI ? 1 : Math.sin(seg / 2);
      const inner2 = Math.max(inner, (lh * 2 + 4) / (2 * half)); // where the slice is two lines tall
      const len2 = outer - inner2;
      if (len2 >= 48) {
        ctx.font = font(fs2);
        const words = text.split(/\s+/).filter(Boolean);
        let first = "";
        let k = 0;
        while (k < words.length) {
          const next = first ? first + " " + words[k] : words[k];
          if (ctx.measureText(next).width > len2) break;
          first = next;
          k++;
        }
        const rest = words.slice(k).join(" ");
        if (k > 0 && rest) {
          const second = fitText(ctx, rest, len2);
          const shown = (s) => s.replace(/…$/, "").length;
          if (shown(first) + shown(second) > shown(one) + 2) out = { font: font(fs2), lines: [first, second], lh };
        }
      }
    }
    if (labelCache.size > 2000) labelCache.clear();
    labelCache.set(key, out);
    return out;
  }

  function wheelColors() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    const dark = document.documentElement.classList.contains("night-mode");
    return { dark, sheet: v("--sheet"), form: v("--form"), ink: v("--ink"), pencil: v("--pencil"), seen: dark ? "#1a1e27" : "#eef0f3" };
  }

  function fitText(ctx, s, w) {
    const key = ctx.font + "|" + w + "|" + s;
    if (fitCache.has(key)) return fitCache.get(key);
    let out = s;
    if (ctx.measureText(s).width > w) {
      let lo = 0;
      let hi = s.length;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (ctx.measureText(s.slice(0, mid) + "…").width <= w) lo = mid;
        else hi = mid - 1;
      }
      out = s.slice(0, lo).trimEnd() + "…";
    }
    if (fitCache.size > 3000) fitCache.clear();
    fitCache.set(key, out);
    return out;
  }

  function sector(ctx, cx, cy, r, a0, a1, full) {
    ctx.beginPath();
    if (full) ctx.arc(cx, cy, r, 0, TAU);
    else {
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, a0, a1);
      ctx.closePath();
    }
  }

  function sizeWheel() {
    const wrap = document.getElementById("ro-wheel-wrap");
    const cv = document.getElementById("ro-wheel");
    const stage = wrap && wrap.closest(".ro-stage");
    if (!wrap || !cv || !stage) return;
    // the wheel gives up size before the Girar button leaves the screen
    let byHeight = 420;
    const main = document.getElementById("main");
    if (main) {
      const box = main.getBoundingClientRect();
      const wrapTop = wrap.getBoundingClientRect().top - box.top + main.scrollTop;
      const below = stage.getBoundingClientRect().bottom - cv.getBoundingClientRect().bottom;
      byHeight = main.clientHeight - wrapTop - 12 - below - 14;
    }
    const px = Math.round(Math.max(260, Math.min(wrap.clientWidth - 8, 420, byHeight)));
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const w = Math.round(px * dpr);
    if (px !== WHEEL.px || cv.width !== w) {
      cv.width = w;
      cv.height = w;
      cv.style.width = px + "px";
      cv.style.height = px + "px";
      WHEEL.px = px;
      clearTextCaches();
    }
    drawWheel();
  }

  function drawWheel() {
    const cv = document.getElementById("ro-wheel");
    if (!cv || !WHEEL.px) return;
    const ctx = cv.getContext("2d");
    const size = WHEEL.px;
    ctx.setTransform(cv.width / size, 0, 0, cv.width / size, 0, 0);
    ctx.clearRect(0, 0, size, size);
    const col = wheelColors();
    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - 6;
    const cat = roCat();
    const items = cat ? itemsOf(scopeOf(cat).subs) : [];
    if (!items.length) {
      ctx.beginPath();
      ctx.arc(cx, cy, R - 4, 0, TAU);
      ctx.setLineDash([6, 7]);
      ctx.lineWidth = 2;
      ctx.strokeStyle = col.form;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = col.pencil;
      ctx.font = "500 15px " + WHEEL_FONT;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("Sem tópicos nesta seleção", cx, cy);
      return;
    }
    const seenOf = (t) => t.seen && t.id !== WHEEL.hideId;
    const labeled = items.length <= MAX_LABELED;
    const n = labeled ? items.length : DECOR_SEGS;
    const seg = TAU / n;
    const pal = PALETTE[col.dark ? "dark" : "light"];
    const start = -Math.PI / 2 + WHEEL.rotation;
    for (let i = 0; i < n; i++) {
      const a0 = start + i * seg;
      const seen = labeled && seenOf(items[i].t);
      sector(ctx, cx, cy, R, a0, a0 + seg, n === 1);
      let c = i % pal.length;
      if (n > 1 && i === n - 1 && c === 0) c = Math.floor(pal.length / 2); // no two neighbours alike
      ctx.fillStyle = seen ? col.seen : pal[c];
      ctx.fill();
      if (n > 1) {
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = col.sheet;
        ctx.stroke();
      }
    }
    const hr = Math.max(22, R * 0.16);
    if (labeled) {
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      for (let i = 0; i < n; i++) {
        const t = items[i].t;
        const mid = start + i * seg + seg / 2;
        const lay = labelLayout(ctx, t.t, R, hr, seg);
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(mid);
        ctx.font = lay.font;
        ctx.fillStyle = seenOf(t) ? (col.dark ? "rgba(230,232,238,.34)" : "rgba(30,35,51,.34)") : col.ink;
        if (lay.lines.length === 1) ctx.fillText(lay.lines[0], R - 14, 0);
        else {
          ctx.fillText(lay.lines[0], R - 14, -lay.lh / 2);
          ctx.fillText(lay.lines[1], R - 14, lay.lh / 2);
        }
        ctx.restore();
      }
      if (WHEEL.hitId && !WHEEL.spin) {
        const i = items.findIndex((it) => it.t.id === WHEEL.hitId);
        if (i >= 0) {
          const a0 = start + i * seg;
          sector(ctx, cx, cy, R - 2, a0, a0 + seg, n === 1);
          ctx.lineWidth = 3;
          ctx.lineJoin = "round";
          ctx.strokeStyle = col.ink;
          ctx.stroke();
        }
      }
    }
    // rim and pins
    ctx.beginPath();
    ctx.arc(cx, cy, R + 1, 0, TAU);
    ctx.lineWidth = 3;
    ctx.strokeStyle = col.form;
    ctx.stroke();
    if (n > 1 && n <= 40) {
      ctx.fillStyle = col.sheet;
      for (let i = 0; i < n; i++) {
        const a = start + i * seg;
        ctx.beginPath();
        ctx.arc(cx + Math.cos(a) * (R - 5), cy + Math.sin(a) * (R - 5), 2.2, 0, TAU);
        ctx.fill();
      }
    }
    // hub with the topics still in the draw
    ctx.beginPath();
    ctx.arc(cx, cy, hr, 0, TAU);
    ctx.fillStyle = col.sheet;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = col.form;
    ctx.stroke();
    const pending = items.length - items.reduce((k, it) => k + (seenOf(it.t) ? 1 : 0), 0);
    ctx.fillStyle = col.ink;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "600 " + Math.round(hr * (pending > 99 ? 0.6 : 0.78)) + "px " + WHEEL_FONT;
    ctx.fillText(String(pending), cx, cy + 1);
  }

  function pointerIndex(n, seg) {
    const th = ((-WHEEL.rotation % TAU) + TAU) % TAU;
    return Math.min(n - 1, Math.floor(th / seg));
  }

  function setTicker(text, live) {
    const box = document.getElementById("ro-ticker");
    const span = document.getElementById("ro-ticker-text");
    if (!box || !span) return;
    span.textContent = text;
    box.title = text;
    box.classList.toggle("live", !!live);
  }

  function idleTicker(items) {
    if (!items.length) return "Adicione tópicos para começar";
    let last = null;
    for (const it of items) if (it.t.seen && (!last || it.t.seen > last.t.seen)) last = it;
    if (!last) return "Pronto para girar";
    const w = fmtWhen(last.t.seen);
    return "Último: " + last.t.t + (w ? ", " + w : "");
  }

  function flickPointer() {
    const p = document.getElementById("ro-pointer");
    if (!p || !motionOK()) return;
    p.classList.add("flick");
    clearTimeout(p._t);
    p._t = setTimeout(() => p.classList.remove("flick"), 70);
  }

  function stopSpin() {
    if (WHEEL.spin) {
      WHEEL.spin = null;
      WHEEL.hideId = null;
      document.body.classList.remove("spinning");
    }
  }

  async function roSpin(opts = {}) {
    if (WHEEL.spin) {
      WHEEL.spin.skip = true;
      return;
    }
    if (overlays.length || S.view !== "roleta") return;
    const cat = roCat();
    if (!cat) return toast("Importe ou crie uma matéria antes de girar.", { error: true });
    if (!itemsOf(scopeOf(cat).subs).length) return toast("Adicione tópicos a esta seleção para girar.", { error: true });
    let res;
    try {
      res = opts.again ? await api("roleta_again", { tid: opts.again }) : await api("roleta_spin", { cat: cat.id });
    } catch (err) {
      return;
    }
    S.ro = res;
    const pick = res.pick;
    const scopeCat = roCat();
    const items = itemsOf(scopeOf(scopeCat).subs);
    if (pick.reset) {
      play("reset");
      toast(`Novo ciclo: ${plural(pick.reset, "tópico voltou", "tópicos voltaram")} ao sorteio.`);
    }
    WHEEL.hideId = pick.id;
    WHEEL.hitId = null;
    refreshRoleta({ lists: false });
    const labeled = items.length <= MAX_LABELED;
    const n = labeled ? items.length : DECOR_SEGS;
    const seg = TAU / n;
    const dest = labeled ? -(pick.index * seg + seg / 2) + (Math.random() - 0.5) * seg * 0.6 : Math.random() * TAU;
    const moving = motionOK();
    const turns = moving ? 5 + Math.floor(Math.random() * 3) : 0;
    const from = WHEEL.rotation;
    const base = from + turns * TAU;
    const to = base + ((((dest - base) % TAU) + TAU) % TAU); // always forward
    WHEEL.spin = { from, to, t0: performance.now(), dur: moving ? 4200 + Math.random() * 1300 : 0, pick, items, labeled, n, seg, lastIdx: -1, skip: false };
    document.body.classList.add("spinning");
    const btn = document.getElementById("ro-spin");
    if (btn) btn.textContent = "Parar a animação";
    play("spin");
    setTicker("Girando…", true);
    requestAnimationFrame(spinFrame);
  }

  const easeOut = (t) => 1 - Math.pow(1 - t, 4);

  function spinFrame(now) {
    const s = WHEEL.spin;
    if (!s) return;
    let t = s.skip || !s.dur ? 1 : (now - s.t0) / s.dur;
    t = t >= 1 ? 1 : t > 0 ? t : 0;
    WHEEL.rotation = s.from + (s.to - s.from) * easeOut(t);
    drawWheel();
    if (t < 1) {
      const idx = pointerIndex(s.n, s.seg);
      if (idx !== s.lastIdx) {
        s.lastIdx = idx;
        play("tick", idx);
        flickPointer();
        const it = s.labeled ? s.items[idx] : s.items[Math.floor(Math.random() * s.items.length)];
        if (it) setTicker(it.t.t, true);
      }
      requestAnimationFrame(spinFrame);
    } else finishSpin();
  }

  function finishSpin() {
    const s = WHEEL.spin;
    WHEEL.spin = null;
    WHEEL.hideId = null;
    document.body.classList.remove("spinning");
    WHEEL.rotation = ((WHEEL.rotation % TAU) + TAU) % TAU;
    const found = findTopic(s.pick.id);
    WHEEL.hitId = s.pick.id;
    refreshRoleta();
    if (!found) return;
    setTicker(found.topic.t, true);
    play(s.pick.cycle_done ? "cycle" : "reveal");
    openTopicDialog(found.topic.id, "result", { cycleDone: s.pick.cycle_done });
  }

  // ---------------------------------------------------------------- roleta: page
  async function viewRoleta(args = {}) {
    S.ro = await api("roleta");
    if (S.ro.fx) S.fx = S.ro.fx;
    applyFx();
    renderRoleta();
    if (args.spin) setTimeout(() => roSpin(), motionOK() ? 350 : 0);
  }

  function renderRoleta() {
    const st = roState();
    const cat = roCat();
    const head = `<div class="ro-head"><h1>Roleta</h1><div class="actions">
        <button class="btn quiet" data-act="ro-import">Importar e backup</button>${soundButton()}</div></div>`;
    if (!cat) {
      page(`<div class="page wide">${head}
        <div class="empty ro-empty"><p>Monte sua roleta.</p>
        <p class="muted">Cole o bloco JSON da skill exportar-roleta, ou restaure um backup da Roleta de Estudos: os vistos, as datas e as anotações vêm junto. Também dá para criar uma matéria e digitar os tópicos.</p>
        <div class="actions"><button class="btn primary" data-act="ro-import">Importar tópicos ou backup</button><button class="btn" data-act="ro-new">Criar matéria</button></div></div></div>`);
      return;
    }
    page(`<div class="page wide">${head}
      <div class="ro-toolbar">
        <label class="inline">Matéria <select class="select" data-ro-cat>${st.cats
          .map((c) => `<option value="${esc(c.id)}" ${c.id === cat.id ? "selected" : ""}>${esc(c.name)}</option>`)
          .join("")}</select></label>
        <button class="btn quiet" data-act="ro-org">Organizar</button>
        <button class="btn quiet" data-act="ro-new">Nova matéria</button>
      </div>
      <div class="chips" id="ro-chips"></div>
      <div class="ro-layout">
        <section class="ro-stage" aria-label="Roleta">
          <p class="ro-scope" id="ro-scope"></p>
          <div class="ro-wheel-wrap" id="ro-wheel-wrap"><div class="ro-pointer" id="ro-pointer" aria-hidden="true"></div><canvas id="ro-wheel" role="img" aria-label="Roleta"></canvas></div>
          <div class="ro-ticker" id="ro-ticker" aria-live="polite"><span id="ro-ticker-text"></span></div>
          <div class="ro-progress" id="ro-progress"></div>
          <button class="btn primary ro-spin" id="ro-spin" data-act="ro-spin">Girar</button>
          <div class="ro-foot"><span class="muted">Atalho: espaço</span><button class="link" data-act="ro-reset" id="ro-reset" hidden>Reiniciar ciclo</button></div>
        </section>
        <section class="ro-sheet" aria-label="Tópicos">
          <div class="tabs" role="tablist">
            <button class="tab" data-act="ro-tab" data-tab="hist" role="tab">Histórico <span class="badge" id="ro-hist-n"></span></button>
            <button class="tab" data-act="ro-tab" data-tab="list" role="tab">Tópicos <span class="badge" id="ro-list-n"></span></button>
          </div>
          <div id="ro-panel"></div>
        </section>
      </div></div>`);
    sizeWheel();
    if (document.fonts && document.fonts.load) document.fonts.load("600 14px " + WHEEL_FONT).then(() => {
        clearTextCaches(); // measured with a fallback font until now
        drawWheel();
      }).catch(() => {});
    refreshRoleta();
  }

  function refreshRoleta(opts = {}) {
    const cat = roCat();
    if (!cat || !document.getElementById("ro-wheel")) return;
    const sc = scopeOf(cat);
    const items = itemsOf(sc.subs);
    const hide = (t) => t.id === WHEEL.hideId;
    const seen = items.reduce((k, it) => k + (it.t.seen && !hide(it.t) ? 1 : 0), 0);
    document.getElementById("ro-scope").textContent = scopeName(cat);
    const select = document.querySelector("[data-ro-cat]");
    if (select) select.value = cat.id;
    // subcategory chips with their progress
    const chips = document.getElementById("ro-chips");
    if (!hasNamedSubs(cat)) chips.innerHTML = "";
    else {
      const chip = (sel, label, list) => {
        const its = itemsOf(list);
        const k = countSeen(its);
        const on = sel === "_all" ? sc.all : !sc.all && sc.subs[0] && sc.subs[0].id === sel;
        return `<button class="chip ${on ? "on" : ""}" data-act="ro-sel" data-sel="${esc(sel)}" aria-pressed="${on}"><span class="chip-fill" style="width:${its.length ? Math.round((k / its.length) * 100) : 0}%"></span><span class="chip-label">${esc(label)}</span><span class="chip-count num">${k}/${its.length}</span></button>`;
      };
      chips.innerHTML = (cat.subs.length > 1 ? chip("_all", "Todos", cat.subs) : "") + cat.subs.map((s) => chip(s.id, subLabel(s), [s])).join("");
    }
    const progress = document.getElementById("ro-progress");
    const pcts = items.length ? Math.round((seen / items.length) * 100) : 0;
    progress.innerHTML = `<div class="prog-text"><span>${seen} de ${items.length} vistos neste ciclo</span><span>${items.length - seen} no sorteio</span></div><div class="bar"><div class="bar-fill" style="width:${pcts}%"></div></div>`;
    document.getElementById("ro-reset").hidden = !seen || !!WHEEL.spin;
    const spinBtn = document.getElementById("ro-spin");
    if (spinBtn && !WHEEL.spin) spinBtn.textContent = "Girar";
    if (!WHEEL.spin) setTicker(idleTicker(items), false);
    document.getElementById("ro-hist-n").textContent = String(seen);
    document.getElementById("ro-list-n").textContent = String(items.length);
    document.querySelectorAll(".ro-sheet .tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === S.roTab)));
    if (opts.lists !== false) renderPanel();
    sizeWheel(); // the chips row comes and goes with the matéria, which moves the wheel
  }

  function renderPanel() {
    const cat = roCat();
    const panel = document.getElementById("ro-panel");
    if (!cat || !panel) return;
    const sc = scopeOf(cat);
    const items = itemsOf(sc.subs);
    if (S.roTab === "hist") {
      const seenItems = items.filter((it) => it.t.seen).sort((a, b) => a.t.seen - b.t.seen);
      if (!seenItems.length) {
        panel.innerHTML = `<div class="empty"><p>Nada sorteado neste ciclo.</p><p class="muted">Gire a roleta. Os tópicos sorteados aparecem aqui, do mais recente para o mais antigo.</p></div>`;
        return;
      }
      let rows = "";
      for (let i = seenItems.length - 1; i >= 0; i--) {
        const { t, s } = seenItems[i];
        const when = fmtWhen(t.seen);
        const meta = sc.all ? subLabel(s) + (when ? ", " + when : "") : when;
        rows += `<div class="ro-row ${t.id === WHEEL.hitId ? "hit" : ""}">
          <span class="ord num" aria-label="Ordem">${i + 1}</span>
          <button class="ro-main" data-act="ro-detail" data-tid="${esc(t.id)}"><span class="ro-title">${esc(t.t)}</span>${meta ? `<span class="ro-meta">${esc(meta)}</span>` : ""}</button>
          ${t.note ? `<button class="icon-btn has" data-act="ro-detail" data-tid="${esc(t.id)}" title="Ver anotação">${ICON.note}</button>` : ""}
          <button class="icon-btn" data-act="ro-unsee" data-tid="${esc(t.id)}" title="Voltar ao sorteio">${ICON.undo}</button>
          <button class="icon-btn del" data-act="ro-remove" data-tid="${esc(t.id)}" title="Remover tópico">${ICON.trash}</button>
        </div>`;
      }
      panel.innerHTML = `<div class="ro-list">${rows}</div>`;
      return;
    }
    const q = norm(S.roQuery);
    const shown = items.filter(
      (it) =>
        (S.roFilter === "all" || (S.roFilter === "seen" ? it.t.seen : !it.t.seen)) &&
        (!q || norm(it.t.t).includes(q) || norm(it.t.note).includes(q))
    );
    const seg = [
      ["all", "Tudo"],
      ["pending", "Pendentes"],
      ["seen", "Vistos"],
    ]
      .map(([f, label]) => `<button class="${S.roFilter === f ? "on" : ""}" data-act="ro-filter" data-f="${f}">${label}</button>`)
      .join("");
    const counts = S.roCounts && S.roCounts.cat === cat.id ? S.roCounts.counts : null;
    if (!counts && cat.deck) loadCardCounts(cat.id);
    const rows = shown
      .map(
        ({ t, s }) => `<div class="ro-row">
          <button class="topic-toggle" data-act="ro-toggle" data-tid="${esc(t.id)}" aria-pressed="${!!t.seen}" title="${t.seen ? "Voltar ao sorteio" : "Marcar como visto"}"><span class="bubble ${t.seen ? "full" : ""}"></span></button>
          <div class="ro-namebox"><input class="ro-name" data-rename="${esc(t.id)}" value="${esc(t.t)}" aria-label="Nome do tópico" title="${esc(t.t)}" spellcheck="false">${
            sc.all ? `<span class="ro-sub">${esc(subLabel(s))}</span>` : ""
          }</div>
          ${cardsPill(counts, t)}
          <button class="icon-btn ${t.note ? "has" : ""}" data-act="ro-detail" data-tid="${esc(t.id)}" title="${t.note ? "Ver anotação" : "Anotar"}">${ICON.note}</button>
          <button class="icon-btn del" data-act="ro-remove" data-tid="${esc(t.id)}" title="Remover tópico">${ICON.trash}</button>
        </div>`
      )
      .join("");
    const addSub =
      sc.all && cat.subs.length > 1
        ? `<select class="select" id="ro-add-sub" aria-label="Subcategoria do novo tópico">${cat.subs.map((s) => `<option value="${esc(s.id)}">${esc(subLabel(s))}</option>`).join("")}</select>`
        : "";
    const keep = document.activeElement && document.activeElement.id === "ro-search";
    panel.innerHTML = `<div class="ro-tools"><input class="input search" id="ro-search" type="search" placeholder="Buscar tópico ou anotação" value="${esc(S.roQuery)}" autocomplete="off"><div class="seg" role="group" aria-label="Filtro">${seg}</div></div>
      <div class="ro-list">${rows || `<p class="muted pad">Nenhum tópico ${S.roQuery ? "encontrado" : "nesta seleção"}.</p>`}</div>
      <div class="ro-add">${addSub}<input class="input" id="ro-add-input" placeholder="Novo tópico" autocomplete="off"><button class="btn primary" data-act="ro-add">Adicionar</button></div>`;
    if (keep) {
      const input = document.getElementById("ro-search");
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  // ---------------------------------------------------------------- roleta: dialogs
  function openTopicDialog(tid, mode, info = {}) {
    const f = findTopic(tid);
    if (!f) return;
    const result = mode === "result";
    const when = fmtWhen(f.topic.seen);
    const deck = f.cat.deck;
    const el = overlay(`<div class="dialog result-dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-topic">
      <p class="kicker">${result ? "Tópico sorteado" : "Tópico"}</p>
      <h2 class="res-topic" id="dlg-topic">${esc(f.topic.t)}</h2>
      <p class="res-path">${esc(pathOf(f.cat, f.sub))}</p>
      ${!result ? `<p class="res-status">${f.topic.seen ? "Visto neste ciclo" + (when ? ", " + esc(when) : "") : "Pendente neste ciclo"}</p>` : ""}
      ${result && info.cycleDone ? `<p class="res-cycle">Ciclo concluído: todos os tópicos desta seleção já saíram. No próximo giro eles voltam ao sorteio.</p>` : ""}
      <label class="field note-field"><span>Anotação</span><textarea class="note" data-note="${esc(f.topic.id)}" rows="3" placeholder="Artigos, súmulas, pontos a revisar">${esc(f.topic.note || "")}</textarea></label>
      <div class="topic-cards" id="topic-cards" aria-live="polite">${deck ? `<p class="muted small">Procurando os cartões deste tópico…</p>` : ""}</div>
      <div class="actions">
        ${
          result
            ? `<button class="btn primary" data-act="ro-accept" data-tid="${esc(f.topic.id)}" title="Cria o baralho do tópico dentro do baralho da matéria">Estudar</button>`
            : `<button class="btn primary" data-act="dlg-close">Fechar</button>`
        }
        ${result && !info.cycleDone ? `<button class="btn" data-act="ro-again" data-tid="${esc(f.topic.id)}">Sortear outro</button>` : ""}
        ${!result ? `<button class="btn" data-act="ro-toggle-dlg" data-tid="${esc(f.topic.id)}">${f.topic.seen ? "Voltar ao sorteio" : "Marcar como visto"}</button>` : ""}
        <span class="topic-study" id="topic-study">${deck ? `<button class="btn" data-act="study" data-did="${deck}">Estudar os cartões dessa matéria</button>` : ""}</span>
      </div>
      <div class="res-foot"><button class="link danger" data-act="ro-remove-dlg" data-tid="${esc(f.topic.id)}">Remover tópico</button></div>
    </div>`);
    if (result) {
      animate(el.querySelector(".res-topic"), "stamp");
      setTimeout(() => el.querySelector(".btn.primary").focus(), 60);
    }
    el._onClose = () => {
      flushNote();
      if (S.view === "roleta") refreshRoleta();
    };
    el._tid = f.topic.id;
    loadTopicCards(el);
  }

  // ---------------------------------------------------------------- roleta: a topic's cards
  async function loadTopicCards(el, opts = {}) {
    let info;
    try {
      info = await api("roleta_topic_cards", { tid: el._tid, tags: !!opts.picker }, { quiet: true });
    } catch (err) {
      const box = el.querySelector("#topic-cards");
      if (box) box.innerHTML = "";
      return;
    }
    if (!el.isConnected) return;
    el._cards = info;
    renderTopicCards(el, opts);
  }

  function renderTopicCards(el, opts = {}) {
    const box = el.querySelector("#topic-cards");
    const slot = el.querySelector("#topic-study");
    const info = el._cards;
    if (!box || !slot || !info) return;
    const n = info.count || 0;
    slot.innerHTML = topicStudyButton(info, info.deck, info.tid);
    const cards = (k) => plural(k, "cartão", "cartões");
    const link = (act, label) => `<button class="link" data-act="${act}">${label}</button>`;
    const pick = link("tc-pick", info.mode === "tag" ? "Mudar a etiqueta" : "Escolher uma etiqueta");
    const suggestion = info.suggest
      ? ` Sugestão: etiqueta ${esc(info.suggest.label)} (${cards(info.suggest.n)}). <button class="link" data-act="tc-use" data-tag="${esc(info.suggest.tag)}">Usar</button>`
      : "";
    let text = "";
    let links = [];
    const own = info.topic_deck;
    if (info.mode === "nodeck")
      text = `<p class="muted small">Esta matéria ainda não tem baralho. Ligue a um baralho em Organizar, ou clique Estudar num tópico sorteado: o painel cria o baralho da matéria e o do tópico.</p>`;
    else if (info.mode === "deck") {
      text = `<p class="small">${cards(n)} no baralho do tópico, ${esc(own.path)}.</p>`;
      links = [pick];
    } else if (info.mode === "tag") {
      text = `<p class="small">${cards(n)} pela etiqueta ${esc(info.tag_label)}.</p>`;
      links = [pick, link("tc-auto", info.has_articles ? "Usar os artigos do nome" : "Desligar")];
    } else if (info.mode === "articles" && info.ambiguous)
      text = `<p class="small">Os ${esc(info.arts_text)} aparecem em mais de uma lei em ${esc(info.deck_name)}. De qual lei é este tópico?</p>
        <div class="inline tc-row"><select class="select" id="tc-law" aria-label="Lei do tópico">${info.laws
          .map((l) => `<option value="${esc(l.key)}">${esc(l.label)} (${cards(l.n)})</option>`)
          .join("")}</select><button class="btn" data-act="tc-law">Usar esta lei</button></div>`;
    else if (info.mode === "articles" && n) {
      text = `<p class="small">${cards(n)} em ${esc(info.deck_name)} ${esc(info.arts_label)}${info.law_label ? `, ${esc(info.law_label)}` : ""}.</p>`;
      links = info.chosen ? [link("tc-auto", "Trocar a lei"), pick] : [pick];
    } else if (info.mode === "articles") {
      text = `<p class="muted small">Nenhum cartão em ${esc(info.deck_name)} ${esc(info.arts_label)}.${suggestion}</p>`;
      links = [pick];
    } else {
      text = `<p class="muted small">O nome deste tópico não traz artigos.${suggestion}</p>`;
      links = [pick];
    }
    if (own && info.mode !== "deck") text += `<p class="muted small">Baralho do tópico: ${esc(own.path)}, ${own.n ? cards(own.n) : "ainda sem cartões"}.</p>`;
    let html = text + (links.length && !opts.picker ? `<div class="tc-links">${links.join("")}</div>` : "");
    if (opts.picker && info.tags) {
      const current = info.mode === "tag" ? info.tag : info.suggest ? info.suggest.tag : "";
      html += info.tags.length
        ? `<div class="inline tc-row"><select class="select" id="tc-tag" aria-label="Etiqueta dos cartões">${info.tags
            .map((t) => `<option value="${esc(t.tag)}" ${t.tag === current ? "selected" : ""}>${esc(t.label)} (${t.n})</option>`)
            .join("")}</select><button class="btn" data-act="tc-tag">Usar esta etiqueta</button><button class="btn quiet" data-act="tc-cancel">Cancelar</button></div>`
        : `<p class="muted small">Os cartões de ${esc(info.deck_name)} não têm etiquetas.</p>`;
    }
    box.innerHTML = html;
    if (opts.picker) {
      const select = box.querySelector("#tc-tag");
      if (select) select.focus();
    }
  }

  async function linkTopic(el, link) {
    let res;
    try {
      res = await roCall("roleta_link", { tid: el._tid, link }, { refresh: false });
    } catch (err) {
      return;
    }
    if (!el.isConnected) return;
    el._cards = res.cards;
    renderTopicCards(el);
    play("mark");
  }

  let countsLoading = null;
  function loadCardCounts(catId) {
    if (countsLoading === catId) return;
    countsLoading = catId;
    api("roleta_card_counts", { cat: catId }, { quiet: true })
      .then((res) => {
        S.roCounts = res;
        const cat = roCat();
        if (S.view === "roleta" && S.roTab === "list" && cat && cat.id === res.cat) renderPanel();
      })
      .catch(() => {})
      .finally(() => {
        countsLoading = null;
      });
  }

  function cardsPill(counts, t) {
    const c = counts && counts[t.id];
    if (!c) return "";
    if (c.ambiguous) return `<span class="ro-cards amb" title="Esses artigos aparecem em mais de uma lei: escolha a lei no tópico">?</span>`;
    return `<span class="ro-cards ${c.n ? "" : "zero"}" title="${c.n ? plural(c.n, "cartão", "cartões") + " no Anki" : "Nenhum cartão no Anki para este tópico"}">${c.n}</span>`;
  }

  let noteTimer = null;
  let notePending = null;
  function queueNote(tid, note) {
    notePending = { tid, note };
    clearTimeout(noteTimer);
    noteTimer = setTimeout(flushNote, 450);
  }
  function flushNote() {
    clearTimeout(noteTimer);
    if (!notePending) return;
    const { tid, note } = notePending;
    notePending = null;
    roCall("roleta_note", { tid, note }, { refresh: false }).catch(() => {});
  }

  const FORMATS = `Lista simples por matéria:
{ "Português": ["Crase", "Regência verbal"] }

Com subcategorias:
{ "Legislação complementar": {
    "Lei 14.133/2021": ["Princípios", "Modalidades"],
    "Lei 8.429/1992": ["Sujeitos", "Sanções"] } }

Com separador " > " no nome:
{ "Português > Sintaxe": ["Sujeito", "Predicado"] }

Backup da Roleta de Estudos (arquivo roleta-backup-....json)

Sem JSON, um tópico por linha (entra na seleção atual):
Crase
Regência verbal`;

  function openImport() {
    overlay(`<div class="dialog wide-dialog" role="dialog" aria-modal="true" aria-labelledby="imp-title">
      <h3 id="imp-title">Importar e backup</h3>
      <p class="muted">Cole o bloco JSON da skill exportar-roleta, um backup da Roleta de Estudos ou um tópico por linha. Tópicos repetidos ficam de fora, e matérias com o mesmo nome se juntam mesmo com acentos diferentes.</p>
      <textarea class="paste" id="ro-paste" spellcheck="false" aria-label="Conteúdo a importar" placeholder='{ "Português > Sintaxe": ["Crase", "Regência verbal"] }'></textarea>
      <div class="actions top-gap"><button class="btn" data-act="ro-file">Escolher arquivo</button><span class="spacer"></span><button class="btn primary" data-act="ro-do-import">Importar</button></div>
      <details class="formats"><summary>Formatos aceitos</summary><pre>${esc(FORMATS)}</pre></details>
      <h4>Backup</h4>
      <p class="muted small">Guarda matérias, tópicos, vistos e anotações. O arquivo também abre na Roleta de Estudos. Para restaurar, cole o backup no campo acima ou escolha o arquivo.</p>
      <div class="actions"><button class="btn" data-act="ro-save-backup">Salvar backup em arquivo</button><button class="btn" data-act="ro-copy" data-what="backup">Copiar backup</button><button class="btn" data-act="ro-copy" data-what="topics">Copiar só os tópicos</button><span class="spacer"></span><button class="btn danger" data-act="ro-clear">Apagar tudo</button></div>
      <div class="actions end top-gap"><button class="btn" data-act="dlg-close">Fechar</button></div>
    </div>`);
  }

  async function doImport(text) {
    if (!String(text || "").trim()) return toast("Cole um conteúdo ou escolha um arquivo.", { error: true });
    let info;
    try {
      info = await api("roleta_inspect", { text });
    } catch (err) {
      return;
    }
    if (info.kind === "backup") {
      const ok = await ask({
        title: "Restaurar backup?",
        msg: `O backup tem ${plural(info.cats, "matéria", "matérias")} e ${plural(info.topics, "tópico", "tópicos")}. A Roleta atual será substituída; dá para desfazer logo em seguida.`,
        ok: "Restaurar",
      });
      if (!ok) return;
    }
    let res;
    try {
      res = await roCall("roleta_import", { text }, { refresh: false });
    } catch (err) {
      return;
    }
    closeAllOverlays();
    renderRoleta();
    const r = res.imported;
    let msg;
    if (r.kind === "backup") msg = `Backup restaurado: ${plural(r.cats, "matéria", "matérias")} e ${plural(r.added, "tópico", "tópicos")}.`;
    else {
      msg = plural(r.added, "tópico importado", "tópicos importados");
      if (r.dup) msg += `, ${plural(r.dup, "repetido ignorado", "repetidos ignorados")}`;
      if (r.bad) msg += `, ${plural(r.bad, "item inválido", "itens inválidos")}`;
      msg += ".";
    }
    toast(msg, { action: { label: "Desfazer", fn: roUndo } });
  }

  function openOrganizer(mode) {
    const cat = mode === "edit" ? roCat() : null;
    const subs = cat ? cat.subs.map((s) => ({ id: s.id, name: s.name, n: s.topics.length })) : [{ id: null, name: "", n: 0 }];
    const decks = S.ro.decks || [];
    const el = overlay(`<div class="dialog" role="dialog" aria-modal="true" aria-labelledby="org-title">
      <h3 id="org-title">${cat ? "Organizar matéria" : "Nova matéria"}</h3>
      <label class="field"><span>Nome da matéria</span><input class="input wide-input" id="org-name" value="${esc(cat ? cat.name : "")}" autocomplete="off"></label>
      <label class="field"><span>Baralho do Anki</span><select class="select" id="org-deck"><option value="">Nenhum</option>${decks
        .map((d) => `<option value="${d.id}" ${cat && cat.deck === d.id ? "selected" : ""}>${esc(d.name)}</option>`)
        .join("")}</select></label>
      <div class="org-head"><span>Subcategorias</span><span class="muted small">opcional</span></div>
      <div class="org-list" id="org-subs"></div>
      <button class="link" data-act="org-add-sub">Adicionar subcategoria</button>
      <p class="small muted">Com uma única subcategoria sem nome, a matéria fica sem subdivisões. Excluir uma subcategoria apaga os tópicos dela.</p>
      <p class="err" id="org-err" role="alert"></p>
      <div class="actions">${cat ? `<button class="btn danger" data-act="org-delete">Excluir matéria</button>` : ""}<span class="spacer"></span>
      <button class="btn" data-act="dlg-close">Cancelar</button><button class="btn primary" data-act="org-save">Salvar</button></div>
    </div>`);
    el._org = { cat: cat ? cat.id : null, subs, deck0: cat ? cat.deck : null };
    renderOrgSubs(el);
  }

  function renderOrgSubs(el) {
    el.querySelector("#org-subs").innerHTML = el._org.subs
      .map((s, i) =>
        s.del
          ? ""
          : `<div class="org-row"><input class="input" data-org-sub="${i}" value="${esc(s.name)}" placeholder="${s.id || i ? "Nome da subcategoria" : "Sem nome (Geral)"}" autocomplete="off">
             <span class="muted small">${s.n ? plural(s.n, "tópico", "tópicos") : ""}</span>
             <button class="icon-btn del" data-act="org-del-sub" data-i="${i}" title="Excluir subcategoria">${ICON.x}</button></div>`
      )
      .join("");
  }

  async function saveOrganizer(el) {
    const o = el._org;
    const deckValue = el.querySelector("#org-deck").value;
    const deck = deckValue ? Number(deckValue) : null;
    const args = {
      name: el.querySelector("#org-name").value,
      subs: o.subs.filter((s) => !s.del).map((s) => ({ id: s.id, name: s.name })),
      cat: o.cat,
    };
    if (deck !== o.deck0) args.deck = deck;
    let res;
    try {
      res = await roCall("roleta_save_cat", args, { quiet: true, refresh: false });
    } catch (err) {
      el.querySelector("#org-err").textContent = err.message;
      return;
    }
    closeOverlay(el);
    if (!o.cat) S.roTab = "list";
    renderRoleta();
    if (o.cat) toast(res.removed ? `${plural(res.removed, "tópico excluído", "tópicos excluídos")} com as subcategorias.` : "Alterações salvas.", { action: { label: "Desfazer", fn: roUndo } });
    else toast("Matéria criada. Digite os tópicos na aba Tópicos ou use Importar.");
  }

  // ---------------------------------------------------------------- ajustes
  async function viewAjustes() {
    const d = await api("settings");
    S.fx = d.fx;
    applyFx();
    page(`<div class="page"><h1>Ajustes</h1>
      <p class="lede">Ficam salvos na sua coleção do Anki e sincronizam com ela.</p>
      <section class="section" style="margin-top:0"><div class="section-head"><h2>Meta diária</h2></div>
        <div class="field"><span>Quanto estudar por dia</span>
          <div class="inline"><input class="input num" id="goal-value" type="number" min="1" max="2000" value="${esc(d.goal.value)}">
          <select class="select" id="goal-unit"><option value="cards" ${d.goal.unit === "cards" ? "selected" : ""}>cartões</option><option value="minutes" ${d.goal.unit === "minutes" ? "selected" : ""}>minutos</option></select></div>
        </div></section>
      <section class="section"><div class="section-head"><h2>Matérias</h2></div>
        <div class="field"><span>Onde estão as matérias</span>
          <select class="select" id="root"><option value="">Automático</option>${d.parents.map((p) => `<option value="${p.id}" ${p.id === d.root ? "selected" : ""}>Sub-baralhos de ${esc(p.name)}</option>`).join("")}</select>
          <p class="note">No automático, cada baralho do topo é uma matéria. Se houver um só baralho no topo, os sub-baralhos dele viram as matérias.</p>
          <p class="note">Matérias agora: ${d.matters.length ? d.matters.map(esc).join(", ") : "nenhuma"}.</p>
        </div></section>
      <div class="actions" style="margin-top:22px"><button class="btn primary" data-act="save-settings">Salvar meta e matérias</button></div>
      <section class="section"><div class="section-head"><h2>Sons e animações</h2><span class="muted">valem na hora</span></div>
        <label class="switch"><input type="checkbox" data-fx="sound" ${d.fx.sound ? "checked" : ""}><span>Sons</span></label>
        <div class="field"><span>Volume</span><div class="inline"><input type="range" min="0" max="100" step="5" value="${Math.round(d.fx.volume * 100)}" data-fx="volume" aria-label="Volume"><button class="btn quiet" data-act="fx-test">Ouvir um exemplo</button></div></div>
        <label class="switch"><input type="checkbox" data-fx="motion" ${d.fx.motion ? "checked" : ""}><span>Animações</span></label>
        <p class="note">Se o Windows estiver com as animações desligadas (Acessibilidade, Efeitos visuais), as do painel também ficam.</p>
      </section>
      ${mobileSection(d.mobile)}
      <section class="section"><div class="section-head"><h2>Anki</h2></div>
        <div class="actions" style="margin-top:14px"><button class="btn" data-open="prefs">Preferências do Anki</button><button class="btn" data-open="profiles">Trocar de perfil</button></div></section>
      <section class="section"><div class="section-head"><h2>Interface</h2></div>
        <p class="note">A interface normal do Anki continua disponível. Para voltar ao painel, use Ferramentas, Abrir o Painel de Estudos.</p>
        <div class="actions" style="margin-top:12px"><button class="btn" data-open="anki">Usar a interface do Anki</button></div></section>
      <p class="note" style="margin-top:48px">Painel de Estudos ${esc(d.version)}, perfil ${esc(d.profile)}.</p>
    </div>`);
  }

  // The phone: C/E buttons and question letters inside the cards, for AnkiDroid.
  function mobileSection(m) {
    const types = (m && m.types) || [];
    const used = types.filter((t) => t.notes);
    const on = types.filter((t) => t.state === "on");
    const old = types.filter((t) => t.state === "old");
    const names = (list) => list.map((t) => `${esc(t.name)}${t.notes ? ` (${plural(t.notes, "nota", "notas")})` : ""}`).join(", ");
    let status;
    let buttons;
    if (!used.length && !on.length && !old.length) {
      status = "Nenhum modelo de cartão com itens Certo/Errado ou questões apareceu na coleção.";
      buttons = "";
    } else if (old.length) {
      status = `Ligado em ${names(old)}, numa versão anterior do painel.`;
      buttons = `<button class="btn primary" data-act="mobile-on">Atualizar</button><button class="btn" data-act="mobile-off">Desativar</button>`;
    } else if (on.length) {
      status = `Ligado em ${names(on)}. Chega ao celular na próxima sincronização.`;
      buttons = `<button class="btn" data-act="mobile-off">Desativar</button>`;
    } else {
      status = `Desligado. Vai no modelo ${names(used)}.`;
      buttons = `<button class="btn primary" data-act="mobile-on">Ativar no celular</button>`;
    }
    return `<section class="section"><div class="section-head"><h2>Celular (AnkiDroid)</h2><span class="muted">vale depois de sincronizar</span></div>
      <p class="note">Põe os botões C e E, e as letras das questões, dentro dos próprios cartões, para responder no AnkiDroid como aqui: errou, Continuar, que dá De novo; acertou, Difícil, Bom ou Fácil. No Anki do computador os cartões continuam iguais.</p>
      <p class="mobile-status">${status}</p>
      ${buttons ? `<div class="actions" style="margin-top:12px">${buttons}</div>` : ""}
      <p class="note">Feito para a tela de estudo padrão do AnkiDroid. Na tela de estudo nova, que ainda é experimental, o cartão mostra se você acertou, e a nota fica nos botões do próprio AnkiDroid.</p>
    </section>`;
  }

  const mobileOn = () =>
    guarded(async () => {
      const ok = await ask({
        title: "Ativar no celular?",
        msg: "O painel acrescenta um bloco de código no fim da frente e do verso do modelo de cartão desses itens. O resto do modelo não muda, e Desativar tira o bloco.",
        ok: "Ativar",
      });
      if (!ok) return;
      await api("mobile_enable");
      await go("ajustes");
      toast("Pronto. Sincronize o computador e depois o celular.");
    });

  const mobileOff = () =>
    guarded(async () => {
      await api("mobile_disable");
      await go("ajustes");
      toast("Botões tirados dos cartões. Sincronize para valer no celular.");
    });

  const saveSettings = () =>
    guarded(async () => {
      const value = Number(document.getElementById("goal-value").value);
      if (!value || value < 1) return toast("A meta precisa ser um número maior que zero.", { error: true });
      const unit = document.getElementById("goal-unit").value;
      const root = document.getElementById("root").value;
      await api("save_settings", { goal: { value, unit }, root: root ? Number(root) : null });
      await go("ajustes");
      toast("Ajustes salvos.");
    });

  // ---------------------------------------------------------------- events
  const ACTIONS = {
    study: (t) => startStudy(t.dataset.did ? Number(t.dataset.did) : null),
    end: () => endStudy(),
    reveal: () => reveal(),
    choose: (t) => choose(t.dataset.choice),
    rate: (t) => rate(Number(t.dataset.r)),
    edit: () => api("edit").catch(() => {}),
    bury: () => cardAction("bury"),
    suspend: () => cardAction("suspend"),
    undo: () => cardAction("undo"),
    replay: () => api("replay").catch(() => {}),
    reason: (t) => setReason(t.dataset.code),
    "mobile-on": () => mobileOn(),
    "mobile-off": () => mobileOff(),
    "edit-card": (t) => api("edit", { cid: Number(t.dataset.cid) }).catch(() => {}),
    "err-days": (t) => go("erros", { days: Number(t.dataset.days) }),
    "err-redo": (t) => studyErrors(Number(t.dataset.days), t.dataset.did ? Number(t.dataset.did) : null),
    "err-open": (t) => toggleErr(t),
    "save-settings": () => saveSettings(),
    "toggle-sound": () =>
      setFx({ sound: !S.fx.sound })
        .then(() => S.fx.sound && play("right"))
        .catch(() => {}),
    "fx-test": () => play("reveal"),
    "dlg-close": (t) => closeOverlay(topOverlay(t)),
    "ask-ok": (t) => {
      const el = topOverlay(t);
      const resolve = el._resolve;
      el._resolve = null;
      closeOverlay(el);
      if (resolve) resolve(true);
    },
    // roleta
    "ro-spin": () => roSpin(),
    "ro-again": (t) => {
      const tid = t.dataset.tid;
      closeAllOverlays();
      roSpin({ again: tid });
    },
    "ro-sel": (t) => {
      const cat = roCat();
      if (cat) roCall("roleta_select", { cat: cat.id, sel: t.dataset.sel }).catch(() => {});
    },
    "ro-tab": (t) => {
      S.roTab = t.dataset.tab;
      refreshRoleta();
    },
    "ro-filter": (t) => {
      S.roFilter = t.dataset.f;
      renderPanel();
    },
    "ro-detail": (t) => openTopicDialog(t.dataset.tid, "detail"),
    // Estudar on a drawn topic: the panel makes the topic's deck (Matéria::Subcategoria::Tópico)
    "ro-accept": (t) => {
      const tid = t.dataset.tid;
      closeOverlay(topOverlay(t));
      roCall("roleta_topic_deck", { tid })
        .then((res) => {
          const d = res.topic_deck;
          toast(`${d.created ? "Baralho criado" : "Baralho do tópico"}: ${d.path}`, { action: { label: "Adicionar cartões", fn: () => openAnki("add", d.did) } });
        })
        .catch(() => {});
    },
    "deck-rename": (t) => renameDeck(Number(t.dataset.did), t.dataset.name),
    "deck-delete": (t) => deleteDeck(t),
    "ask-name-ok": (t) => {
      const el = topOverlay(t);
      if (el && el._submit) el._submit();
    },
    "ro-study-topic": (t) => studyTopic(t.dataset.tid),
    "tc-pick": (t) => loadTopicCards(topOverlay(t), { picker: true }),
    "tc-cancel": (t) => renderTopicCards(topOverlay(t)),
    "tc-tag": (t) => {
      const el = topOverlay(t);
      const select = el.querySelector("#tc-tag");
      if (select && select.value) linkTopic(el, { tag: select.value });
    },
    "tc-use": (t) => linkTopic(topOverlay(t), { tag: t.dataset.tag }),
    "tc-law": (t) => {
      const el = topOverlay(t);
      const select = el.querySelector("#tc-law");
      if (select && select.value) linkTopic(el, { law: select.value });
    },
    "tc-auto": (t) => linkTopic(topOverlay(t), null),
    "ro-toggle": (t) =>
      roCall("roleta_toggle", { tid: t.dataset.tid })
        .then((res) => {
          play(res.seen ? "mark" : "undo");
          if (S.view !== "roleta") rerender();
        })
        .catch(() => {}),
    "ro-toggle-dlg": (t) => {
      const tid = t.dataset.tid;
      closeOverlay(topOverlay(t));
      roCall("roleta_toggle", { tid }).catch(() => {});
    },
    "ro-unsee": (t) => roCall("roleta_unsee", { tid: t.dataset.tid }, { undo: true }).catch(() => {}),
    "ro-remove": (t) => roCall("roleta_remove", { tid: t.dataset.tid }, { undo: true }).catch(() => {}),
    "ro-remove-dlg": (t) => {
      const tid = t.dataset.tid;
      closeOverlay(topOverlay(t));
      roCall("roleta_remove", { tid }, { undo: true }).catch(() => {});
    },
    "ro-add": () => roAdd(),
    "ro-reset": async () => {
      const cat = roCat();
      if (!cat) return;
      const n = countSeen(itemsOf(scopeOf(cat).subs));
      const ok = await ask({ title: "Reiniciar o ciclo?", msg: `${plural(n, "tópico visto", "tópicos vistos")} em ${scopeName(cat)} ${n === 1 ? "volta" : "voltam"} ao sorteio.`, ok: "Reiniciar" });
      if (!ok) return;
      await roCall("roleta_reset", { cat: cat.id }).catch(() => {});
      play("reset");
      toast("Ciclo reiniciado.", { action: { label: "Desfazer", fn: roUndo } });
    },
    "ro-open": (t) => roCall("roleta_select", { cat: t.dataset.cat }, { refresh: false }).then(() => go("roleta")).catch(() => {}),
    "ro-import": () => openImport(),
    "ro-do-import": () => doImport(document.getElementById("ro-paste").value),
    "ro-file": async () => {
      const res = await api("roleta_file").catch(() => null);
      if (!res || res.cancel) return;
      document.getElementById("ro-paste").value = res.text;
      doImport(res.text);
    },
    "ro-save-backup": async () => {
      const res = await api("roleta_save_backup").catch(() => null);
      if (res && res.saved) toast("Backup salvo.");
    },
    "ro-copy": async (t) => {
      await api("roleta_copy", { what: t.dataset.what }).catch(() => {});
      toast(t.dataset.what === "backup" ? "Backup copiado para a área de transferência." : "Tópicos copiados no formato de importação.");
    },
    "ro-clear": async () => {
      const st = roState();
      const n = st ? st.cats.length : 0;
      if (!n) return;
      const ok = await ask({ title: "Apagar tudo?", msg: `Isso remove ${plural(n, "matéria", "matérias")} com todos os tópicos, anotações e o progresso da Roleta. Dá para desfazer logo em seguida.`, ok: "Apagar tudo", danger: true });
      if (!ok) return;
      await roCall("roleta_clear", {}, { refresh: false }).catch(() => {});
      closeAllOverlays();
      renderRoleta();
      toast("Roleta apagada.", { action: { label: "Desfazer", fn: roUndo } });
    },
    "ro-org": () => openOrganizer("edit"),
    "ro-new": () => openOrganizer("new"),
    "org-add-sub": (t) => {
      const el = topOverlay(t);
      el._org.subs.push({ id: null, name: "", n: 0 });
      renderOrgSubs(el);
      const inputs = el.querySelectorAll("[data-org-sub]");
      if (inputs.length) inputs[inputs.length - 1].focus();
    },
    "org-del-sub": (t) => {
      const el = topOverlay(t);
      el._org.subs[Number(t.dataset.i)].del = true;
      renderOrgSubs(el);
    },
    "org-save": (t) => saveOrganizer(topOverlay(t)),
    "org-delete": async (t) => {
      const el = topOverlay(t);
      const cat = findCatById(el._org.cat);
      if (!cat) return;
      const n = itemsOf(cat.subs).length;
      const ok = await ask({ title: "Excluir a matéria?", msg: `${cat.name} sai da Roleta com ${plural(n, "tópico", "tópicos")}. Dá para desfazer logo em seguida.`, ok: "Excluir", danger: true });
      if (!ok) return;
      await roCall("roleta_delete_cat", { cat: cat.id }, { refresh: false }).catch(() => {});
      closeAllOverlays();
      renderRoleta();
      toast("Matéria excluída.", { action: { label: "Desfazer", fn: roUndo } });
    },
  };

  function findCatById(id) {
    const st = roState();
    return st ? st.cats.find((c) => c.id === id) : null;
  }

  async function roAdd() {
    const cat = roCat();
    const input = document.getElementById("ro-add-input");
    if (!cat || !input || !input.value.trim()) return input && input.focus();
    const subSel = document.getElementById("ro-add-sub");
    const args = { cat: cat.id, name: input.value };
    if (subSel) args.sub = subSel.value;
    try {
      await roCall("roleta_add", args);
    } catch (err) {
      return;
    }
    if (S.roFilter === "seen") S.roFilter = "all";
    renderPanel();
    const again = document.getElementById("ro-add-input");
    if (again) again.focus();
  }

  document.addEventListener("click", (ev) => {
    const target = ev.target.closest("[data-act],[data-open],[data-go]");
    if (!target || target.disabled) return;
    if (target.dataset.act) {
      const action = ACTIONS[target.dataset.act];
      if (action) action(target, ev);
    } else if (target.dataset.open) {
      openAnki(target.dataset.open, target.dataset.did ? Number(target.dataset.did) : null);
    } else if (target.dataset.go) {
      const args = {};
      if (target.dataset.did) args.did = Number(target.dataset.did);
      if (target.dataset.spin) args.spin = true;
      go(target.dataset.go, args);
    }
  });

  document.addEventListener("change", (ev) => {
    const t = ev.target;
    if (t.matches("[data-ro-cat]")) {
      roCall("roleta_select", { cat: t.value }).catch(() => {});
    } else if (t.matches("[data-rename]")) {
      const tid = t.dataset.rename;
      roCall("roleta_rename", { tid, name: t.value }, { refresh: false })
        .then(() => {
          const f = findTopic(tid);
          if (f) t.title = f.topic.t;
          drawWheel();
        })
        .catch(() => {
          const f = findTopic(tid);
          if (f) t.value = f.topic.t;
        });
    } else if (t.matches("[data-fx]")) {
      const key = t.dataset.fx;
      const value = key === "volume" ? Number(t.value) / 100 : t.checked;
      setFx({ [key]: value })
        .then(() => {
          if (key === "volume" || (key === "sound" && value)) play("reveal");
        })
        .catch(() => {});
    }
  });

  document.addEventListener("input", (ev) => {
    const t = ev.target;
    if (t.matches("[data-note]")) queueNote(t.dataset.note, t.value);
    else if (t.id === "ro-search") {
      S.roQuery = t.value;
      renderPanel();
    } else if (t.matches("[data-org-sub]")) {
      const el = topOverlay(t);
      el._org.subs[Number(t.dataset.orgSub)].name = t.value;
    }
  });

  document.addEventListener("keydown", (ev) => {
    const target = ev.target;
    const tag = (target.tagName || "").toLowerCase();
    const typing = ["input", "textarea", "select"].includes(tag);
    const k = (ev.key || "").toLowerCase();
    if (overlays.length) {
      if (k === "escape") {
        ev.preventDefault();
        closeOverlay();
      } else if (k === "enter" && target.id === "org-name") {
        ev.preventDefault();
        saveOrganizer(topOverlay(target));
      } else if (k === "enter" && target.id === "ask-name") {
        ev.preventDefault();
        const el = topOverlay(target);
        if (el && el._submit) el._submit();
      } else if (k === "enter" && (ev.ctrlKey || ev.metaKey) && target.id === "ro-paste") {
        ev.preventDefault();
        doImport(target.value);
      }
      return;
    }
    if (S.view === "roleta") {
      if (k === "enter" && target.id === "ro-add-input") {
        ev.preventDefault();
        roAdd();
      } else if (k === "enter" && target.matches && target.matches("[data-rename]")) {
        ev.preventDefault();
        target.blur();
      } else if ((k === " " || k === "enter") && !typing && tag !== "button" && !ev.repeat && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        ev.preventDefault();
        roSpin();
      }
      return;
    }
    if (typing) return;
    if (S.view !== "study" || !S.card) return;
    if ((ev.ctrlKey || ev.metaKey) && k === "z") {
      ev.preventDefault();
      return cardAction("undo");
    }
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (tag === "button" && (k === " " || k === "enter")) return; // the focused button handles it
    if (k === "escape") return endStudy();
    if (k === "r" && S.card.audio) return api("replay").catch(() => {});
    const c = S.card;
    const go3 = k === " " || k === "enter";
    if (S.phase === "question") {
      if (c.mode === "ce" && (k === "c" || k === "e")) {
        ev.preventDefault();
        return choose(k === "c" ? "CERTO" : "ERRADO");
      }
      if (c.mode === "mc" && c.options.some((o) => o.letter.toLowerCase() === k)) {
        ev.preventDefault();
        return choose(k.toUpperCase());
      }
      if (c.mode === "basic" && go3) {
        ev.preventDefault();
        return reveal();
      }
    } else if (S.phase === "answer") {
      if (["1", "2", "3", "4"].includes(k)) return rate(Number(k));
      if (go3) {
        ev.preventDefault();
        return rate(3);
      }
    } else if (S.phase === "result") {
      if (S.result.right) {
        if (["2", "3", "4"].includes(k)) return rate(Number(k));
        if (go3) {
          ev.preventDefault();
          return rate(3);
        }
      } else {
        const reason = REASONS.find((r) => r[2] === k);
        if (reason) {
          ev.preventDefault();
          return setReason(reason[0]);
        }
        if (go3 || k === "1") {
          ev.preventDefault();
          return rate(1);
        }
      }
    }
  });

  // Messages from Python (theme, sync, changes made in Anki's own windows).
  window.PE = {
    event(e) {
      if (e.type === "theme") {
        document.documentElement.classList.toggle("night-mode", !!e.night);
        clearTextCaches();
        rerender();
      } else if (e.type === "sync") {
        S.syncing = e.state === "start";
        const button = document.querySelector('[data-open="sync"]');
        if (button) button.textContent = S.syncing ? "Sincronizando…" : "Sincronizar";
        if (!S.syncing && S.view !== "study") rerender();
      } else if (e.type === "changed") {
        S.roCounts = null;
        if (S.view === "study") {
          if (e.note_text) rerender();
        } else if (S.view !== "done" && S.view !== "roleta") rerender();
      } else if (e.type === "refresh") {
        if (S.view !== "study") rerender();
      }
    },
    go,
    state: () => ({ view: S.view, phase: S.phase, mode: S.card && S.card.mode, spinning: !!WHEEL.spin, overlays: overlays.length, reason: S.reason, deck: S.card && S.card.deck }),
    topic: (tid) => openTopicDialog(tid, "detail"),
    renderSound,
    sounds: () => Object.keys(SOUNDS),
  };

  async function boot() {
    try {
      const b = await api("boot");
      S.base = b.base;
      S.fx = b.fx || S.fx;
      S.reduceMotion = !!b.reduce_motion;
      document.documentElement.classList.toggle("night-mode", !!b.night);
    } catch (err) {
      /* shown already */
    }
    applyFx();
    go("home");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
