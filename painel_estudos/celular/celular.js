/* Painel de Estudos no celular: os botões C/E, as letras das questões e o Modo voz, dentro do
 * próprio cartão.
 *
 * Vai no modelo de cartão (frente e verso) quando o painel ativa "Celular" em Ajustes, e só age no
 * AnkiDroid. No Anki do computador e dentro do painel o cartão continua como está.
 *
 * Na frente, tocar numa opção guarda a escolha (sessionStorage, que o AnkiDroid mantém entre a
 * frente e o verso) e vira o cartão. No verso, o script compara a escolha com o gabarito, marca as
 * opções, risca a troca dos itens ERRADO e mostra as notas: errou, só Continuar (De novo); acertou,
 * Difícil, Bom ou Fácil. A nota é dada pelos sinais da tela de estudo do AnkiDroid
 * (buttonAnswerEase1 a 4). A tela de estudo nova do AnkiDroid ainda não aceita esses sinais, então
 * nela o verso mostra o resultado e a nota fica nos botões do próprio AnkiDroid.
 *
 * Modo voz: o cartão é lido em voz alta (ankiTtsSpeak, da API de JavaScript do AnkiDroid) e a
 * resposta é ouvida (ankiSttStart; o que foi dito volta por window.ankiSttResult). Fica ligado
 * durante a sessão de estudo (sessionStorage), cartão após cartão, até dizer "parar" ou tocar em
 * Parar. Só na tela de estudo padrão, a que aceita a nota dada pelo cartão.
 *
 * Este arquivo não pode ter chaves duplas seguidas: o Anki leria como campo do modelo.
 */
