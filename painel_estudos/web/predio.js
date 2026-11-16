/* O prédio: the study game's pixel building, drawn above the card while you study.
 *
 * Same craft as The Quiet Floor: rectangles on a small canvas (320 x 64), scaled up without
 * smoothing. On the left, the building from the street: one floor per matéria of the cronograma,
 * the café at street level, the roof when it is open. On the right, inside the floor of the
 * matéria being studied: how furnished it is follows the share of its cards already learned,
 * with simulated students at their desks and you at yours. Answers make things happen here
 * (react); the words about them (banners, numbers) are HTML, drawn by app.js.
 */
(function () {
  "use strict";
  const W = 320;
  const H = 64;
  const TX = 58; // where the inside of the floor starts

  // ---- small helpers
  let G = null;
  function R(c, x, y, w, h) {
    G.fillStyle = c;
    G.fillRect(Math.round(x), Math.round(y), w, h);
  }
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (a) => a[Math.floor(Math.random() * a.length)];
  function hash(n) {
    n = (n ^ 61) ^ (n >>> 16);
    n = n + (n << 3);
    n = n ^ (n >>> 4);
    n = Math.imul(n, 0x27d4eb2d);
    n = n ^ (n >>> 15);
    return (n >>> 0) / 4294967296;
  }
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    let r = n >> 16;
    let g = (n >> 8) & 255;
    let b = n & 255;
    if (f < 0) {
      r *= 1 + f;
      g *= 1 + f;
      b *= 1 + f;
    } else {
      r += (255 - r) * f;
      g += (255 - g) * f;
      b += (255 - b) * f;
    }
    return "#" + ((1 << 24) | (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b)).toString(16).slice(1);
  }
  function disc(cx, cy, r, c) {
    for (let y = -r; y <= r; y++) {
      const w = Math.round(Math.sqrt(r * r - y * y));
      R(c, cx - w, cy + y, 2 * w + 1, 1);
    }
  }

  // ---- 3x5 pixel font (capitals, digits, a few signs)
  const FONT = {
    A: [".#.", "#.#", "###", "#.#", "#.#"], B: ["##.", "#.#", "##.", "#.#", "##."], C: [".##", "#..", "#..", "#..", ".##"],
    D: ["##.", "#.#", "#.#", "#.#", "##."], E: ["###", "#..", "##.", "#..", "###"], F: ["###", "#..", "##.", "#..", "#.."],
    G: [".##", "#..", "#.#", "#.#", ".##"], H: ["#.#", "#.#", "###", "#.#", "#.#"], I: ["###", ".#.", ".#.", ".#.", "###"],
    J: ["..#", "..#", "..#", "#.#", ".#."], K: ["#.#", "#.#", "##.", "#.#", "#.#"], L: ["#..", "#..", "#..", "#..", "###"],
    M: ["#.#", "###", "###", "#.#", "#.#"], N: ["##.", "#.#", "#.#", "#.#", "#.#"], O: [".#.", "#.#", "#.#", "#.#", ".#."],
    P: ["##.", "#.#", "##.", "#..", "#.."], Q: [".#.", "#.#", "#.#", ".#.", "..#"], R: ["##.", "#.#", "##.", "#.#", "#.#"],
    S: [".##", "#..", ".#.", "..#", "##."], T: ["###", ".#.", ".#.", ".#.", ".#."], U: ["#.#", "#.#", "#.#", "#.#", "###"],
    V: ["#.#", "#.#", "#.#", "#.#", ".#."], W: ["#.#", "#.#", "#.#", "###", "#.#"], X: ["#.#", "#.#", ".#.", "#.#", "#.#"],
    Y: ["#.#", "#.#", ".#.", ".#.", ".#."], Z: ["###", "..#", ".#.", "#..", "###"],
    0: ["###", "#.#", "#.#", "#.#", "###"], 1: [".#.", "##.", ".#.", ".#.", "###"], 2: ["##.", "..#", ".#.", "#..", "###"],
    3: ["##.", "..#", ".#.", "..#", "##."], 4: ["#.#", "#.#", "###", "..#", "..#"], 5: ["###", "#..", "##.", "..#", "##."],
    6: [".##", "#..", "###", "#.#", "###"], 7: ["###", "..#", ".#.", ".#.", ".#."], 8: ["###", "#.#", ".#.", "#.#", "###"],
    9: ["###", "#.#", "###", "..#", "##."], "!": ["#", "#", "#", ".", "#"], "?": ["##.", "..#", ".#.", "...", ".#."],
    "+": ["...", ".#.", "###", ".#.", "..."], "-": ["...", "...", "###", "...", "..."], " ": [".", ".", ".", ".", "."],
    "%": ["#.#", "..#", ".#.", "#..", "#.#"], ".": [".", ".", ".", ".", "#"], ":": [".", "#", ".", "#", "."],
  };
  function textWidth(s, k = 1) {
    let w = 0;
    for (const ch of s) w += ((FONT[ch] || FONT[" "])[0].length + 1) * k;
    return w - k;
  }
  function drawText(s, x, y, c, k = 1) {
    for (const ch of s) {
      const g = FONT[ch] || FONT[" "];
      for (let r = 0; r < 5; r++) for (let i = 0; i < g[r].length; i++) if (g[r][i] === "#") R(c, x + i * k, y + r * k, k, k);
      x += (g[0].length + 1) * k;
    }
  }

  // ---- little icons for speech bubbles (7x6)
  const ICONS = {
    heart: { c: "#D2445A", px: [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."] },
    note: { c: "#2C5E8A", px: ["...##..", "...#.#.", "...#...", "...#...", ".###...", ".##...."] },
    coffee: { c: "#6B4228", px: ["..#.#..", ".#.#...", "######.", "#####.#", "######.", ".####.."] },
    book: { c: "#2F5D7C", px: [".......", "##.##..", "#.#.#..", "#.#.#..", "###.##.", "......."] },
    bulb: { c: "#E0AE4C", px: ["..###..", ".#...#.", ".#...#.", "..#.#..", "..###..", "..##..."] },
    star: { c: "#E0AE4C", px: ["...#...", "..###..", "#######", ".#####.", ".##.##.", "#.....#"] },
    q: { c: "#56665F", px: ["..###..", ".#...#.", "....#..", "...#...", ".......", "...#..."] },
  };
  function bubble(cx, bottom, b) {
    const h = 9;
    const w = b.icon ? 11 : textWidth(b.text) + 6;
    const x = Math.max(TX + 1, Math.min(W - w - 1, Math.round(cx - w / 2)));
    const y = Math.max(1, Math.round(bottom - h - 3));
    const ink = "#2A2522";
    const paper = "#FBF7EE";
    R(ink, x + 1, y, w - 2, 1);
    R(ink, x + 1, y + h - 1, w - 2, 1);
    R(ink, x, y + 1, 1, h - 2);
    R(ink, x + w - 1, y + 1, 1, h - 2);
    R(paper, x + 1, y + 1, w - 2, h - 2);
    const tx = Math.max(x + 2, Math.min(x + w - 4, Math.round(cx)));
    R(paper, tx, y + h - 1, 2, 1);
    R(ink, tx - 1, y + h - 1, 1, 1);
    R(ink, tx + 2, y + h - 1, 1, 1);
    R(ink, tx, y + h, 2, 1);
    if (b.icon) {
      const ic = ICONS[b.icon];
      for (let r = 0; r < 6; r++) for (let i = 0; i < 7; i++) if (ic.px[r][i] === "#") R(ic.c, x + 2 + i, y + 2 + r, 1, 1);
    } else drawText(b.text, x + 3, y + 2, b.color || ink);
  }

  // ---- sky
  const SKY = {
    day: { bands: ["#79B4DF", "#8FC2E6", "#A8D1EC", "#C3E0F1"], far: "#A9BFCF", near: "#8BA5BA", lit: 0 },
    dusk: { bands: ["#38386A", "#6E4A7C", "#BD6478", "#EB966A"], far: "#4C3B60", near: "#33284A", lit: 0.35 },
    night: { bands: ["#0B1430", "#101C3D", "#15254C", "#1B2D58"], far: "#151F38", near: "#0A101F", lit: 0.5 },
  };
  function skyMode() {
    const h = new Date().getHours() + new Date().getMinutes() / 60;
    if (h >= 6.5 && h < 17.5) return "day";
    if ((h >= 17.5 && h < 19) || (h >= 5.5 && h < 6.5)) return "dusk";
    return "night";
  }
  function skyBands(mode, x, y, w, h) {
    const b = SKY[mode].bands;
    const bh = Math.ceil(h / b.length);
    b.forEach((c, k) => R(c, x, y + k * bh, w, Math.min(bh, h - k * bh)));
  }

  // ---- looks
  const WALLS = [
    ["#2E4943", "#35524B", "#5B3C29"],
    ["#33415E", "#3B4A6B", "#4E3A2C"],
    ["#56404D", "#614957", "#5B3C29"],
    ["#45573A", "#4E6243", "#5A4128"],
    ["#5B4A33", "#66543B", "#47331F"],
    ["#344B5E", "#3D566B", "#4E3A2C"],
  ];
  const BOOKS = ["#8E3B46", "#2F5D7C", "#C49A3A", "#3F6B4E", "#6B4C8A", "#B5653A", "#D8CBB0", "#24404F", "#7A2E2E", "#4F7C8A"];
  const YOU = { skin: "#E0AC85", hair: "#2B1D16", shirt: "#2C7553", style: "short", glasses: false };
  const STUDENTS = [
    { skin: "#F2CDB0", hair: "#3B2219", shirt: "#C2566B", style: "long", glasses: false, act: "type" },
    { skin: "#8D5A3C", hair: "#17171A", shirt: "#3E6E9E", style: "curly", glasses: true, act: "read" },
    { skin: "#F2CDB0", hair: "#C9A15A", shirt: "#E0A23A", style: "bun", glasses: false, act: "write" },
    { skin: "#C68A62", hair: "#17171A", shirt: "#6B4C8A", style: "short", glasses: true, act: "type" },
  ];
  const DESKS = [146, 100, 192, 238, 284]; // yours first, then the students' as the floor fills

  function drawHair(L, x, y) {
    const c = L.hair;
    if (L.style === "long") {
      R(c, x, y, 10, 3);
      R(c, x, y + 3, 1, 8);
      R(c, x + 9, y + 3, 1, 8);
    } else if (L.style === "curly") {
      R(c, x, y - 1, 10, 4);
      R(c, x - 1, y + 1, 1, 3);
      R(c, x + 10, y + 1, 1, 3);
      R(shade(c, 0.15), x + 2, y - 1, 1, 1);
      R(shade(c, 0.15), x + 6, y, 1, 1);
    } else if (L.style === "bun") {
      R(c, x + 1, y, 8, 3);
      R(c, x + 3, y - 3, 4, 3);
      R(c, x, y + 1, 1, 4);
      R(c, x + 9, y + 1, 1, 4);
    } else {
      R(c, x, y, 10, 3);
      R(c, x, y + 3, 1, 2);
      R(c, x + 9, y + 3, 1, 2);
    }
  }

  // a person behind a desk, seen from the front; the desk is drawn over the legs
  function drawSeated(L, cx, t, p) {
    const x = cx - 5;
    let y = 31;
    if (p.cheer > 0 || p.bob) y -= 1;
    R(L.shirt, x, y + 10, 10, 7);
    R(shade(L.shirt, -0.2), x, y + 10, 1, 7);
    R(shade(L.shirt, -0.2), x + 9, y + 10, 1, 7);
    R(L.skin, x + 1, y + 1, 8, 8);
    R(shade(L.skin, -0.12), x, y + 4, 1, 2);
    R(shade(L.skin, -0.12), x + 9, y + 4, 1, 2);
    R(L.skin, x + 4, y + 9, 2, 1);
    drawHair(L, x, y);
    const look = p.look || 0;
    const blink = (t + p.phase) % 4.1 < 0.13;
    const down = p.act === "read" || p.act === "write" || p.act === "type";
    if (!blink) {
      R("#1E1A18", x + 3 + look, y + 5 + (down && !p.cheer ? 1 : 0), 1, 1);
      R("#1E1A18", x + 6 + look, y + 5 + (down && !p.cheer ? 1 : 0), 1, 1);
    }
    if (L.glasses) {
      R("#3A3330", x + 2 + look, y + 4, 6, 1);
      R("#3A3330", x + 2 + look, y + 5, 1, 1);
      R("#3A3330", x + 7 + look, y + 5, 1, 1);
    }
    if (p.cheer > 0) {
      // both arms up
      const k = Math.floor(t * 6) % 2;
      R(shade(L.shirt, -0.2), x - 2, y + 2 + k, 2, 9);
      R(shade(L.shirt, -0.2), x + 10, y + 2 + k, 2, 9);
      R(L.skin, x - 2, y + k, 2, 2);
      R(L.skin, x + 10, y + k, 2, 2);
    } else if (p.sip > 0) {
      R("#F2EEE3", x + 3, y + 6, 4, 4);
      R("#F2EEE3", x + 7, y + 7, 1, 2);
      R(L.skin, x + 3, y + 10, 3, 1);
    } else if (p.stretch > 0) {
      R(shade(L.shirt, -0.2), x - 1, y + 1, 2, 9);
      R(shade(L.shirt, -0.2), x + 9, y + 1, 2, 9);
      R(L.skin, x - 1, y - 1, 2, 2);
      R(L.skin, x + 9, y - 1, 2, 2);
    } else {
      const k = p.act === "type" ? Math.floor(t * 5 + p.phase) % 2 : 0;
      R(L.skin, x + 1 + k, y + 15, 2, 2);
      R(L.skin, x + 7 - k, y + 15, 2, 2);
      if (p.act === "read") {
        R(p.book || "#7A3B3B", x - 1, y + 12, 12, 5);
        R("#F2EEE3", x, y + 12, 10, 1);
        R(shade(p.book || "#7A3B3B", -0.3), x + 4, y + 12, 2, 5);
      }
      if (p.act === "write") R("#2A2522", x + 8, y + 12, 1, 3);
    }
  }

  function drawStanding(L, x, feet, t, walking) {
    const step = walking ? Math.floor(t * 7) % 2 : 0;
    const y = feet - 22 - step;
    x = Math.round(x) - 5;
    R(L.shirt, x, y + 10, 10, 6);
    R(shade(L.shirt, -0.2), x, y + 10, 1, 6);
    R(shade(L.shirt, -0.2), x + 9, y + 10, 1, 6);
    R(L.skin, x, y + 15, 1, 1);
    R(L.skin, x + 9, y + 15, 1, 1);
    R("#2F3A4A", x + 2, y + 16, 6, 4);
    R("#2F3A4A", x + 2, y + 20, 2, 1 - step);
    R("#2F3A4A", x + 6, y + 20, 2, step);
    R("#2A2522", x + 2, y + 21 - step, 2, 1 + step);
    R("#2A2522", x + 6, y + 20 + step, 2, 2 - step);
    R(L.skin, x + 1, y + 1, 8, 8);
    R(L.skin, x + 4, y + 9, 2, 1);
    drawHair(L, x, y);
    R("#1E1A18", x + 3, y + 5, 1, 1);
    R("#1E1A18", x + 6, y + 5, 1, 1);
  }

  function drawDesk(cx, opts) {
    const x = cx - 13;
    R("#8A5B36", x, 47, 26, 2);
    R("#6B4428", x, 49, 26, 1);
    R("#5A3A22", x + 1, 50, 2, 9);
    R("#5A3A22", x + 23, 50, 2, 9);
    R("#4A2F1C", x + 3, 50, 20, 4);
    // the laptop, seen from behind
    R("#9AA3AE", cx - 5, 41, 10, 6);
    R("#7E8893", cx - 5, 46, 10, 1);
    R("#C8CED6", cx - 1, 43, 2, 2);
    if (opts.mug) {
      R("#F2EEE3", x + 21, 44, 3, 3);
      R("#F2EEE3", x + 24, 45, 1, 1);
    }
    if (opts.pile) for (let k = 0; k < opts.pile; k++) R(k % 2 ? "#F4F1E8" : "#E6E0D2", x + 2, 46 - k, 7, 1);
  }

  // ---- the street view of the building (x 0..55)
  function drawTower(st, mode, t) {
    skyBands(mode, 0, 0, TX - 2, H);
    if (mode === "night") {
      for (let k = 0; k < 14; k++) if (Math.sin(t * 1.2 + k) > -0.3) R("#E8ECF8", hash(k * 7) * 54, hash(k * 13) * 30, 1, 1);
    } else if (mode === "day") {
      const cx = ((t * 1.2) % 80) - 14;
      R("#F4F8FB", cx, 8, 10, 2);
      R("#F4F8FB", cx + 2, 7, 6, 1);
    }
    // the neighbours
    R(SKY[mode].far, 0, 30, 10, 34);
    R(SKY[mode].near, 2, 40, 8, 24);
    R(SKY[mode].far, 46, 34, 10, 30);
    R(SKY[mode].near, 47, 44, 9, 20);
    // street
    R(mode === "day" ? "#B5B1A4" : "#4A4842", 0, 61, TX - 2, 3);
    R(mode === "day" ? "#9C988C" : "#3A3832", 0, 61, TX - 2, 1);
    // tree
    R("#5A3A24", 5, 55, 1, 6);
    disc(5, 53, 3, mode === "day" ? "#4E8A52" : "#2E5A36");

    const floors = st.tower;
    const top = 50 - 4 * Math.max(0, floors.length - 1);
    // ground floor: the café
    R(mode === "day" ? "#B98A6A" : "#6A4E3C", 12, 54, 32, 7);
    for (let k = 0; k < 8; k++) R(k % 2 ? "#F4F1E8" : "#C0392B", 12 + k * 4, 54, 4, 2);
    R(mode === "day" ? "#9CC6E5" : "#F3D27A", 14, 57, 8, 3);
    R(mode === "day" ? "#9CC6E5" : "#F3D27A", 34, 57, 8, 3);
    R("#3A2618", 25, 56, 6, 5);
    // floors, bottom up
    floors.forEach((f, k) => {
      const y = 50 - 4 * k;
      if (!f.open) {
        R("#8A8F96", 12, y, 32, 3);
        for (let xx = 12; xx < 44; xx += 4) R("#6E5034", xx + ((k + Math.floor(xx / 4)) % 2), y, 1, 3);
        R("#B5824A", 12, y + 1, 32, 1);
      } else {
        R(mode === "day" ? "#C9B79C" : "#5E5446", 12, y, 32, 3);
        for (let w = 0; w < 6; w++) {
          const wx = 14 + w * 5;
          const learned = f.complete ? 6 : f.stage;
          let c;
          if (w < learned) c = f.lit ? (mode === "day" ? "#F3C969" : "#F7D77E") : mode === "day" ? "#C9A66A" : "#8A6E3A";
          else c = mode === "day" ? "#8FB8D6" : "#253049";
          R(c, wx, y, 2, 2);
        }
      }
      R(mode === "day" ? "#8A7A64" : "#3A342C", 11, y + 3, 34, 1);
      if (f.here) {
        const on = Math.floor(t * 2) % 2 === 0;
        R(on ? "#FFFFFF" : "#F3D27A", 45, y + 1, 2, 1);
        R(on ? "#FFFFFF" : "#F3D27A", 47, y, 1, 3);
        R(on ? "#FFFFFF" : "#F3D27A", 48, y - 1, 1, 5);
        R(on ? "rgba(255,255,255,.55)" : "rgba(255,240,180,.35)", 11, y - 1, 34, 1);
        R(on ? "rgba(255,255,255,.55)" : "rgba(255,240,180,.35)", 11, y + 4, 34, 1);
      }
    });
    // roof: open, or a crane still working
    const roofY = top - 3;
    R(mode === "day" ? "#9E8E76" : "#4A4238", 11, roofY + 1, 34, 2);
    if (st.roof) {
      R("#7A93A6", 32, roofY - 6, 8, 6);
      R("#5E7486", 33, roofY - 1, 1, 2);
      R("#5E7486", 38, roofY - 1, 1, 2);
      R("#3A3A40", 16, roofY - 8, 1, 9);
      if (Math.floor(t * 1.5) % 2) R("#F06A5A", 16, roofY - 9, 1, 1);
      R("#4E8A52", 22, roofY - 2, 4, 2);
    } else {
      R("#E0A23A", 40, Math.max(0, roofY - 14), 1, Math.min(14, roofY + 1));
      R("#E0A23A", 24, Math.max(0, roofY - 14), 22, 1);
      const hook = 28 + Math.round(Math.sin(t * 0.4) * 3);
      R("#3A3A40", hook, Math.max(1, roofY - 13), 1, 5);
      R("#B5824A", hook - 2, Math.max(6, roofY - 8), 5, 2);
    }
  }

  // ---- inside the floor (x 58..319)
  function drawRoom(st, mode, t, sim) {
    const f = st.floor;
    const idx = f && f.i != null ? f.i : 5;
    const pal = WALLS[idx % WALLS.length];
    const open = f && f.open;
    const stage = f ? (open ? f.stage : 0) : 0;
    const dark = !f || !f.has_deck;
    // wall
    R(pal[0], TX, 0, W - TX, 44);
    for (let y = 6, k = 0; y < 34; y += 6, k++) for (let x = TX + (k % 2 ? 3 : 0); x < W; x += 6) R(pal[1], x, y, 1, 1);
    R(shade(pal[0], -0.35), TX, 0, W - TX, 2);
    R(pal[2], TX, 34, W - TX, 10);
    for (let x = TX + 2; x < W; x += 16) {
      R(shade(pal[2], 0.08), x, 36, 12, 6);
      R(shade(pal[2], -0.15), x, 36, 12, 1);
    }
    R(shade(pal[2], -0.35), TX, 43, W - TX, 1);
    // windows
    for (const wx of [92, 178, 252]) {
      R("#A79F88", wx - 1, 5, 30, 25);
      R("#D8D0B8", wx, 6, 28, 23);
      skyBands(mode, wx + 2, 8, 24, 19);
      const s = SKY[mode];
      if (mode === "night") for (let k = 0; k < 5; k++) if (Math.sin(t + k + wx) > -0.2) R("#E8ECF8", wx + 3 + hash(k * 7 + wx) * 22, 9 + hash(k * 3 + wx) * 8, 1, 1);
      if (mode === "day") {
        const cx = wx + 2 + ((t * 0.8 + wx) % 34) - 6;
        if (cx > wx && cx < wx + 20) R("#F4F8FB", cx, 11, 6, 1);
      }
      for (let k = 0; k < 6; k++) R(s.far, wx + 2 + k * 4, 27 - 3 - hash(k + wx) * 7, 4, 10);
      R(s.near, wx + 2, 23, 24, 4);
      R("#D8D0B8", wx + 13, 8, 2, 19);
      R("#D8D0B8", wx + 2, 16, 24, 1);
      R("#C9C0A6", wx - 3, 29, 34, 2);
    }
    // the floor
    R("#7A5536", TX, 44, W - TX, 18);
    for (let y = 44; y < 62; y += 4) {
      R("#6A4930", TX, y, W - TX, 1);
      for (let x = TX + ((y / 4) % 2) * 17; x < W; x += 34) R("#62432C", x, y + 1, 1, 3);
    }
    R("#3A2618", TX, 62, W - TX, 2);
    // the door to the stairs
    R("#4E3220", 299, 18, 16, 26);
    R("#6B4428", 300, 19, 14, 25);
    R("#E0AE4C", 311, 31, 2, 2);

    if (!open && f) {
      // still being built
      R("rgba(30,30,30,.35)", TX, 0, W - TX, 62);
      for (let x = TX + 6; x < 296; x += 30) {
        R("#B5824A", x, 6, 2, 50);
        R("#B5824A", x + 14, 6, 2, 50);
        R("#8A6A3A", x, 20, 16, 1);
        R("#8A6A3A", x, 36, 16, 1);
        for (let k = 0; k < 14; k++) R("#8A6A3A", x + k, 6 + k * 2, 1, 2);
      }
      for (const cx of [120, 200, 260]) {
        R("#E06A2A", cx, 52, 5, 8);
        R("#F4F1E8", cx, 55, 5, 1);
        R("#3A2618", cx - 1, 60, 7, 1);
      }
      sim.you.pile = Math.min(6, Math.floor(sim.rights / 2));
      drawSeated(YOU, DESKS[0], t, sim.you);
      drawDesk(DESKS[0], { pile: sim.you.pile });
      return;
    }
    if (dark) R("rgba(10,12,20,.55)", TX, 0, W - TX, 62);

    // the sign of the floor
    R("#2A1F17", 132, 7, 36, 22);
    R("#B47E25", 132, 7, 36, 1);
    R("#B47E25", 132, 28, 36, 1);
    R("#B47E25", 132, 7, 1, 22);
    R("#B47E25", 167, 7, 1, 22);
    const label = f && f.i != null ? String(f.i + 1) : "+";
    drawText(label, 150 - Math.floor(textWidth(label, 2) / 2), 10, f && f.complete ? "#F7D77E" : "#F4F1E8", 2);
    if (f && f.total) {
      const p = Math.max(0, Math.min(1, f.learned / f.total));
      R("#4A3A2C", 136, 23, 28, 2);
      R(f.complete ? "#F7D77E" : "#55B884", 136, 23, Math.max(1, Math.round(28 * p)), 2);
    } else drawText("SEM", 144, 22, "#8EA29A");
    if (f && f.complete) {
      R("#F7D77E", 146, 2, 8, 4);
      R("#E0AE4C", 148, 6, 4, 1);
      if (Math.floor(t * 2) % 2) R("#FFFFFF", 147, 2, 1, 1);
    }
    // lamps
    for (const lx of [120, 220]) {
      R("#2A2522", lx, 2, 1, 5);
      R(dark ? "#3A3530" : "#E0AE4C", lx - 3, 7, 7, 2);
      if (!dark && mode !== "day") {
        G.fillStyle = "rgba(255,214,140,.10)";
        G.beginPath();
        G.moveTo(lx - 3, 9);
        G.lineTo(lx + 4, 9);
        G.lineTo(lx + 22, 62);
        G.lineTo(lx - 21, 62);
        G.fill();
      }
    }
    if (stage >= 2) {
      // bookshelf
      R("#3B2516", 62, 10, 24, 34);
      R("#4E3220", 63, 11, 22, 32);
      const rows = stage >= 5 ? 4 : stage >= 3 ? 3 : 2;
      for (let i = 0; i < 4; i++) {
        const sy = 11 + i * 8;
        R("#2B1A0F", 63, sy, 22, 7);
        if (i < rows) for (let bx = 64, k = 0; bx < 84; k++) {
          const bw = 2 + (hash(k * 7 + i * 31 + idx) > 0.6 ? 1 : 0);
          const bh = 5 + (hash(k * 13 + i) > 0.5 ? 1 : 0);
          R(BOOKS[Math.floor(hash(k * 3 + i * 11 + idx * 5) * BOOKS.length)], bx, sy + 7 - bh, bw, bh);
          bx += bw + (hash(k + i * 5) > 0.8 ? 1 : 0);
        }
        R("#5E3C26", 63, sy + 7, 22, 1);
      }
      if (f.complete) {
        R("#F7D77E", 71, 5, 6, 3);
        R("#E0AE4C", 73, 8, 2, 2);
      }
    }
    if (stage >= 3) {
      // rug and plants
      R("#3F5470", 116, 52, 140, 9);
      R("#D8CBB0", 117, 53, 138, 1);
      R("#D8CBB0", 117, 59, 138, 1);
      for (const [px, h] of [[88, 7], [210, 9]]) {
        R("#A9542F", px - 3, 37, 7, 6);
        R("#C2683E", px - 4, 37, 9, 1);
        R("#4E8A52", px - 3, 37 - h, 2, h);
        R("#3E7A4A", px, 37 - h - 2, 2, h + 2);
        R("#5C9A5E", px + 2, 37 - h + 2, 2, h - 2);
      }
    }
    if (stage >= 4) {
      // coffee corner and a picture
      R("#4E3220", 220, 34, 26, 10);
      R("#6B4428", 220, 34, 26, 2);
      R("#2A2A30", 224, 26, 7, 8);
      R(Math.floor(t * 2) % 2 ? "#F06A5A" : "#8A3A30", 229, 28, 1, 1);
      R("#F2EEE3", 234, 31, 3, 3);
      R("#F2EEE3", 239, 31, 3, 3);
      R("#B47E25", 214, 10, 18, 13);
      R("#9CC6E5", 216, 12, 14, 9);
      R("#4E8A52", 216, 17, 14, 4);
      disc(225, 15, 2, "#F6C27A");
    }
    if (stage >= 5) {
      for (let x = TX + 4; x < 296; x += 8) {
        const y = 3 + (Math.floor(x / 8) % 2);
        R("#3A3A40", x, y - 1, 8, 1);
        const c = ["#F06A5A", "#F7D77E", "#55B884", "#9CC6E5"][Math.floor(x / 8) % 4];
        R(Math.floor(t * 2 + x / 8) % 3 ? c : shade(c, -0.4), x + 3, y, 2, 2);
      }
    }
    // students and you
    const seats = sim.students.length;
    for (let k = 0; k < seats; k++) {
      const s = sim.students[k];
      if (s.away) drawDesk(DESKS[k + 1], { mug: s.mug });
      else {
        drawSeated(s.L, DESKS[k + 1], t, s);
        drawDesk(DESKS[k + 1], { mug: s.mug });
      }
    }
    sim.you.pile = Math.min(6, Math.floor(sim.rights / 2));
    drawSeated(YOU, DESKS[0], t, sim.you);
    drawDesk(DESKS[0], { pile: sim.you.pile, mug: stage >= 4 });
    // someone going for coffee
    for (const s of sim.students) if (s.away) drawStanding(s.L, s.x, 61, t, s.walking);
    if (sim.cat && stage >= 4) {
      const c = sim.cat;
      const cx = Math.round(c.x);
      R("#3A3330", cx, 57, 8, 3);
      R("#3A3330", cx + (c.dir > 0 ? 7 : -2), 55, 3, 3);
      R("#3A3330", cx + (c.dir > 0 ? 7 : -2), 54, 1, 1);
      R("#3A3330", cx + (c.dir > 0 ? 9 : 0), 54, 1, 1);
      R("#3A3330", cx + (c.dir > 0 ? -2 : 8), 56 + (Math.floor(t * 2) % 2), 2, 1);
      if (c.walking) {
        R("#3A3330", cx + 1, 60, 1, 1 + (Math.floor(t * 6) % 2));
        R("#3A3330", cx + 6, 60, 1, 2 - (Math.floor(t * 6) % 2));
      }
    }
  }

  // ---- what lives in the room
  function makeSim() {
    return {
      you: { phase: 0.4, act: "type", cheer: 0, look: 0 },
      students: [],
      rights: 0,
      bubbles: [],
      parts: [],
      floats: [],
      cat: { x: 140, dir: 1, walking: false, until: 0 },
      nextChat: 0,
    };
  }

  function fitStudents(sim, stage) {
    const want = Math.max(0, Math.min(4, stage - 1));
    while (sim.students.length < want) {
      const k = sim.students.length;
      sim.students.push({ L: STUDENTS[k], act: STUDENTS[k].act, phase: k * 1.7, cheer: 0, look: 0, mug: k % 2 === 0, book: BOOKS[k * 3], next: 0, away: false, x: DESKS[k + 1], walking: false });
    }
    sim.students.length = want;
  }

  function create(canvas, opts) {
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    const motion = opts && opts.motion ? opts.motion : () => true;
    let st = null;
    let sim = makeSim();
    let floorKey = "";
    let raf = 0;
    let last = 0;
    let t0 = performance.now();

    function draw(now) {
      const t = (now - t0) / 1000;
      G = ctx;
      const mode = skyMode();
      ctx.clearRect(0, 0, W, H);
      if (!st) return;
      drawTower(st, mode, t);
      R("#1B2623", TX - 2, 0, 2, H);
      drawRoom(st, mode, t, sim);
      for (const b of sim.bubbles) bubble(b.x, b.bottom, b);
      for (const p of sim.parts) R(p.c, p.x, p.y, p.s || 1, p.s || 1);
      for (const fl of sim.floats) drawText(fl.text, Math.round(fl.x - textWidth(fl.text) / 2), Math.round(fl.y), fl.c);
    }

    function tick(dt, now) {
      const nowS = now / 1000;
      sim.bubbles = sim.bubbles.filter((b) => b.until > nowS);
      for (const p of sim.parts) {
        p.vy += (p.g || 30) * dt;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.life -= dt;
      }
      sim.parts = sim.parts.filter((p) => p.life > 0 && p.y < H + 2);
      for (const fl of sim.floats) {
        fl.y -= 8 * dt;
        fl.life -= dt;
      }
      sim.floats = sim.floats.filter((fl) => fl.life > 0);
      for (const who of [sim.you, ...sim.students]) {
        if (who.cheer > 0) who.cheer -= dt;
        if (who.sip > 0) who.sip -= dt;
        if (who.stretch > 0) who.stretch -= dt;
      }
      // the students' own lives: a sip, a stretch, a word with the neighbour, a coffee
      for (const s of sim.students) {
        if (s.away) {
          const target = s.back ? s.home : 232;
          const d = target - s.x;
          s.walking = Math.abs(d) > 0.5;
          if (s.walking) s.x += Math.sign(d) * Math.min(Math.abs(d), 18 * dt);
          else if (!s.back) {
            if (!s.waitUntil) s.waitUntil = nowS + rnd(2, 4);
            if (nowS > s.waitUntil) s.back = true;
          } else {
            s.away = false;
            s.back = false;
            s.waitUntil = 0;
            s.next = nowS + rnd(6, 14);
          }
          continue;
        }
        if (nowS < s.next) continue;
        s.next = nowS + rnd(6, 16);
        const r = Math.random();
        if (r < 0.3) s.sip = 1.6;
        else if (r < 0.42) s.stretch = 1.3;
        else if (r < 0.56 && st && st.floor && st.floor.stage >= 4 && !sim.students.some((o) => o.away)) {
          s.away = true;
          s.home = DESKS[sim.students.indexOf(s) + 1];
          s.x = s.home;
        } else if (r < 0.8) sim.bubbles.push({ x: DESKS[sim.students.indexOf(s) + 1], bottom: 30, icon: pick(["note", "book", "coffee", "bulb"]), until: nowS + 2.2 });
        else s.look = s.look ? 0 : pick([-1, 1]);
      }
      const c = sim.cat;
      if (c.walking) {
        c.x += c.dir * 10 * dt;
        if (c.x < 120 || c.x > 250) {
          c.dir *= -1;
          c.walking = false;
          c.until = nowS + rnd(10, 25);
        }
      } else if (nowS > c.until) {
        c.walking = true;
        c.until = 0;
      }
    }

    function loop(now) {
      raf = requestAnimationFrame(loop);
      if (now - last < 66) return; // about 15 frames a second is plenty for pixels
      const dt = Math.min(0.2, (now - (last || now)) / 1000);
      last = now;
      tick(dt, now);
      draw(now);
    }

    function start() {
      if (raf || !motion()) {
        draw(performance.now());
        return;
      }
      last = 0;
      raf = requestAnimationFrame(loop);
    }
    function stop() {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    }

    function set(state) {
      st = state;
      const f = state.floor;
      const key = f ? `${f.name}|${f.i}` : "";
      if (key !== floorKey) {
        sim = makeSim();
        floorKey = key;
      }
      sim.rights = state.session && state.session.results ? state.session.results.filter(Boolean).length : 0;
      fitStudents(sim, f && f.open ? f.stage : 0);
      if (!motion()) draw(performance.now());
    }

    function confetti(n, x0, x1) {
      const colors = ["#F06A5A", "#F7D77E", "#55B884", "#9CC6E5", "#E9A3B5", "#FFFFFF"];
      for (let k = 0; k < n; k++) sim.parts.push({ x: rnd(x0, x1), y: rnd(-6, 4), vx: rnd(-12, 12), vy: rnd(0, 20), g: 22, c: pick(colors), life: rnd(1.6, 2.6), s: Math.random() < 0.3 ? 2 : 1 });
    }
    function sparkle(cx, cy, n, c) {
      for (let k = 0; k < n; k++) {
        const a = (k / n) * Math.PI * 2;
        sim.parts.push({ x: cx, y: cy, vx: Math.cos(a) * rnd(12, 26), vy: Math.sin(a) * rnd(12, 26) - 8, g: 18, c: c || "#F7D77E", life: rnd(0.6, 1.1) });
      }
    }

    // things that just happened, from the panel
    function react(events) {
      if (!events || !events.length || !motion()) {
        if (!motion()) draw(performance.now());
        return;
      }
      const nowS = performance.now() / 1000;
      const you = DESKS[0];
      for (const ev of events) {
        if (ev.type === "xp") {
          sim.floats.push({ text: "+" + ev.n, x: you, y: 26, c: ev.bonus ? "#F7D77E" : ev.right ? "#9BE3B8" : "#C9D3EC", life: 1.4 });
          if (!ev.right) sim.bubbles.push({ x: you, bottom: 30, icon: "q", until: nowS + 1.4 });
        } else if (ev.type === "combo") {
          const k = sim.students.length ? Math.floor(Math.random() * sim.students.length) : -1;
          const at = k >= 0 ? DESKS[k + 1] : you;
          sim.bubbles.push({ x: at, bottom: 30, text: "X" + ev.n, color: "#C0392B", until: nowS + 2.4 });
          for (const s of sim.students) s.look = DESKS[sim.students.indexOf(s) + 1] > you ? -1 : 1;
          setTimeout(() => sim.students.forEach((s) => (s.look = 0)), 2400);
          if (ev.n >= 10) {
            sim.you.cheer = 1.2;
            sparkle(you, 30, 14);
          }
        } else if (ev.type === "level" || ev.type === "goal") {
          confetti(70, TX + 4, W - 4);
          sim.you.cheer = 1.6;
          sim.students.forEach((s) => (s.cheer = 1.6));
        } else if (ev.type === "unlock") {
          confetti(30, 0, TX);
        } else if (ev.type === "stage" || ev.type === "badge") {
          sparkle(150, 18, 18);
          sparkle(you, 34, 10, "#9BE3B8");
        } else if (ev.type === "learned") {
          sim.floats.push({ text: "+1", x: 150, y: 20, c: "#9BE3B8", life: 1.2 });
          sparkle(150, 24, 8, "#9BE3B8");
        } else if (ev.type === "record") {
          sparkle(you, 30, 16, "#F06A5A");
          sim.you.cheer = 1.2;
        }
      }
    }

    function destroy() {
      stop();
    }

    return { set, react, start, stop, destroy, draw: () => draw(performance.now()) };
  }

  window.Predio = { create, W, H };
})();
