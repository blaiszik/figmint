import React, { useLayoutEffect, useRef, useState } from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import assets from "./agent_assets.json";

// A 40-second film about what an agent's reply can look like with mintchip and mintfig.
// Everything inside the chat window and the terminal is real output (make_agent_assets.py):
// mintchip's HTML chips, popover text and table; mintfig's interactive figure fragment, whose
// hover and click are reproduced here with the page script's own tooltip and citation rules.

export const AGENT_FPS = 30;
const S = {
  hook: [0, 90],
  wall: [90, 300],
  chips: [300, 500],
  table: [500, 680],
  figure: [680, 940],
  term: [940, 1080],
  cta: [1080, 1200],
} as const;
export const AGENT_DURATION = S.cta[1];

const C = {
  bg: "#0B1020",
  ink: "#EEF2FA",
  muted: "#93A0BC",
  mint: "#34D8A0",
  amber: "#F6B941",
  line: "#22304F",
  page: "#FFFFFF",
  pageInk: "#1A1D21",
  pageMuted: "#5B6570",
  pageLine: "#E3E7EC",
  bubble: "#EEF1F5",
  term: "#0E1219",
};
const SANS = '-apple-system, "SF Pro Display", "Helvetica Neue", Helvetica, Arial, sans-serif';
const UI = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';
const MONO = '"SF Mono", Menlo, "JetBrains Mono", Consolas, monospace';

// The chat window, in its own CSS pixels. The reply column is 700 px: mintfig's chat width.
const WIN = { w: 780, h: 700, bar: 38, input: 64, pad: 40 };
const AREA_H = WIN.h - WIN.bar - WIN.input;
// Fixed tops inside the scrolling message column, so nothing reflows between scenes.
const TOP = { user1: 20, reply1: 76, user2: 470, reply2: 528 };
const SCROLL2 = 448;

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.33, 0, 0.2, 1);
const ramp = (f: number, a: number, b: number) => interpolate(f, [a, b], [0, 1], { ...clamp, easing: ease });
const within = (f: number, [a, b]: readonly [number, number]) => f >= a && f < b;

const useLayout = () => {
  const { width, height } = useVideoConfig();
  const square = width / height < 1.3;
  // The viewport that frames the window, and the caption block beside or above it.
  const view = square ? { x: 40, y: 262, w: 1000, h: 790 } : { x: 650, y: 30, w: 1240, h: 1020 };
  const cap = square ? { x: 64, y: 54, w: 952 } : { x: 80, y: 0, w: 530 };
  return { width, height, square, view, cap };
};

const usePop = (delay: number, damping = 16) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping, mass: 0.6 } });
};

// ------------------------------------------------------------------ backdrop and captions

const Backdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, AGENT_DURATION], [0, 80]);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(1100px 760px at ${18 + drift / 8}% ${10 + drift / 10}%, rgba(52,216,160,0.13), transparent 60%),
          radial-gradient(900px 700px at 92% 96%, rgba(127,178,255,0.12), transparent 60%), ${C.bg}`,
      }}
    />
  );
};

const CAPTIONS: { at: readonly [number, number]; eyebrow: string; title: string; body: string }[] = [
  {
    at: S.wall,
    eyebrow: "Before",
    title: `${assets.chips.numbers_before} numbers in one paragraph.`,
    body: "Which ones matter? Your agent knows. The paragraph doesn't say.",
  },
  {
    at: S.chips,
    eyebrow: "mintchip",
    title: "The shape of a number, inside the sentence.",
    body: "A trend or an interval the size of a word. Click it for the detail.",
  },
  {
    at: S.table,
    eyebrow: "mintchip table",
    title: "Three or more? One table, one scale.",
    body: "The lift column is a forest plot with a single zero line.",
  },
  {
    at: S.figure,
    eyebrow: "mintfig",
    title: "A figure that states the result.",
    body: "Laid out for a 700 px chat column. Hover a mark for its value, click to cite it back.",
  },
  {
    at: S.term,
    eyebrow: "Any terminal",
    title: "No images? The same report in text.",
    body: "Every chip, table and figure has a plain-text form.",
  },
];

const Caption: React.FC = () => {
  const frame = useCurrentFrame();
  const { square, cap, height } = useLayout();
  const c = CAPTIONS.find((k) => within(frame, k.at));
  if (!c) return null;
  const [a, b] = c.at;
  const inP = ramp(frame, a + 4, a + 22);
  const out = 1 - ramp(frame, b - 12, b);
  const body = ramp(frame, a + 14, a + 32);
  return (
    <div
      style={{
        position: "absolute",
        left: cap.x,
        top: square ? cap.y : 0,
        width: cap.w,
        height: square ? undefined : height,
        display: "flex",
        flexDirection: "column",
        justifyContent: square ? "flex-start" : "center",
        opacity: inP * out,
        transform: `translateY(${(1 - inP) * 24}px)`,
        fontFamily: SANS,
      }}
    >
      <div
        style={{
          color: c.eyebrow === "Before" ? C.amber : C.mint,
          fontSize: square ? 26 : 30,
          fontWeight: 700,
          letterSpacing: 2.5,
          textTransform: "uppercase",
          fontFamily: c.eyebrow.startsWith("mint") ? MONO : SANS,
        }}
      >
        {c.eyebrow}
      </div>
      <div
        style={{
          color: C.ink,
          fontSize: square ? 48 : 64,
          fontWeight: 760,
          lineHeight: 1.08,
          letterSpacing: -1,
          marginTop: square ? 10 : 18,
        }}
      >
        {c.title}
      </div>
      <div
        style={{
          color: C.muted,
          fontSize: square ? 27 : 32,
          lineHeight: 1.35,
          marginTop: square ? 10 : 24,
          opacity: body,
        }}
      >
        {c.body}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ hook

const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { square } = useLayout();
  const a = usePop(4);
  const b = usePop(36);
  const out = 1 - ramp(frame, S.hook[1] - 12, S.hook[1]);
  const size = square ? 74 : 92;
  return (
    <AbsoluteFill
      style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", opacity: out, fontFamily: SANS }}
    >
      <div style={{ color: C.ink, fontSize: size, fontWeight: 760, letterSpacing: -1.5, opacity: a, transform: `translateY(${(1 - a) * 30}px)`, textAlign: "center" }}>
        Your agent ran the experiment.
      </div>
      <div style={{ color: C.amber, fontSize: size, fontWeight: 760, letterSpacing: -1.5, marginTop: 14, opacity: b, transform: `translateY(${(1 - b) * 30}px)`, textAlign: "center" }}>
        Then it sent you a paragraph.
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ chat window

const Html: React.FC<{ html: string; style?: React.CSSProperties; className?: string }> = React.memo(
  ({ html, style, className }) => <div className={className} style={style} dangerouslySetInnerHTML={{ __html: html }} />,
);

/** The wall-of-text reply, with every number lit in turn. */
const Wall: React.FC<{ frame: number }> = ({ frame }) => {
  const text = (
    "The ablation finished (5 seeds, 8k steps each). Retrieval did best: validation loss went from 1.84 to 1.32, " +
    "0.96, 0.74, 0.61, 0.52, 0.46, 0.43 and finally 0.42, which is inside the 0.38–0.48 target band, and accuracy " +
    "reached 0.82, a lift of +0.08 over the baseline (95% CI +0.05 to +0.11). The reranker reached 0.79 accuracy " +
    "(+0.05, 95% CI +0.02 to +0.08) with a final validation loss of 0.51. Warmup reached 0.75 (+0.01, 95% CI −0.02 " +
    "to +0.04), so its effect is not distinguishable from zero; its validation loss ended at 0.70. The baseline " +
    "reached 0.74 accuracy and a final validation loss of 0.78."
  );
  const [a] = S.wall;
  const shown = Math.floor(interpolate(frame, [a + 30, a + 92], [0, text.length], clamp));
  const parts = text.split(/([-+−]?\d+(?:\.\d+)?)/);
  let pos = 0;
  let idx = 0;
  const out: React.ReactNode[] = [];
  parts.forEach((p, i) => {
    const start = pos;
    pos += p.length;
    if (start >= shown) return;
    const vis = p.slice(0, Math.max(0, shown - start));
    if (i % 2) {
      const lit = frame >= a + 104 + idx * 2.4;
      idx += 1;
      out.push(
        <span
          key={i}
          style={{
            background: lit ? "rgba(246,185,65,0.42)" : "transparent",
            borderRadius: 3,
            boxShadow: lit ? "0 0 0 1.5px rgba(246,185,65,0.42)" : "none",
          }}
        >
          {vis}
        </span>,
      );
    } else out.push(<span key={i}>{vis}</span>);
  });
  return <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6 }}>{out}</p>;
};

type Pt = { x: number; y: number; w: number; h: number };

const Cursor: React.FC<{ x: number; y: number; press: number }> = ({ x, y, press }) => (
  <svg
    width={22}
    height={26}
    viewBox="0 0 22 26"
    style={{ position: "absolute", left: x - 3, top: y - 2, zIndex: 20, transform: `scale(${1 - press * 0.15})`, transformOrigin: "3px 2px", filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.35))" }}
  >
    <path d="M3 2 L3 21 L8 16.5 L11.5 24 L14.6 22.6 L11.2 15.3 L18 15.3 Z" fill="#111" stroke="#fff" strokeWidth={1.6} strokeLinejoin="round" />
  </svg>
);

/** Position of an element relative to `root`, in `root`'s own (untransformed) CSS pixels. */
const rel = (el: Element, root: HTMLElement): Pt => {
  const o = root.getBoundingClientRect();
  const s = o.width / root.offsetWidth || 1;
  const b = el.getBoundingClientRect();
  return { x: (b.left - o.left) / s, y: (b.top - o.top) / s, w: b.width / s, h: b.height / s };
};

const ChatWindow: React.FC = () => {
  const frame = useCurrentFrame();
  const col = useRef<HTMLDivElement>(null);
  const prose = useRef<HTMLDivElement>(null);
  const fig = useRef<HTMLDivElement>(null);
  const [pts, setPts] = useState<{ chip?: Pt; mark?: Pt; pop?: string }>({});

  // Measure once: the interval chip, its popover text, and the hovered mark of the figure.
  useLayoutEffect(() => {
    if (!col.current) return;
    const root = col.current;
    const ciChip = prose.current?.querySelector(".mc-ci .mc-open");
    const pop = prose.current?.querySelector(".mc-ci .mc-pop");
    const marks = Array.from(fig.current?.querySelectorAll(`[data-mf="${assets.figure.hover_key}"]`) ?? []);
    const mark = marks.find((m) => m.getBoundingClientRect().width > 0);
    setPts({
      chip: ciChip ? rel(ciChip, root) : undefined,
      mark: mark ? rel(mark, root) : undefined,
      pop: pop?.innerHTML,
    });
  }, []);

  // Chips pop in one after the other; the mintfig tooltip and citation note follow the page
  // script's own rules (tooltip centred above the mark, "copied: <cite>" after a click).
  useLayoutEffect(() => {
    const chips = Array.from(prose.current?.querySelectorAll<HTMLElement>(".mc") ?? []);
    chips.forEach((el, i) => {
      const p = ramp(frame, S.chips[0] + 22 + i * 16, S.chips[0] + 36 + i * 16);
      el.style.display = "inline-block";
      el.style.opacity = String(p);
      el.style.transform = `scale(${0.7 + 0.3 * p})`;
      el.style.transformOrigin = "left center";
      const open = el.querySelector<HTMLElement>(".mc-open");
      if (open) {
        const lit = i === 1 && frame >= POP_AT && frame < POP_END;
        open.style.textDecoration = lit ? "underline dotted 1px" : "none";
        open.style.textUnderlineOffset = ".22em";
      }
    });
    const R = fig.current?.querySelector<HTMLElement>(".mf-root");
    const tip = R?.querySelector<HTMLElement>(".mf-tip");
    const note = R?.querySelector<HTMLElement>(".mf-note");
    const marks = Array.from(R?.querySelectorAll(`[data-mf="${assets.figure.hover_key}"]`) ?? []);
    const mark = marks.find((m) => m.getBoundingClientRect().width > 0);
    if (R && tip && mark) {
      const on = frame >= HOVER_AT;
      tip.hidden = !on;
      (mark as SVGElement).style.stroke = on ? "var(--mf-ui-ink)" : "";
      (mark as SVGElement).style.strokeWidth = on ? "1.2" : "";
      if (on) {
        tip.textContent = mark.getAttribute("aria-label");
        const b = rel(mark, R);
        const x = b.x + b.w / 2 - tip.offsetWidth / 2;
        const y = b.y - tip.offsetHeight - 6;
        tip.style.left = `${Math.max(0, Math.min(x, R.clientWidth - tip.offsetWidth))}px`;
        tip.style.top = `${y < 0 ? b.y + b.h + 6 : y}px`;
      }
    }
    if (note) note.textContent = frame >= CLICK_AT ? `copied: ${assets.figure.cite}` : "";
  }, [frame]);

  // Scroll to the second exchange.
  // ...and a little further at the click, so the figure's own "copied: …" line shows.
  const scroll = SCROLL2 * ramp(frame, S.figure[0] + 2, S.figure[0] + 28) + 76 * ramp(frame, CLICK_AT - 6, CLICK_AT + 10);
  const wallOut = 1 - ramp(frame, S.chips[0], S.chips[0] + 14);
  const proseIn = ramp(frame, S.chips[0] + 8, S.chips[0] + 22);
  const tableIn = usePop(S.table[0] + 6);
  const user2 = usePop(S.figure[0] + 14);
  const reply2 = ramp(frame, S.figure[0] + 34, S.figure[0] + 50);
  const figIn = ramp(frame, S.figure[0] + 42, S.figure[0] + 64);
  const user1 = usePop(S.wall[0] + 14);

  // The cursor: to the interval chip, click; later to the mark, click.
  const cur = cursorAt(frame, pts);

  // What the input box says: a typed question, then the pasted citation.
  const typed = inputText(frame);

  const userBubble = (text: string, p: number, top: number) => (
    <div style={{ position: "absolute", top, right: 0, maxWidth: 520, opacity: p, transform: `translateY(${(1 - p) * 14}px)` }}>
      <div style={{ background: C.bubble, borderRadius: 16, padding: "9px 15px", fontSize: 15 }}>{text}</div>
    </div>
  );
  const who = (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 650, color: C.pageMuted, marginBottom: 8 }}>
      <span style={{ width: 18, height: 18, borderRadius: 5, background: "linear-gradient(135deg,#34D8A0,#2A9DD8)", display: "inline-block" }} />
      Agent
    </div>
  );

  return (
    <div
      style={{
        width: WIN.w,
        height: WIN.h,
        background: C.page,
        borderRadius: 14,
        overflow: "hidden",
        position: "relative",
        color: C.pageInk,
        fontFamily: UI,
        boxShadow: "0 40px 90px rgba(0,0,0,0.5)",
      }}
    >
      <style>{assets.chips.css}</style>
      {/* title bar */}
      <div style={{ height: WIN.bar, borderBottom: `1px solid ${C.pageLine}`, display: "flex", alignItems: "center", padding: "0 14px", gap: 8, background: "#F7F8FA" }}>
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <span key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c, display: "inline-block" }} />
        ))}
        <span style={{ flex: 1, textAlign: "center", fontSize: 13, color: C.pageMuted, marginRight: 52 }}>agent · ablation-study</span>
      </div>
      {/* messages */}
      <div style={{ position: "absolute", top: WIN.bar, left: 0, right: 0, height: AREA_H, overflow: "hidden" }}>
        <div ref={col} style={{ position: "absolute", left: WIN.pad, width: WIN.w - 2 * WIN.pad, top: -scroll }}>
          {userBubble("How did the ablation go?", user1, TOP.user1)}
          <div style={{ position: "absolute", top: TOP.reply1, left: 0, right: 0 }}>
            {who}
            <div style={{ position: "relative" }}>
              <div style={{ position: "absolute", inset: 0, opacity: wallOut }}>
                {frame < S.chips[0] + 16 && <Wall frame={frame} />}
              </div>
              <div ref={prose} style={{ opacity: proseIn }}>
                <Html html={`<p style="margin:0;font-size:15px;line-height:1.6">${assets.chips.prose_html}</p>`} />
              </div>
              <div style={{ marginTop: 16, opacity: tableIn, transform: `translateY(${(1 - tableIn) * 16}px)`, fontSize: 15 }}>
                <Html html={assets.chips.table_html} />
              </div>
            </div>
          </div>
          {userBubble("Can I see the loss curves?", user2, TOP.user2)}
          <div style={{ position: "absolute", top: TOP.reply2, left: 0, right: 0, opacity: reply2 }}>
            {who}
            <p style={{ margin: "0 0 10px", fontSize: 15, lineHeight: 1.6 }}>Here is validation loss for all four variants:</p>
            <div ref={fig} style={{ opacity: figIn }}>
              <Html html={assets.figure.fragment} />
            </div>
          </div>
          {/* popover for the interval chip: mintchip's own popover text, under the chip */}
          {pts.chip && pts.pop && within(frame, [POP_AT, POP_END]) && (
            <div
              style={{
                position: "absolute",
                left: pts.chip.x,
                top: pts.chip.y + pts.chip.h + 5,
                padding: ".35em .6em .4em",
                maxWidth: "22em",
                border: "1px solid rgba(26,29,33,0.22)",
                borderRadius: 3,
                background: "#fff",
                fontSize: 15 * 0.84,
                lineHeight: 1.45,
                boxShadow: "0 6px 18px rgba(0,0,0,0.12)",
                zIndex: 10,
                opacity: ramp(frame, POP_AT, POP_AT + 5),
              }}
              dangerouslySetInnerHTML={{ __html: pts.pop }}
            />
          )}
          {cur && <Cursor x={cur.x} y={cur.y} press={cur.press} />}
        </div>
      </div>
      {/* input */}
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: WIN.input, padding: "10px 24px 14px", boxSizing: "border-box" }}>
        <div
          style={{
            height: "100%",
            border: `1px solid ${typed.active ? "#9DB7E0" : C.pageLine}`,
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            padding: "0 14px",
            fontSize: 14.5,
            color: typed.text ? C.pageInk : "#9AA3AD",
            whiteSpace: "nowrap",
            overflow: "hidden",
          }}
        >
          {typed.text ? (
            <span>
              {typed.cite && <span style={{ background: "#E8F0FC", borderRadius: 4, padding: "1px 5px", fontFamily: MONO, fontSize: 12.5 }}>{typed.cite}</span>}
              {typed.text}
              {typed.active && <span style={{ opacity: Math.floor(frame / 8) % 2 ? 0 : 1 }}>▍</span>}
            </span>
          ) : (
            "Message your agent…"
          )}
        </div>
      </div>
    </div>
  );
};

const POP_AT = S.chips[0] + 112;
const POP_END = S.chips[1] - 8;
const HOVER_AT = S.figure[0] + 150;
const CLICK_AT = S.figure[0] + 176;

function cursorAt(frame: number, pts: { chip?: Pt; mark?: Pt }) {
  const press = (at: number) => interpolate(frame, [at - 3, at, at + 4], [0, 1, 0], clamp);
  if (pts.chip && within(frame, [S.chips[0] + 70, S.chips[1] - 4])) {
    const tx = pts.chip.x + pts.chip.w * 0.7;
    const ty = pts.chip.y + pts.chip.h * 0.6;
    const p = ramp(frame, S.chips[0] + 72, POP_AT - 4);
    return { x: interpolate(p, [0, 1], [tx + 160, tx]), y: interpolate(p, [0, 1], [ty + 120, ty]), press: press(POP_AT - 2) };
  }
  if (pts.mark && within(frame, [S.figure[0] + 110, S.figure[1] - 6])) {
    const tx = pts.mark.x + pts.mark.w / 2;
    const ty = pts.mark.y + pts.mark.h / 2;
    const p = ramp(frame, S.figure[0] + 112, HOVER_AT);
    return { x: interpolate(p, [0, 1], [tx + 220, tx]), y: interpolate(p, [0, 1], [ty + 150, ty]), press: press(CLICK_AT) };
  }
  return null;
}

function inputText(frame: number) {
  const q = "Can I see the loss curves?";
  const [a] = S.figure;
  // Typed before it is sent (the bubble appears at a + 14), so type it during the table scene.
  const t0 = S.table[1] - 46;
  if (frame >= t0 && frame < a + 12) {
    const n = Math.floor(interpolate(frame, [t0, t0 + 34], [0, q.length], clamp));
    return { text: q.slice(0, n), active: true, cite: "" };
  }
  if (frame >= CLICK_AT + 12) {
    const follow = " does it hold at 10 seeds?";
    const n = Math.floor(interpolate(frame, [CLICK_AT + 22, CLICK_AT + 50], [0, follow.length], clamp));
    return { text: follow.slice(0, n) || "​", active: true, cite: assets.figure.cite };
  }
  return { text: "", active: false, cite: "" };
}

// ------------------------------------------------------------------ camera

type Cam = { f: number; cy: number; z: number };

/** Keyframes: the window row to centre, and the zoom from the fitted size (z=0) to the
 *  largest size at which the whole 700 px column still fits the viewport (z=1). */
const CAMERA: Cam[] = [
  { f: S.wall[0], cy: 350, z: 0 },
  { f: S.wall[0] + 96, cy: 350, z: 0 },
  { f: S.wall[0] + 120, cy: 260, z: 1 },
  { f: S.chips[1] - 10, cy: 260, z: 1 },
  { f: S.table[0] + 30, cy: 300, z: 1 },
  { f: S.table[1] - 50, cy: 300, z: 1 },
  { f: S.table[1] - 20, cy: 350, z: 0 },
  { f: S.figure[0] + 70, cy: 350, z: 0 },
  { f: S.figure[0] + 110, cy: 380, z: 1 },
  { f: S.figure[1] - 40, cy: 420, z: 1 },
  { f: S.figure[1], cy: 350, z: 0.4 },
];

function camera(frame: number): { cy: number; z: number } {
  const k = CAMERA;
  if (frame <= k[0].f) return k[0];
  for (let i = 1; i < k.length; i++) {
    if (frame <= k[i].f) {
      const p = ramp(frame, k[i - 1].f, k[i].f);
      return { cy: k[i - 1].cy + (k[i].cy - k[i - 1].cy) * p, z: k[i - 1].z + (k[i].z - k[i - 1].z) * p };
    }
  }
  return k[k.length - 1];
}

const Stage: React.FC<{ children: React.ReactNode; fit: number; cam: { cy: number; z: number }; opacity: number; lift: number }> = ({
  children,
  fit,
  cam,
  opacity,
  lift,
}) => {
  const { view } = useLayout();
  const maxS = Math.max(1, view.w / (WIN.w * fit));
  const s = fit * (1 + (maxS - 1) * cam.z);
  // Keep the window's top and bottom edges from sliding into view past its content.
  const half = view.h / (2 * s);
  const cy = half >= WIN.h / 2 ? WIN.h / 2 : Math.min(Math.max(cam.cy, half), WIN.h - half);
  return (
    <div style={{ position: "absolute", left: view.x, top: view.y, width: view.w, height: view.h, overflow: "hidden", borderRadius: 22, opacity }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          transformOrigin: "0 0",
          transform: `translate(${view.w / 2 - (WIN.w / 2) * s}px, ${view.h / 2 - cy * s + lift}px) scale(${s})`,
        }}
      >
        {children}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ terminal

const TERM_LINES: { cmd?: string; out?: string }[] = [
  { cmd: "mintchip render reply.txt" },
  { out: assets.chips.prose_text },
  { cmd: "mintchip table runs.json --col variant --col acc:num:accuracy \\\n    --col 'lift:ci:lift, 95% CI' --col 'loss:spark:val loss' --set lift.level=0.95" },
  { out: assets.chips.table_text },
  { cmd: `python -c "import mintfig as mint; print(mint.load('loss.png').to_text())"` },
  { out: assets.figure.text.split("\n").slice(0, 8).join("\n") },
];

const Terminal: React.FC = () => {
  const frame = useCurrentFrame();
  const [a] = S.term;
  return (
    <div
      style={{
        width: WIN.w,
        height: WIN.h,
        background: C.term,
        borderRadius: 14,
        overflow: "hidden",
        boxShadow: "0 40px 90px rgba(0,0,0,0.5)",
        border: "1px solid #283247",
        fontFamily: MONO,
        color: "#D7DEEA",
      }}
    >
      <div style={{ height: WIN.bar, display: "flex", alignItems: "center", padding: "0 14px", gap: 8, background: "#151B26", borderBottom: "1px solid #232C3D" }}>
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <span key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c, display: "inline-block" }} />
        ))}
        <span style={{ flex: 1, textAlign: "center", fontSize: 13, color: "#7D8AA3", marginRight: 52, fontFamily: UI }}>zsh · ablation-study</span>
      </div>
      <div style={{ padding: "16px 20px", fontSize: 13.4, lineHeight: 1.5 }}>
        {TERM_LINES.map((l, i) => {
          const p = ramp(frame, a + 8 + i * 9, a + 14 + i * 9);
          return (
            <div key={i} style={{ opacity: p, marginTop: l.cmd && i ? 10 : 0 }}>
              {l.cmd ? (
                <div style={{ whiteSpace: "pre-wrap" }}>
                  <span style={{ color: C.mint }}>$ </span>
                  {l.cmd}
                </div>
              ) : (
                <div style={{ whiteSpace: "pre-wrap" }}>{l.out}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ call to action

const CTA: React.FC = () => {
  const frame = useCurrentFrame();
  const { square } = useLayout();
  const [a] = S.cta;
  const t = usePop(a + 4);
  const c1 = usePop(a + 18);
  const c2 = usePop(a + 28);
  const foot = ramp(frame, a + 44, a + 60);
  const fade = ramp(frame, a, a + 10);
  const card = (p: number, name: string, line: string, install: string) => (
    <div
      style={{
        opacity: p,
        transform: `translateY(${(1 - p) * 26}px)`,
        background: "rgba(18,26,46,0.9)",
        border: `2px solid ${C.line}`,
        borderRadius: 22,
        padding: square ? "26px 34px" : "34px 40px",
        width: square ? 860 : 700,
        boxSizing: "border-box",
      }}
    >
      <div style={{ fontFamily: MONO, color: C.mint, fontSize: square ? 46 : 54, fontWeight: 700 }}>{name}</div>
      <div style={{ color: C.ink, fontSize: square ? 28 : 31, marginTop: 10, lineHeight: 1.3 }}>{line}</div>
      <div style={{ fontFamily: MONO, color: C.muted, fontSize: square ? 25 : 27, marginTop: 18 }}>{install}</div>
    </div>
  );
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", fontFamily: SANS, opacity: fade }}>
      <div style={{ color: C.ink, fontSize: square ? 50 : 72, fontWeight: 780, letterSpacing: -1.2, opacity: t, transform: `translateY(${(1 - t) * 24}px)`, textAlign: "center", lineHeight: 1.1 }}>
        Give your agent a better way to answer.
      </div>
      <div style={{ display: "flex", flexDirection: square ? "column" : "row", gap: square ? 22 : 40, marginTop: square ? 44 : 64 }}>
        {card(c1, "mintchip", "Word-sized graphics for the numbers in a reply.", "github.com/blaiszik/mintchip")}
        {card(c2, "mintfig", "Figures that state the result, readable in chat.", "pip install mintfig")}
      </div>
      <div style={{ color: C.muted, fontSize: square ? 25 : 28, marginTop: square ? 36 : 52, opacity: foot, fontFamily: MONO, textAlign: "center", lineHeight: 1.5 }}>
        {square ? (
          <>
            Agent skills included · MIT
            <br />
            mintfig skill --install · mintchip guide --agents
          </>
        ) : (
          "Agent skills included · mintfig skill --install · mintchip guide --agents · MIT"
        )}
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ composition

export const AgentReply: React.FC = () => {
  const frame = useCurrentFrame();
  const { view } = useLayout();
  const fit = Math.min((view.w - 40) / WIN.w, (view.h - 40) / WIN.h);
  const cam = camera(frame);
  const chatIn = usePop(S.wall[0], 20);
  const chatOn = frame >= S.wall[0] && frame < S.term[0] + 14;
  const swap = ramp(frame, S.term[0], S.term[0] + 14);
  const termOn = frame >= S.term[0] && frame < S.term[1];
  const termOut = 1 - ramp(frame, S.term[1] - 12, S.term[1]);
  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <Backdrop />
      {within(frame, S.hook) && <Hook />}
      {chatOn && (
        <Stage fit={fit} cam={cam} opacity={chatIn * (1 - swap)} lift={(1 - chatIn) * 60}>
          <ChatWindow />
        </Stage>
      )}
      {termOn && (
        <Stage fit={fit} cam={{ cy: WIN.h / 2, z: 0 }} opacity={swap * termOut} lift={(1 - swap) * 40}>
          <Terminal />
        </Stage>
      )}
      <Caption />
      {frame >= S.cta[0] && <CTA />}
    </AbsoluteFill>
  );
};