(function () {
  "use strict";
  var root = document.documentElement;

  // AnkiDroid's js-api.js declares AnkiDroidJS as a class at the top level of a script: a global
  // name, but not a property of window.
  function apiClass() {
    if (typeof AnkiDroidJS === "function") return AnkiDroidJS; // eslint-disable-line no-undef
    return typeof window.AnkiDroidJS === "function" ? window.AnkiDroidJS : null;
  }

  // AnkiDroid's card page marks <html> with "android" and defines showAnswer(); both study screens do.
  var onAndroid = (root.classList.contains("android") || !!apiClass()) && typeof window.showAnswer === "function";
  if (!onAndroid) return;

  var KEY = "painelEstudosEscolha";
  var DEV = "https://github.com/jpvanacor/painel-estudos-anki";
  var MAX_AGE = 30 * 60 * 1000;
  var CE_RE = /\(\s*\)\s*Certo[\s ]*\(\s*\)\s*Errado/i;
  var CE_ANS_RE = /^[\W_]*(?:gabarito\s*[:\-]?\s*)?(certo|errado)\b/i;
  var MC_ANS_RE = /gabarito\s*[:\-]?\s*(?:letra\s+)?\(?([A-E])\)?(?![\w])/i;
  var ALT_RE = /^\s*\(?([A-E])\s*\)/;
  var TRAP_RE = /🔁️?\s*([^\n]+?)\s*(?:→|->|⟶)\s*([^\n]+)/;
  var SKIP = { SCRIPT: 1, STYLE: 1, TEMPLATE: 1, NOSCRIPT: 1, BUTTON: 1 };
  var BLOCKS = { DIV: 1, P: 1, LI: 1, UL: 1, OL: 1, TR: 1, TABLE: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, HR: 1, BLOCKQUOTE: 1 };

  function newScreen() {
    return !!(window.ankidroid && typeof window.ankidroid.waitForZoomReset === "function");
  }

  // ------------------------------------------------------------ reading the card
  function skipped(node, scope) {
    for (var p = node.parentNode; p && p !== scope; p = p.parentNode) {
      if (SKIP[p.nodeName] || (p.classList && p.classList.contains("pe-ui"))) return true;
    }
    return false;
  }

  function side(node, mark) {
    if (!mark) return "front";
    return mark.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_PRECEDING ? "front" : "back";
  }

  // Text nodes of one side of the card (all of it on the question side).
  function textNodes(which, mark) {
    var out = [];
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    while (walker.nextNode()) {
      var n = walker.currentNode;
      if (!skipped(n, document.body) && side(n, mark) === which) out.push(n);
    }
    return out;
  }

  // Text of one side with line breaks where <br> and blocks are, for finding the alternatives and
  // for the voice. blanks: a cloze still hidden ("[...]" or "[dica]") is said as "lacuna".
  function linesOf(which, mark, blanks) {
    var text = "";
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null);
    while (walker.nextNode()) {
      var n = walker.currentNode;
      if (skipped(n, document.body) || side(n, mark) !== which) continue;
      if (n.nodeType === 3) {
        var p = n.parentNode;
        text += blanks && p && p.closest && p.closest(".cloze") ? blank(n.nodeValue) : n.nodeValue;
      } else if (n.nodeName === "BR" || BLOCKS[n.nodeName]) text += "\n";
    }
    return text.split("\n");
  }

  function blank(s) {
    var h = squash(s).replace(/^\[|\]$/g, "");
    return h && h !== "..." && h !== "…" ? " lacuna (dica: " + h + ") " : " lacuna ";
  }

  function joined(nodes) {
    var s = "";
    for (var i = 0; i < nodes.length; i++) s += nodes[i].nodeValue;
    return s;
  }

  function squash(s) {
    return String(s || "").replace(/[\s ]+/g, " ").trim();
  }

  // Lines to sentences for the voice: a pause between lines, never two stops in a row. In a
  // question, "A) texto" is said "Letra A: texto".
  function speechOf(lines, mc) {
    var s = "";
    for (var i = 0; i < lines.length; i++) {
      var l = squash(lines[i]);
      var m = mc ? ALT_RE.exec(l) : null;
      if (m) l = "Letra " + m[1].toUpperCase() + ": " + squash(l.slice(m[0].length));
      s = joinSpeech(s, l);
    }
    return s;
  }

  function joinSpeech(a, b) {
    a = squash(a);
    b = squash(b);
    if (!a || !b) return a || b;
    return a + (/[.!?:;…,]$/.test(a) ? " " : ". ") + b;
  }

  // The same statement gives the same key on the front and on the back.
  function keyOf(frontText) {
    var s = squash(frontText.replace(CE_RE, ""));
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return s.length + ":" + (h >>> 0).toString(36);
  }

  function lettersOf(lines) {
    var found = [];
    for (var i = 0; i < lines.length; i++) {
      var m = ALT_RE.exec(lines[i]);
      if (m) found.push(m[1].toUpperCase());
    }
    var run = [];
    for (var j = 0; j < found.length; j++) {
      var want = "ABCDE".charAt(run.length);
      if (found[j] === want) run.push(found[j]);
      else if (found[j] === "A") run = ["A"];
    }
    return run.length >= 2 ? run : null;
  }

  // Index in the joined text -> [node, offset], for building a Range.
  function point(nodes, index, isEnd) {
    var start = 0;
    for (var i = 0; i < nodes.length; i++) {
      var len = nodes[i].nodeValue.length;
      if (isEnd ? index <= start + len : index < start + len) return [nodes[i], index - start];
      start += len;
    }
    var last = nodes[nodes.length - 1];
    return [last, last.nodeValue.length];
  }

  function rangeOf(nodes, from, to) {
    var r = document.createRange();
    var a = point(nodes, from, false);
    var b = point(nodes, to, true);
    r.setStart(a[0], a[1]);
    r.setEnd(b[0], b[1]);
    return r;
  }

  // ------------------------------------------------------------ the choice, kept between sides
  function save(rec) {
    var s = JSON.stringify(rec);
    try {
      window.sessionStorage.setItem(KEY, s);
    } catch (e) {
      /* no storage */
    }
    try {
      window.name = KEY + ":" + s;
    } catch (e) {
      /* no window name */
    }
  }

  function take() {
    var s = null;
    try {
      s = window.sessionStorage.getItem(KEY);
      window.sessionStorage.removeItem(KEY);
    } catch (e) {
      /* no storage */
    }
    try {
      var w = String(window.name || "");
      if (w.indexOf(KEY + ":") === 0) {
        if (!s) s = w.slice(KEY.length + 1);
        window.name = "";
      }
    } catch (e) {
      /* no window name */
    }
    try {
      return s ? JSON.parse(s) : null;
    } catch (e) {
      return null;
    }
  }

  function getItem(key) {
    try {
      return window.sessionStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function setItem(key, value) {
    try {
      if (value == null) window.sessionStorage.removeItem(key);
      else window.sessionStorage.setItem(key, String(value));
    } catch (e) {
      /* no storage: voice mode lasts one card */
    }
  }

  // ------------------------------------------------------------ talking to AnkiDroid
  var API = null;
  function api() {
    if (API) return API;
    var C = apiClass();
    if (!C) return null;
    try {
      API = new C({ developer: DEV, version: "0.0.3" });
    } catch (e) {
      API = null;
    }
    return API;
  }

  function flip() {
    if (typeof window.showAnswer === "function") return window.showAnswer();
    var a = api();
    if (a) a.ankiShowAnswer();
  }

  function grade(n) {
    var fn = window["buttonAnswerEase" + n];
    if (typeof fn === "function") return fn();
    var a = api();
    if (a) a["ankiAnswerEase" + n]();
  }

  // ------------------------------------------------------------ drawing
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function options(ce, letters) {
    var box = el("div", "pe-ui " + (ce ? "pe-ce" : "pe-letters"));
    box.setAttribute("role", "group");
    var list = ce ? ["CERTO", "ERRADO"] : letters;
    for (var i = 0; i < list.length; i++) {
      var v = list[i];
      var b = el("button", "pe-opt", ce ? '<span class="pe-k">' + v.charAt(0) + "</span>" + (v === "CERTO" ? "Certo" : "Errado") : '<span class="pe-k">' + v + "</span>");
      b.type = "button";
      b.setAttribute("data-v", v);
      box.appendChild(b);
    }
    return box;
  }

  // Puts the options where the "( ) Certo ( ) Errado" line is, or after the question.
  function placeOptions(nodes, box, fallback) {
    var text = joined(nodes);
    var m = CE_RE.exec(text);
    if (m) {
      var r = rangeOf(nodes, m.index, m.index + m[0].length);
      r.deleteContents();
      r.insertNode(box);
    } else if (fallback && fallback.parentNode) fallback.parentNode.insertBefore(box, fallback);
    else document.body.appendChild(box);
  }

  function markOptions(box, choice, correct) {
    var buttons = box.querySelectorAll(".pe-opt");
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      var v = b.getAttribute("data-v");
      b.disabled = true;
      if (v === correct) b.classList.add("pe-correct");
      if (v === choice) b.classList.add(v === correct ? "pe-chosen" : "pe-wrongpick");
    }
  }

  function markTrap(wrong, right) {
    var nodes = textNodes("front", document.getElementById("answer"));
    var hay = "";
    var map = [];
    var raw = joined(nodes);
    var space = false;
    for (var i = 0; i < raw.length; i++) {
      var ch = raw.charAt(i);
      if (/\s/.test(ch)) {
        if (space) continue;
        space = true;
        ch = " ";
      } else space = false;
      var f = ch.normalize ? ch.normalize("NFD").replace(/[̀-ͯ]/g, "") : ch;
      f = f.toLowerCase();
      for (var j = 0; j < f.length; j++) {
        hay += f.charAt(j);
        map.push(i);
      }
    }
    var needle = squash(wrong).toLowerCase();
    if (needle.normalize) needle = needle.normalize("NFD").replace(/[̀-ͯ]/g, "");
    var at = needle ? hay.indexOf(needle) : -1;
    if (at < 0) return;
    var r = rangeOf(nodes, map[at], map[at + needle.length - 1] + 1);
    var mark = el("span", "pe-trap");
    try {
      r.surroundContents(mark);
    } catch (e) {
      mark.appendChild(r.extractContents());
      r.insertNode(mark);
    }
    var fix = el("span", "pe-ui pe-fix");
    fix.textContent = right;
    mark.parentNode.insertBefore(fix, mark.nextSibling);
  }

  function gradeRow(right) {
    if (newScreen()) {
      return el("p", "pe-ui pe-hint", right ? "Acertou: dê Difícil, Bom ou Fácil nos botões do AnkiDroid." : "Errou: dê De novo nos botões do AnkiDroid.");
    }
    var row = el("div", "pe-ui pe-grade");
    var items = right
      ? [
          [2, "Difícil"],
          [3, "Bom"],
          [4, "Fácil"],
        ]
      : [[1, "Continuar"]];
    for (var i = 0; i < items.length; i++) {
      var b = el("button", "pe-g" + (items[i][0] === 3 || !right ? " pe-main" : ""), items[i][1] + (right ? "" : "<small>De novo</small>"));
      b.type = "button";
      b.setAttribute("data-ease", String(items[i][0]));
      row.appendChild(b);
    }
    row.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pe-g") : null;
      if (!b) return;
      voiceQuiet();
      sendGrade(row, Number(b.getAttribute("data-ease")));
    });
    return row;
  }

  // Gives the grade once, from a tap or from the voice.
  function sendGrade(row, n) {
    if (row) {
      if (row.getAttribute("data-sent")) return;
      row.setAttribute("data-sent", "1");
      var b = row.querySelector('.pe-g[data-ease="' + n + '"]');
      if (b) b.classList.add("pe-pressed");
    }
    grade(n);
  }

  // ------------------------------------------------------------ the two sides
  // Each returns what the voice mode needs to know about the card.
  function question() {
    var nodes = textNodes("front", null);
    var text = joined(nodes);
    var ce = CE_RE.test(text);
    var letters = ce ? null : lettersOf(linesOf("front", null));
    if (!ce && !letters) return { kind: "basic", text: speechOf(linesOf("front", null, true)) };
    var key = keyOf(text);
    var box = options(ce, letters);
    placeOptions(nodes, box, document.querySelector('.pe-m[data-side="q"]'));
    var info = { kind: ce ? "ce" : "mc", letters: ce ? ["CERTO", "ERRADO"] : letters, box: box };
    info.text = speechOf(linesOf("front", null, true), !ce); // without the "( ) Certo ( ) Errado" line
    info.choose = function (v) {
      if (box.getAttribute("data-sent")) return;
      box.setAttribute("data-sent", "1");
      save({ v: v, k: key, t: Date.now() });
      var b = box.querySelector('.pe-opt[data-v="' + v + '"]');
      if (b) b.classList.add("pe-chosen");
      voiceQuiet();
      setTimeout(flip, 140);
    };
    // The choice is kept on the first touch, before AnkiDroid's own tap gestures can flip the card.
    box.addEventListener("pointerdown", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pe-opt") : null;
      if (b && !box.getAttribute("data-sent")) save({ v: b.getAttribute("data-v"), k: key, t: Date.now() });
    });
    box.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pe-opt") : null;
      if (b) info.choose(b.getAttribute("data-v"));
    });
    return info;
  }

  function answer(mark) {
    var nodes = textNodes("front", mark);
    var text = joined(nodes);
    var ce = CE_RE.test(text);
    var letters = ce ? null : lettersOf(linesOf("front", mark));
    var backLines = linesOf("back", mark);
    var basic = { kind: "basic", back: backLines };
    if (!ce && !letters) return basic;
    var backText = squash(backLines.join(" "));
    var m = ce ? CE_ANS_RE.exec(backText) : MC_ANS_RE.exec(backText.slice(0, 200));
    if (!m) return basic; // not a Certo/Errado item or a question with a gabarito
    var correct = m[1].toUpperCase();
    if (!ce && letters.indexOf(correct) < 0) return basic;
    var rec = take();
    var choice = rec && rec.k === keyOf(text) && Date.now() - rec.t < MAX_AGE ? rec.v : null;
    var box = options(ce, letters);
    placeOptions(nodes, box, mark);
    markOptions(box, choice, correct);
    var info = { kind: ce ? "ce" : "mc", correct: correct, choice: choice, right: choice === correct, back: backLines, trap: null, row: null };
    if (!choice) return info; // the card was turned without choosing: the gabarito is marked, nothing else
    var word = ce ? (correct === "CERTO" ? "Certo" : "Errado") : correct;
    var verdict = el("div", "pe-ui pe-verdict " + (info.right ? "pe-right" : "pe-wrong"), (info.right ? "Você acertou." : "Você errou.") + "<small>Gabarito: " + word + "</small>");
    box.parentNode.insertBefore(verdict, box.nextSibling);
    if (ce && correct === "ERRADO") {
      for (var i = 0; i < backLines.length; i++) {
        var t = TRAP_RE.exec(backLines[i]);
        if (t) {
          info.trap = { from: squash(t[1]), to: squash(t[2]) };
          markTrap(t[1], info.trap.to);
          break;
        }
      }
    }
    var end = document.querySelector('.pe-m[data-side="a"]');
    var row = gradeRow(info.right);
    if (end && end.parentNode) end.parentNode.insertBefore(row, end);
    else document.body.appendChild(row);
    if (row.classList.contains("pe-grade")) info.row = row;
    return info;
  }

  // ------------------------------------------------------------ Modo voz
  var VOICE_KEY = "painelEstudosVoz";
  var RATE_KEY = "painelEstudosVozRitmo";
  var COUNT_KEY = "painelEstudosVozCartoes";
  var LANG = "pt-BR";
  var MAX_FAILS = 3;
  var MAX_SILENT = 10;
  var voice = { on: false, side: null, info: null, listening: false, fails: 0, silent: 0, timer: null, bar: null, langs: {}, warned: false };

  // What the card says, as it should sound: no emoji, abbreviations of the law spelled out,
  // "05 (cinco)" read once.
  var CODES = {
    "CF/88": "Constituição Federal",
    CF: "Constituição Federal",
    CP: "Código Penal",
    CPP: "Código de Processo Penal",
    CPC: "Código de Processo Civil",
    CC: "Código Civil",
    CTN: "Código Tributário Nacional",
    CDC: "Código de Defesa do Consumidor",
    ECA: "Estatuto da Criança e do Adolescente",
    LINDB: "Lei de Introdução às Normas do Direito Brasileiro",
    STF: "S T F",
    STJ: "S T J",
    TJRS: "T J R S",
  };
  function speakable(s) {
    s = String(s || "");
    s = s.replace(/[\u{1F000}-\u{1FAFF}\u{2190}-\u{21FF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu, " ");
    s = s.replace(/(\b\d{1,3}(?:\/\d{1,3})?)\s*\(([a-zà-ú\s-]{2,40})\)/g, "$2");
    s = s.replace(/\bArts\.\s*/g, "artigos ").replace(/\bArt\.\s*/gi, "artigo ");
    s = s.replace(/§§\s*/g, "parágrafos ").replace(/§\s*/g, "parágrafo ");
    s = s.replace(/\bn[º°]\s*/gi, "número ").replace(/\binc\.\s*/gi, "inciso ").replace(/\bal\.\s*/gi, "alínea ");
    s = s.replace(/\b(CF\/88|CF|CPP|CPC|CP|CC|CTN|CDC|ECA|LINDB|STF|STJ|TJRS)\b/g, function (m) {
      return CODES[m];
    });
    s = s.replace(/\b(\d{1,2}\.\d{3})\/(\d{2}|\d{4})\b/g, "$1 de $2"); // Lei 14.133/2021
    s = s.replace(/\]\s*(?=[A-ZÀ-Ý])/g, ". ").replace(/[\[\]]/g, " ").replace(/\s[–—]\s/g, ", ");
    return squash(s);
  }

  // Android's voice takes up to about 4000 characters at a time.
  function chunks(text) {
    var out = [];
    while (text.length > 3500) {
      var cut = text.lastIndexOf(". ", 3500);
      if (cut < 1000) cut = 3500;
      out.push(text.slice(0, cut + 1));
      text = text.slice(cut + 1);
    }
    if (squash(text)) out.push(text);
    return out;
  }

  function norm(s) {
    var t = String(s || "").toLowerCase();
    if (t.normalize) t = t.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return squash(t.replace(/[^a-z0-9\s]/g, " "));
  }

  function rate() {
    var r = parseFloat(getItem(RATE_KEY));
    return r >= 0.6 && r <= 2 ? r : 1;
  }

  // The words that work on this side, shown while listening; said aloud only on the first cards.
  function hint(sideName, info) {
    if (sideName === "q") {
      if (info.kind === "ce") return "certo ou errado";
      if (info.kind === "mc") return "letra " + info.letters.join(", ");
      return "mostrar";
    }
    if (info.kind !== "basic" && info.choice) return info.right ? "difícil, bom ou fácil" : "continuar";
    return "errei, difícil, bom ou fácil";
  }

  function frontSpeech(info, prompt) {
    var s = info.text || "";
    if (!prompt) return s;
    if (info.kind === "ce") return joinSpeech(s, "Certo ou errado?");
    if (info.kind === "mc") return joinSpeech(s, "Qual é a letra?");
    return joinSpeech(s, "Diga mostrar para ver a resposta.");
  }

  function backSpeech(info, prompt) {
    var s;
    if (info.kind === "basic") s = speechOf(info.back);
    else {
      var g = info.kind === "ce" ? (info.correct === "CERTO" ? "certo" : "errado") : "letra " + info.correct;
      s = info.choice ? (info.right ? "Você acertou. " : "Você errou. ") : "";
      s += "Gabarito: " + g + ".";
      if (info.trap) s += " A lei diz " + info.trap.to + ", não " + info.trap.from + ".";
    }
    if (prompt) s = joinSpeech(s, hint("a", info).replace(/^./, function (c) { return c.toUpperCase(); }) + "?");
    return s;
  }

  // The back without the gabarito line and the 🔁 line: what "explica" reads.
  function explanation(info) {
    var lines = [];
    for (var i = 0; i < info.back.length; i++) {
      var l = squash(info.back[i]);
      if (!l || TRAP_RE.test(l)) continue;
      if (!lines.length && info.kind !== "basic" && (CE_ANS_RE.test(l) || /gabarito/i.test(l))) continue;
      lines.push(l);
    }
    return lines.length ? speechOf(lines, info.kind === "mc") : "Não há explicação no verso deste cartão.";
  }

  // ---- what was said -> what to do
  var STOP_RE = /^(?:(parar|pare|pausa|pausar|desliga|desligar|desligue|chega|sair|encerrar|encerra)\b|para$)/;
  var REPEAT_RE = /\b(repete|repetir|repita|outra vez|le de novo|leia de novo)\b/;
  var FASTER_RE = /\b(mais rapido|acelera|acelerar)\b/;
  var SLOWER_RE = /\b(mais devagar|mais lento|devagar)\b/;
  var EXPLAIN_RE = /\b(explica|explicar|explique|explicacao|comentario|fundamento|le o verso|leia o verso)\b/;
  var SHOW_RE = /\b(mostrar|mostra|mostre|virar|vira|resposta|pronto|revelar)\b/;
  var LETTER_WORDS = { a: "A", ah: "A", b: "B", be: "B", bi: "B", c: "C", ce: "C", se: "C", d: "D", de: "D", e: "E", eh: "E" };
  var ORDINALS = { primeira: "A", segunda: "B", terceira: "C", quarta: "D", quinta: "E" };

  function understandOne(said, sideName, info) {
    var s = norm(said);
    if (!s) return null;
    if (STOP_RE.test(s)) return { type: "stop" };
    if (REPEAT_RE.test(s)) return { type: "repeat" };
    if (FASTER_RE.test(s)) return { type: "rate", by: 0.15 };
    if (SLOWER_RE.test(s)) return { type: "rate", by: -0.15 };
    if (sideName === "q") {
      if (info.kind === "ce") {
        var yes = /\b(certo|certa|correto|correta|verdadeiro|verdadeira|verdade)\b/.test(s) || /^(c|ce|se|sim)$/.test(s);
        var no = /\b(errado|errada|incorreto|incorreta|falso|falsa)\b/.test(s) || /^(e|eh|nao)$/.test(s);
        if (yes !== no) return { type: "choice", v: yes ? "CERTO" : "ERRADO" };
      } else if (info.kind === "mc") {
        var m = /\b(?:letra|alternativa|opcao|item)\s+([a-e]|be|bi|ce|se|de|eh)\b/.exec(s);
        var o = /\b(primeira|segunda|terceira|quarta|quinta)\b/.exec(s);
        var v = m ? LETTER_WORDS[m[1]] : LETTER_WORDS[s] || (o ? ORDINALS[o[1]] : null);
        if (v && info.letters.indexOf(v) >= 0) return { type: "choice", v: v };
      }
      if (SHOW_RE.test(s)) return { type: "flip" };
      return null;
    }
    if (EXPLAIN_RE.test(s)) return { type: "explain" };
    if (info.kind !== "basic" && info.choice) {
      if (!info.right) {
        if (/\b(continuar|continua|proximo|proxima|seguir|segue|ok|okay|beleza|de novo|errei|bom|boa|facil|dificil|certo)\b/.test(s)) return { type: "grade", n: 1 };
        return null;
      }
      if (/\bfacil\b/.test(s)) return { type: "grade", n: 4 };
      if (/\bdificil\b/.test(s)) return { type: "grade", n: 2 };
      if (/\b(bom|boa|proximo|proxima|continuar|continua|seguir|segue|ok|okay|beleza|certo)\b/.test(s)) return { type: "grade", n: 3 };
      return null;
    }
    if (/\b(errei|de novo|nao sabia|nao lembrei|esqueci|errado)\b/.test(s)) return { type: "grade", n: 1 };
    if (/\bfacil\b/.test(s)) return { type: "grade", n: 4 };
    if (/\bdificil\b/.test(s)) return { type: "grade", n: 2 };
    if (/\b(bom|boa|acertei|sabia|lembrei|certo|proximo|proxima|continuar|ok)\b/.test(s)) return { type: "grade", n: 3 };
    return null;
  }

  // The recognizer sends a few guesses, best first: the first one that means something wins.
  function understand(guesses, sideName, info) {
    for (var i = 0; i < guesses.length; i++) {
      var cmd = understandOne(guesses[i], sideName, info);
      if (cmd) return cmd;
    }
    return null;
  }

  // ---- the bar on the card
  function voiceBar() {
    var bar = el("div", "pe-ui pe-voz");
    bar.innerHTML = '<button type="button" class="pe-voz-btn"></button><span class="pe-voz-msg" aria-live="polite"></span>';
    bar.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pe-voz-btn") : null;
      if (!b) return;
      var state = bar.getAttribute("data-state");
      if (state === "off" || state === "error") voiceOn();
      else if (state === "paused") {
        voice.fails = voice.silent = 0;
        listen();
      } else voiceOff("Modo voz desligado.");
    });
    document.body.insertBefore(bar, document.body.firstChild);
    return bar;
  }

  function show(state, msg) {
    var bar = voice.bar;
    if (!bar) return;
    bar.setAttribute("data-state", state);
    bar.className = "pe-ui pe-voz pe-voz-" + state;
    var labels = { off: "🎤 Modo voz", error: "🎤 Tentar de novo", paused: "Continuar", reading: "Parar", listening: "Parar" };
    bar.querySelector(".pe-voz-btn").textContent = labels[state] || "Parar";
    bar.querySelector(".pe-voz-msg").textContent = msg || "";
  }

  function langOnce(kind, fn) {
    if (!voice.langs[kind]) {
      voice.langs[kind] = Promise.resolve()
        .then(fn)
        .catch(function () {
          return null;
        });
    }
    return voice.langs[kind];
  }

  // Reads the text, then calls then() when the voice has finished.
  function speak(text, then) {
    var a = api();
    if (!a || !voice.on) return;
    var parts = chunks(speakable(text));
    if (!parts.length) return then && then();
    show("reading", "Lendo…");
    var go = function () {
      var p = Promise.resolve();
      parts.forEach(function (t, i) {
        p = p.then(function () {
          return a.ankiTtsSpeak(t, i ? 1 : 0);
        });
      });
      return p;
    };
    langOnce("tts", function () {
      return a.ankiTtsSetLanguage(LANG).then(function (r) {
        // below 0: Android has no Portuguese voice (or its data is missing)
        if (r && typeof r.value === "number" && r.value < 0 && !voice.warned) {
          voice.warned = true;
          show("reading", "Sem voz em português no Android: instale nas configurações de texto para fala.");
        }
      });
    })
      .then(function () {
        return a.ankiTtsSetSpeechRate(rate());
      })
      .then(go)
      .then(
        function () {
          waitQuiet(then, go);
        },
        function () {
          if (then) then();
        }
      );
  }

  // Waits for the voice to start and then to stop. If it never starts (the voice can still be
  // loading on the first card), says it once more.
  function waitQuiet(then, again) {
    var a = api();
    var t0 = Date.now();
    var quiet = 0;
    var heard = false;
    var retried = false;
    (function poll() {
      if (!voice.on) return;
      a.ankiTtsIsSpeaking().then(
        function (r) {
          var speaking = !!(r && r.value);
          if (speaking) {
            heard = true;
            quiet = 0;
          } else quiet++;
          var waited = Date.now() - t0;
          if (!heard && waited > 1500 && !retried && again) {
            retried = true;
            t0 = Date.now();
            again();
          } else if ((heard && quiet >= 2) || (!heard && waited > 1500) || waited > 180000) {
            if (then) then();
            return;
          }
          setTimeout(poll, 250);
        },
        function () {
          if (then) then();
        }
      );
    })();
  }

  function listen() {
    var a = api();
    if (!a || !voice.on) return;
    voice.listening = true;
    show("listening", "Ouvindo… diga " + hint(voice.side, voice.info));
    clearTimeout(voice.timer);
    // if AnkiDroid never answers, try again
    voice.timer = setTimeout(function () {
      if (!voice.listening) return;
      voice.listening = false;
      missed(false);
    }, 20000);
    langOnce("stt", function () {
      return a.ankiSttSetLanguage(LANG);
    })
      .then(function () {
        return a.ankiSttStart();
      })
      .catch(function () {
        voice.listening = false;
        clearTimeout(voice.timer);
        failed("O AnkiDroid não respondeu ao pedido para ouvir.");
      });
  }

  // AnkiDroid calls this with what was heard: {"success": true, "value": "[\"certo\", ...]"}, as text.
  function onHeard(raw) {
    if (!voice.listening) return; // not asked by this side of the card
    voice.listening = false;
    clearTimeout(voice.timer);
    var r = null;
    try {
      r = typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch (e) {
      r = null;
    }
    if (!r || r.success === false) return heardError(r ? String(r.value || "") : "");
    var guesses = [];
    try {
      guesses = JSON.parse(r.value);
    } catch (e) {
      guesses = [String(r.value || "")];
    }
    if (!Array.isArray(guesses)) guesses = [String(guesses)];
    var cmd = understand(guesses, voice.side, voice.info);
    if (!cmd) return missed(true);
    voice.fails = voice.silent = 0;
    act(cmd);
  }

  // AnkiDroid's words for what went wrong (JavaScriptSTT.kt).
  function heardError(msg) {
    if (/permission/i.test(msg)) {
      return failed("O AnkiDroid não tem permissão para usar o microfone. Ative em Configurações do Android, Apps, AnkiDroid, Permissões, Microfone.");
    }
    if (/not available/i.test(msg)) return failed("O reconhecimento de voz não está disponível neste celular.");
    if (/network|server/i.test(msg)) return retry("sem conexão para reconhecer a voz (sem internet, o Android precisa do português offline).");
    if (/busy|client|audio|starting/i.test(msg)) return retry("o microfone não respondeu.");
    missed(false); // silence ("No match found", "Speech timeout")
  }

  function retry(why) {
    voice.fails++;
    if (voice.fails >= MAX_FAILS) return pause(why);
    setTimeout(listen, 800);
  }

  // Words that mean nothing here: three in a row pause. Silence: it keeps listening for about a
  // minute, time to think, then pauses.
  function missed(spoken) {
    if (spoken) voice.fails++;
    else voice.silent++;
    if (voice.fails >= MAX_FAILS) return pause("não entendi o que foi dito.");
    if (voice.silent >= MAX_SILENT) return pause();
    if (spoken) speak("Não entendi.", listen);
    else listen();
  }

  function pause(why) {
    var msg = "Pausado: " + (why || "não ouvi uma resposta.");
    show("paused", msg);
    speak("Pausado.", function () {
      show("paused", msg + " Toque em Continuar.");
    });
  }

  function failed(msg) {
    voice.on = false;
    voice.listening = false;
    setItem(VOICE_KEY, null);
    show("error", msg);
  }

  function act(cmd) {
    var info = voice.info;
    if (cmd.type === "stop") return voiceOff("Modo voz desligado.");
    if (cmd.type === "repeat") return run(false);
    if (cmd.type === "rate") {
      setItem(RATE_KEY, Math.max(0.6, Math.min(2, Math.round((rate() + cmd.by) * 100) / 100)));
      return speak(cmd.by > 0 ? "Mais rápido." : "Mais devagar.", listen);
    }
    if (cmd.type === "explain") return speak(explanation(info), listen);
    if (cmd.type === "choice") {
      show("reading", "Resposta: " + (info.kind === "ce" ? (cmd.v === "CERTO" ? "Certo" : "Errado") : "letra " + cmd.v));
      return info.choose(cmd.v);
    }
    if (cmd.type === "flip") {
      voiceQuiet();
      return flip();
    }
    if (cmd.type === "grade") {
      voiceQuiet();
      show("reading", ["", "De novo", "Difícil", "Bom", "Fácil"][cmd.n]);
      sendGrade(info.row, cmd.n);
    }
  }

  // Reads this side and listens. The first cards of a session also say which words work (both
  // sides of each: the front counts the card).
  function run(count) {
    var info = voice.info;
    var n = parseInt(getItem(COUNT_KEY), 10) || 0;
    if (count) setItem(COUNT_KEY, ++n);
    var prompt = n <= 3;
    var text = voice.side === "q" ? frontSpeech(info, prompt) : backSpeech(info, prompt);
    voice.fails = voice.silent = 0;
    speak(text, listen);
  }

  function voiceOn() {
    voice.on = true;
    voice.fails = voice.silent = 0;
    setItem(VOICE_KEY, "1");
    run(voice.side === "q");
  }

  function voiceOff(msg) {
    voice.on = false;
    setItem(VOICE_KEY, null);
    voiceQuiet();
    show("off", msg || "");
  }

  // Stops speaking and listening (a tap, a grade, a flip).
  function voiceQuiet() {
    voice.listening = false;
    clearTimeout(voice.timer);
    var a = voice.on ? api() : null;
    if (!a) return;
    try {
      a.ankiSttStop().catch(function () {});
      a.ankiTtsStop().catch(function () {});
    } catch (e) {
      /* nothing to stop */
    }
  }

  function voiceStart(sideName, info) {
    if (!info || newScreen() || !api()) return; // the new screen can't take the grade from the card
    voice.side = sideName;
    voice.info = info;
    voice.bar = voiceBar();
    window.ankiSttResult = onHeard;
    if (getItem(VOICE_KEY) === "1") {
      voice.on = true;
      run(sideName === "q");
    } else show("off", "");
  }

  function start() {
    var marks = document.querySelectorAll(".pe-m:not([data-done])");
    if (!marks.length) return; // this side was already handled by the other copy of the script
    for (var i = 0; i < marks.length; i++) marks[i].setAttribute("data-done", "1");
    var mark = document.getElementById("answer");
    var onBack = !!mark || !!document.querySelector('.pe-m[data-side="a"]');
    var info = null;
    try {
      if (!onBack) info = question();
      else if (mark) info = answer(mark);
      else info = { kind: "basic", back: linesOf("front", null) }; // a back without the front (cloze)
    } catch (e) {
      info = null; // the card stays as Anki drew it
    }
    try {
      voiceStart(onBack ? "a" : "q", info);
    } catch (e) {
      /* no voice on this card */
    }
  }

  // On the back, the front's copy of this script runs before the rest of the card is parsed.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
