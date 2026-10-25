/* Painel de Estudos no celular: os botões C/E e as letras das questões dentro do próprio cartão.
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
 * Este arquivo não pode ter chaves duplas seguidas: o Anki leria como campo do modelo.
 */
(function () {
  "use strict";
  var root = document.documentElement;
  // AnkiDroid's card page marks <html> with "android" and defines showAnswer(); both study screens do.
  var onAndroid = (root.classList.contains("android") || typeof window.AnkiDroidJS === "function") && typeof window.showAnswer === "function";
  if (!onAndroid) return;

  var KEY = "painelEstudosEscolha";
  var DEV = "https://github.com/jpvanacor/painel-estudos-anki";
  var MAX_AGE = 30 * 60 * 1000;
  var CE_RE = /\(\s*\)\s*Certo[\s ]*\(\s*\)\s*Errado/i;
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

  // Text of one side with line breaks where <br> and blocks are, for finding the alternatives.
  function linesOf(which, mark) {
    var text = "";
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null);
    while (walker.nextNode()) {
      var n = walker.currentNode;
      if (skipped(n, document.body) || side(n, mark) !== which) continue;
      if (n.nodeType === 3) text += n.nodeValue;
      else if (n.nodeName === "BR" || BLOCKS[n.nodeName]) text += "\n";
    }
    return text.split("\n");
  }

  function joined(nodes) {
    var s = "";
    for (var i = 0; i < nodes.length; i++) s += nodes[i].nodeValue;
    return s;
  }

  function squash(s) {
    return String(s || "").replace(/[\s ]+/g, " ").trim();
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

  // ------------------------------------------------------------ talking to AnkiDroid
  function api() {
    try {
      return new window.AnkiDroidJS({ developer: DEV, version: "0.0.3" });
    } catch (e) {
      return null;
    }
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
      if (!b || row.getAttribute("data-sent")) return;
      row.setAttribute("data-sent", "1");
      b.classList.add("pe-pressed");
      grade(Number(b.getAttribute("data-ease")));
    });
    return row;
  }

  // ------------------------------------------------------------ the two sides
  function question() {
    var nodes = textNodes("front", null);
    var text = joined(nodes);
    var ce = CE_RE.test(text);
    var letters = ce ? null : lettersOf(linesOf("front", null));
    if (!ce && !letters) return;
    var key = keyOf(text);
    var box = options(ce, letters);
    placeOptions(nodes, box, document.querySelector('.pe-m[data-side="q"]'));
    var pick = function (b) {
      save({ v: b.getAttribute("data-v"), k: key, t: Date.now() });
    };
    // The choice is kept on the first touch, before AnkiDroid's own tap gestures can flip the card.
    box.addEventListener("pointerdown", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pe-opt") : null;
      if (b && !box.getAttribute("data-sent")) pick(b);
    });
    box.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pe-opt") : null;
      if (!b || box.getAttribute("data-sent")) return;
      box.setAttribute("data-sent", "1");
      pick(b);
      b.classList.add("pe-chosen");
      setTimeout(flip, 140);
    });
  }

  function answer(mark) {
    var nodes = textNodes("front", mark);
    var text = joined(nodes);
    var ce = CE_RE.test(text);
    var letters = ce ? null : lettersOf(linesOf("front", mark));
    if (!ce && !letters) return;
    var backLines = linesOf("back", mark);
    var backText = squash(backLines.join(" "));
    var m = ce ? CE_ANS_RE.exec(backText) : MC_ANS_RE.exec(backText.slice(0, 200));
    if (!m) return; // not a Certo/Errado item or a question with a gabarito
    var correct = m[1].toUpperCase();
    if (!ce && letters.indexOf(correct) < 0) return;
    var rec = take();
    var choice = rec && rec.k === keyOf(text) && Date.now() - rec.t < MAX_AGE ? rec.v : null;
    var box = options(ce, letters);
    placeOptions(nodes, box, mark);
    markOptions(box, choice, correct);
    if (!choice) return; // the card was turned without choosing: the gabarito is marked, nothing else
    var right = choice === correct;
    var word = ce ? (correct === "CERTO" ? "Certo" : "Errado") : correct;
    var verdict = el("div", "pe-ui pe-verdict " + (right ? "pe-right" : "pe-wrong"), (right ? "Você acertou." : "Você errou.") + "<small>Gabarito: " + word + "</small>");
    box.parentNode.insertBefore(verdict, box.nextSibling);
    if (ce && correct === "ERRADO") {
      for (var i = 0; i < backLines.length; i++) {
        var t = TRAP_RE.exec(backLines[i]);
        if (t) {
          markTrap(t[1], squash(t[2]));
          break;
        }
      }
    }
    var end = document.querySelector('.pe-m[data-side="a"]');
    var row = gradeRow(right);
    if (end && end.parentNode) end.parentNode.insertBefore(row, end);
    else document.body.appendChild(row);
  }

  function start() {
    var marks = document.querySelectorAll(".pe-m:not([data-done])");
    if (!marks.length) return; // this side was already handled by the other copy of the script
    for (var i = 0; i < marks.length; i++) marks[i].setAttribute("data-done", "1");
    var mark = document.getElementById("answer");
    var onBack = !!mark || !!document.querySelector('.pe-m[data-side="a"]');
    try {
      if (onBack && mark) answer(mark);
      else if (!onBack) question();
    } catch (e) {
      /* the card stays as Anki drew it */
    }
  }

  // On the back, the front's copy of this script runs before the rest of the card is parsed.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
