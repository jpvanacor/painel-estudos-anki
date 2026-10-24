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
  };

  // ---------------------------------------------------------------- helpers
  const appEl = () => document.getElementById("app");
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const pct = (x) => (x == null ? "sem dados" : `${Math.round(x * 100)}%`);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
  const round = (n) => Math.round(Number(n) || 0);

  function api(m, a = {}) {
    return new Promise((resolve, reject) => {
      const send = () => {
        if (typeof window.pycmd !== "function") return setTimeout(send, 25);
        window.pycmd("pe:" + JSON.stringify({ m, a }), (res) => {
          if (res && res.error) {
            toast(res.error, true);
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
  function toast(message, error = false) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.toggle("error", error);
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), error ? 6000 : 2800);
  }

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
    // The frame is sized to its content when it loads, when its images and fonts arrive, and
    // when the window changes width. A ResizeObserver across documents loops in Chromium.
    frame._fit = () => fitFrame(frame);
    frame.addEventListener("load", () => {
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
    // a scrollbar may appear in the page and narrow the frame; settle in a few frames at most
    if (tries < 3) requestAnimationFrame(() => fitFrame(frame, tries + 1));
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => document.querySelectorAll("iframe.cardframe").forEach((f) => f._fit && f._fit()), 120);
  });

  // ---------------------------------------------------------------- frame and navigation
  const NAV = [
    ["home", "Hoje"],
    ["materias", "Matérias"],
    ["edital", "Edital"],
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
    edital: viewEdital,
    ajustes: viewAjustes,
  };

  async function go(view, args = {}) {
    if (!VIEWS[view]) view = "home";
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
      out += `<span class="bubble ${fill >= 1 ? "full" : fill > 0 ? "part" : ""}" style="--p:${fill.toFixed(3)}"></span>`;
    }
    return out;
  }

  function unitWord(unit, n) {
    return unit === "cards" ? (n === 1 ? "cartão" : "cartões") : n === 1 ? "minuto" : "minutos";
  }

  function scopeText(scope) {
    if (!scope) return "todas as matérias";
    return scope.group ? `${scope.materia} › ${scope.group}` : scope.materia;
  }

  function scopeSelect(draw) {
    const current = draw.scope ? JSON.stringify(draw.scope) : "";
    const option = (value, label) =>
      `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;
    const options = [option("", "Todas as matérias")];
    for (const m of draw.scopes) {
      options.push(option(JSON.stringify({ materia: m.materia }), m.materia));
      for (const g of m.groups) options.push(option(JSON.stringify({ materia: m.materia, group: g }), `${m.materia} › ${g}`));
    }
    return `<label class="inline">Sortear de <select class="select" data-scope>${options.join("")}</select></label>`;
  }

  function drawPanel(draw) {
    if (!draw.has_edital) {
      return `<div class="empty"><p>Nenhum edital carregado.</p>
        <p class="muted">Cole na página Edital o mesmo bloco JSON que você usa na Roleta de Estudos.</p>
        <button class="btn" data-go="edital">Abrir o Edital</button></div>`;
    }
    const c = draw.current;
    let body;
    if (c) {
      body = `<p class="draw-where">${esc(c.materia)}${c.group ? " › " + esc(c.group) : ""}</p>
        <p class="draw-topic">${esc(c.name)}</p>
        <div class="actions"><button class="btn primary" data-act="topic-done">Concluí este tópico</button>
        <button class="btn" data-act="topic-skip">Sortear outro</button></div>`;
    } else if (draw.counts.left > 0) {
      body = `<p class="draw-empty muted">Nenhum tópico sorteado agora. Restam ${draw.counts.left} de ${draw.counts.total} tópicos de ${esc(scopeText(draw.scope))} neste ciclo.</p>
        <div class="actions"><button class="btn primary" data-act="draw">Sortear tópico</button></div>`;
    } else if (draw.all.left > 0) {
      body = `<p class="draw-empty">Todos os tópicos de ${esc(scopeText(draw.scope))} já saíram neste ciclo.</p>
        <div class="actions"><button class="btn" data-act="scope-all">Sortear de todas as matérias</button></div>`;
    } else {
      body = `<p class="draw-empty">Ciclo ${draw.cycle} completo: os ${draw.all.total} tópicos já saíram.</p>
        <div class="actions"><button class="btn primary" data-act="new-cycle">Começar o ciclo ${draw.cycle + 1}</button></div>`;
    }
    return `<div class="draw">${body}<div class="draw-foot">${scopeSelect(draw)}</div></div>`;
  }

  function topicList(materia) {
    return materia.groups
      .map(
        (g) => `${g.name ? `<div class="group-name">${esc(g.name)}</div>` : ""}<ul class="topics">${g.topics
          .map(
            (t) => `<li class="topic ${t.current ? "current" : ""}">
              <button class="topic-toggle" data-act="toggle-topic" data-tid="${esc(t.id)}" aria-pressed="${t.done}" title="${t.done ? "Desmarcar" : "Marcar como estudado neste ciclo"}"><span class="bubble ${t.done ? "full" : ""}"></span></button>
              <span class="topic-name">${esc(t.name)}${t.current ? ` <span class="muted">(sorteado)</span>` : ""}</span>
              <span class="times">${t.times ? (t.times === 1 ? "estudado 1 vez" : `estudado ${t.times} vezes`) : ""}</span>
            </li>`
          )
          .join("")}</ul>`
      )
      .join("");
  }

  function maturityBar(m, wide = false) {
    const total = Math.max(1, m.total);
    const seg = (n, cls) => (n ? `<i class="${cls}" style="width:${((n / total) * 100).toFixed(2)}%"></i>` : "");
    const title = `${m.new} novos, ${m.learning} aprendendo, ${m.young} jovens, ${m.mature} maduros, ${m.suspended} suspensos`;
    return `<span class="matbar" style="${wide ? "width:100%;height:12px;margin:0" : ""}" title="${title}">${seg(m.new, "seg-new")}${seg(m.learning, "seg-learn")}${seg(m.young, "seg-young")}${seg(m.mature, "seg-mature")}${seg(m.suspended, "seg-susp")}</span>`;
  }

  const LEGEND = `<div class="legend"><span style="--c:var(--new)">Novos</span><span style="--c:var(--learn)">Aprendendo</span><span style="--c:var(--young)">Jovens</span><span style="--c:var(--review)">Maduros, com intervalo de 21 dias ou mais</span><span style="--c:var(--form)">Suspensos</span></div>`;

  const NO_DECKS = `<div class="empty"><p>Nenhum baralho encontrado.</p><p class="muted">Importe seus cartões com Importar arquivo, no menu ao lado.</p></div>`;

  // ---------------------------------------------------------------- Hoje
  async function viewHome() {
    const d = await api("home");
    const g = d.goal;
    const left = Math.max(0, g.value - g.done);
    const notes = [];
    if (g.done >= g.value) notes.push("Meta de hoje cumprida.");
    else if (g.unit === "cards")
      notes.push(`Faltam ${plural(round(left), "cartão", "cartões")}, uns ${Math.max(1, round((left * g.avg_secs) / 60))} minutos no seu ritmo.`);
    else notes.push(`Faltam ${plural(Math.ceil(left), "minuto", "minutos")}.`);
    if (g.streak > 0) notes.push(`${plural(g.streak, "dia seguido", "dias seguidos")} batendo a meta.`);

    const plan = d.plan;
    const planHtml = plan.length
      ? `<table class="grid"><thead><tr><th>Matéria</th><th>Novos</th><th>Aprender</th><th>Revisar</th><th>Acerto em 30 dias</th><th><span class="sr-only">Estudar</span></th></tr></thead><tbody>
        ${plan
          .map(
            (r) => `<tr class="clickable" data-go="materia" data-did="${r.did}">
            <td><span class="cell-name">${esc(r.name)}</span>${r.topics ? `<div class="muted" style="font-size:13.5px">Edital: ${r.topics.done} de ${r.topics.total} tópicos neste ciclo</div>` : ""}</td>
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
        <div class="bubbles" role="img" aria-label="${round(g.done)} de ${round(g.value)} ${unitWord(g.unit, g.value)}">${goalBubbles(g)}</div>
        ${notes.map((n) => `<p class="goal-note">${esc(n)}</p>`).join("")}
      </div>
      <div class="start">${
        d.due
          ? `<button class="btn primary" data-act="study">Estudar tudo</button><span class="muted">${plural(d.due, "cartão", "cartões")} para hoje, uns ${Math.max(1, d.eta_min)} minutos. A matéria mais fraca vem primeiro.</span>`
          : `<span class="muted">Nada para revisar agora.</span>`
      }</div>
      <section class="section">
        <div class="section-head"><h2>Matérias de hoje</h2><span class="muted">da mais fraca para a mais forte</span></div>
        ${planHtml}
      </section>
      <section class="section">
        <div class="section-head"><h2>Tópico do edital</h2>${d.draw.has_edital ? `<span class="muted">Ciclo ${d.draw.cycle}: ${d.draw.all.done} de ${d.draw.all.total} tópicos estudados</span>` : ""}</div>
        ${drawPanel(d.draw)}
      </section>
    </div>`);
  }

  // ---------------------------------------------------------------- estudo
  function showStudy(res) {
    if (!res) return;
    if (res.view === "card") {
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
      </header>
      <div class="study-body" id="study-body"><div class="study-col">
        <div class="sheet" id="q"></div>
        <div id="choices">${choicesHtml()}</div>
        <div id="after"></div>
      </div></div>
      <footer class="study-bar" id="bar"></footer>
    </div>`;
    const q = document.getElementById("q");
    if (S.phase === "answer") mountFrame(q, S.answer.html, c.css);
    else mountFrame(q, c.front, c.css, c.mode === "mc" ? "pe-left" : "");
    if (S.phase === "result") renderAfter(false);
    renderBar();
    document.getElementById("study-body").focus?.();
  }

  function renderAfter(scroll = true) {
    const r = S.result;
    const after = document.getElementById("after");
    const gabarito = S.card.mode === "ce" ? (r.correct === "CERTO" ? "Certo" : "Errado") : r.correct;
    after.innerHTML = `<p class="verdict ${r.right ? "right" : "wrong"}" role="status">${r.right ? "Você acertou." : "Você errou."}<span class="muted">Gabarito: ${esc(gabarito)}</span></p><div class="sheet" id="back"></div>`;
    mountFrame(document.getElementById("back"), r.back, S.card.css);
    if (scroll) after.scrollIntoView({ block: "start" });
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
    document.getElementById("bar").innerHTML = `${tools(c)}<div class="main-actions">${hint ? `<span class="hint">${esc(hint)}</span>` : ""}${main}</div>`;
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

  const startStudy = (did) => guarded(async () => showStudy(await api("start", did ? { did } : {})));

  const choose = (choice) =>
    guarded(async () => {
      if (S.view !== "study" || S.phase !== "question") return;
      const res = await api("choose", { choice });
      S.phase = "result";
      S.result = res;
      markChoices(res);
      renderAfter();
      renderBar();
    });

  const reveal = () =>
    guarded(async () => {
      if (S.view !== "study" || S.phase !== "question" || S.card.mode !== "basic") return;
      S.answer = await api("reveal");
      S.phase = "answer";
      const q = document.getElementById("q");
      q.innerHTML = "";
      mountFrame(q, S.answer.html, S.card.css);
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
      showStudy(await api("answer", { rating }));
    });

  const cardAction = (method) => guarded(async () => showStudy(await api(method)));

  const endStudy = () =>
    guarded(async () => {
      await api("stop");
      await go("home");
    });

  function renderDone(d) {
    S.view = "done";
    S.card = null;
    const headline = d.deck ? `Tudo em dia em ${d.deck}.` : "Tudo em dia por hoje.";
    const s = d.session;
    const goalText =
      s.goal_done >= s.goal_value
        ? `Meta de hoje cumprida: ${round(s.goal_done)} de ${round(s.goal_value)} ${unitWord(s.goal_unit, s.goal_value)}.`
        : `Meta de hoje: ${round(s.goal_done)} de ${round(s.goal_value)} ${unitWord(s.goal_unit, s.goal_value)}.`;
    page(`<div class="page done">
      <h1>${esc(headline)}</h1>
      <p class="lede">${
        d.answered
          ? `${plural(d.answered, "cartão", "cartões")} nesta sessão, ${d.right} certos (${pct(d.right / d.answered)}), em ${plural(Math.max(1, d.minutes), "minuto", "minutos")}.`
          : "Não havia cartões para estudar."
      }</p>
      ${d.results && d.results.length ? `<div class="bubbles" role="img" aria-label="Respostas da sessão, em ordem: preenchida é certa, vermelha é errada">${d.results.map((ok) => `<span class="bubble ${ok ? "right" : "wrong"}"></span>`).join("")}</div>` : ""}
      <p class="goal-note">${esc(goalText)}</p>
      <div class="actions" style="margin-top:28px"><button class="btn primary" data-go="home">Voltar para Hoje</button><button class="btn" data-go="materias">Ver as matérias</button></div>
    </div>`);
  }

  // ---------------------------------------------------------------- matérias
  async function viewMaterias() {
    const d = await api("materias");
    const table = d.rows.length
      ? `<table class="grid"><thead><tr><th>Matéria</th><th>Hoje</th><th>Cartões</th><th>Estágio dos cartões</th><th>Acerto em 30 dias</th></tr></thead><tbody>
        ${d.rows
          .map(
            (r) => `<tr class="clickable" data-go="materia" data-did="${r.did}">
            <td><span class="cell-name">${esc(r.name)}</span>${r.topics ? `<div class="muted" style="font-size:13.5px">Edital: ${r.topics.done} de ${r.topics.total} tópicos neste ciclo</div>` : ""}</td>
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
      </div>
      <section class="section"><div class="section-head"><h2>Acerto</h2></div><p style="margin:12px 0 0">${esc(accText)}</p></section>
      <section class="section"><div class="section-head"><h2>Cartões</h2><span class="muted">${plural(d.maturity.total, "cartão", "cartões")}</span></div>
        <div style="margin-top:14px">${maturityBar(d.maturity, true)}</div>${LEGEND}</section>
      <section class="section"><div class="section-head"><h2>Temas</h2><span class="muted">do mais fraco para o mais forte, pelas etiquetas, nos últimos 90 dias</span></div>${weak}</section>
      ${d.edital ? `<section class="section"><div class="section-head"><h2>Edital</h2><span class="muted">${d.edital.counts.done} de ${d.edital.counts.total} tópicos neste ciclo</span></div>${topicList(d.edital)}</section>` : ""}
    </div>`);
  }

  // ---------------------------------------------------------------- edital
  async function viewEdital() {
    const d = await api("edital");
    const has = d.materias.length > 0;
    const block = (m) => {
      const options = [`<option value="">Nenhum baralho</option>`]
        .concat(d.decks.map((dk) => `<option value="${dk.id}" ${dk.id === m.deck ? "selected" : ""}>${esc(dk.name)}</option>`))
        .join("");
      return `<section class="materia-block">
        <div class="materia-head"><h2>${esc(m.name)}</h2><span class="progress-text">${m.counts.done} de ${m.counts.total} neste ciclo</span>
        <label>Baralho <select class="select" data-link="${esc(m.name)}">${options}</select></label></div>
        ${topicList(m)}</section>`;
    };
    page(`<div class="page"><h1>Edital</h1>
      <p class="lede">Cole o mesmo bloco JSON que você usa na Roleta de Estudos. Cada tópico sorteado sai da roleta até todos saírem; aí começa um novo ciclo.</p>
      ${has ? `<section class="section" style="margin-top:0"><div class="section-head"><h2>Sorteio</h2><span class="muted">Ciclo ${d.draw.cycle}: ${d.draw.all.done} de ${d.draw.all.total} tópicos estudados</span></div>${drawPanel(d.draw)}</section>` : ""}
      <section class="section"><div class="section-head"><h2>${has ? "Adicionar tópicos" : "Carregar o edital"}</h2></div>
        <textarea class="paste" id="paste" spellcheck="false" aria-label="Bloco JSON do edital" placeholder='{"Direito Constitucional": ["Princípios fundamentais (Arts. 1º a 4º)", "Direitos sociais (Arts. 6º a 11)"]}'></textarea>
        <div class="actions" style="margin-top:12px"><button class="btn primary" data-act="import">Importar tópicos</button>
        <span class="note" id="import-note" style="margin:0">Tópicos que já estão no edital mantêm o que você marcou.</span></div>
      </section>
      ${d.materias.map(block).join("")}
      ${has ? `<section class="section"><button class="btn danger" data-act="clear-edital">Apagar o edital</button></section>` : ""}
    </div>`);
  }

  const importEdital = () =>
    guarded(async () => {
      const text = document.getElementById("paste").value;
      if (!text.trim()) return toast("Cole o bloco JSON antes de importar.", true);
      const res = await api("edital_import", { text });
      await go("edital");
      const note = document.getElementById("import-note");
      if (note) {
        note.textContent = res.added
          ? `${plural(res.added, "tópico novo entrou", "tópicos novos entraram")} no edital.`
          : "Nenhum tópico novo: todos já estavam no edital.";
        note.classList.add("ok");
      }
    });

  const drawAction = (method, args = {}) => guarded(async () => {
    await api(method, args);
    await rerender();
  });

  function confirmThen(button, label, fn) {
    if (button.dataset.armed) {
      delete button.dataset.armed;
      return fn();
    }
    const original = button.textContent;
    button.dataset.armed = "1";
    button.textContent = label;
    setTimeout(() => {
      if (button.isConnected && button.dataset.armed) {
        delete button.dataset.armed;
        button.textContent = original;
      }
    }, 4000);
  }

  // ---------------------------------------------------------------- ajustes
  async function viewAjustes() {
    const d = await api("settings");
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
      <div class="actions" style="margin-top:22px"><button class="btn primary" data-act="save-settings">Salvar ajustes</button></div>
      <section class="section"><div class="section-head"><h2>Anki</h2></div>
        <div class="actions" style="margin-top:14px"><button class="btn" data-open="prefs">Preferências do Anki</button><button class="btn" data-open="profiles">Trocar de perfil</button></div></section>
      <section class="section"><div class="section-head"><h2>Interface</h2></div>
        <p class="note">A interface normal do Anki continua disponível. Para voltar ao painel, use Ferramentas, Abrir o Painel de Estudos.</p>
        <div class="actions" style="margin-top:12px"><button class="btn" data-open="anki">Usar a interface do Anki</button></div></section>
      <p class="note" style="margin-top:48px">Painel de Estudos ${esc(d.version)}, perfil ${esc(d.profile)}.</p>
    </div>`);
  }

  const saveSettings = () =>
    guarded(async () => {
      const value = Number(document.getElementById("goal-value").value);
      if (!value || value < 1) return toast("A meta precisa ser um número maior que zero.", true);
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
    "topic-done": () => drawAction("topic_done"),
    "topic-skip": () => drawAction("topic_skip"),
    draw: () => drawAction("draw", { scope: currentScope() }),
    "scope-all": () => drawAction("draw", { scope: null }),
    "new-cycle": () => drawAction("new_cycle"),
    "toggle-topic": (t) => drawAction("topic_toggle", { tid: t.dataset.tid }),
    import: () => importEdital(),
    "clear-edital": (t) => confirmThen(t, "Clique de novo para apagar o edital", () => drawAction("edital_clear")),
    "save-settings": () => saveSettings(),
  };

  function currentScope() {
    const select = document.querySelector("[data-scope]");
    return select && select.value ? JSON.parse(select.value) : null;
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
      go(target.dataset.go, target.dataset.did ? { did: Number(target.dataset.did) } : {});
    }
  });

  document.addEventListener("change", (ev) => {
    const t = ev.target;
    if (t.matches("[data-scope]")) {
      api("set_scope", { scope: t.value ? JSON.parse(t.value) : null })
        .then(() => rerender())
        .catch(() => {});
    } else if (t.matches("[data-link]")) {
      api("edital_link", { materia: t.dataset.link, did: t.value ? Number(t.value) : null })
        .then(() => toast("Vínculo salvo."))
        .catch(() => {});
    }
  });

  document.addEventListener("keydown", (ev) => {
    const tag = (ev.target.tagName || "").toLowerCase();
    if (["input", "textarea", "select"].includes(tag)) return;
    if (S.view !== "study" || !S.card) return;
    const k = ev.key.toLowerCase();
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
      } else if (go3 || k === "1") {
        ev.preventDefault();
        return rate(1);
      }
    }
  });

  // Messages from Python (theme, sync, changes made in Anki's own windows).
  window.PE = {
    event(e) {
      if (e.type === "theme") {
        document.documentElement.classList.toggle("night-mode", !!e.night);
        rerender();
      } else if (e.type === "sync") {
        S.syncing = e.state === "start";
        const button = document.querySelector('[data-open="sync"]');
        if (button) button.textContent = S.syncing ? "Sincronizando…" : "Sincronizar";
        if (!S.syncing && S.view !== "study") rerender();
      } else if (e.type === "changed") {
        if (S.view === "study") {
          if (e.note_text) rerender();
        } else if (S.view !== "done") rerender();
      } else if (e.type === "refresh") {
        if (S.view !== "study") rerender();
      }
    },
    go,
    state: () => ({ view: S.view, phase: S.phase, mode: S.card && S.card.mode }),
  };

  async function boot() {
    try {
      const b = await api("boot");
      S.base = b.base;
      document.documentElement.classList.toggle("night-mode", !!b.night);
    } catch (err) {
      /* shown already */
    }
    go("home");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
