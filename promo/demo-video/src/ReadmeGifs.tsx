import React, { useLayoutEffect, useRef, useState } from "react";
import {
  AbsoluteFill,
  Composition,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import agentAssets from "./agent_assets.json";

// Dedicated high-DPI, zero-grain README GIF compositions (1280x720 @ 15 fps).
// Design choices specifically optimized for crisp 256-color GIF encoding:
// - Pure solid #0B1020 dark backdrop (no radial gradients or blurred shadows that cause banding/grain)
// - Native 1:1 pixel sizing for the 700 px chat column (no fractional CSS transform scaling on text/SVG)
// - Both mintchip inline chips AND the mintchip table appear immediately in the upgraded reply,
//   then the already-visible table receives a smooth mint highlight instead of flashing in.

export const README_W = 1280;
export const README_H = 720;
export const README_FPS = 15;
export const OPENER_DURATION = 330; // 22.0 s
export const CHECK_DURATION = 330; // 22.0 s

const C = {
  bg: "#0B1020",
  panel: "#11192E",
  term: "#0D1426",
  termBar: "#131D35",
  line: "#263659",
  ink: "#F1F5FC",
  muted: "#9AA8C4",
  mint: "#34D8A0",
  mintDark: "#149E70",
  blue: "#7FB2FF",
  amber: "#F6B941",
  red: "#FF5D6C",
  page: "#FFFFFF",
  pageInk: "#1A1D21",
  pageMuted: "#5B6570",
  pageLine: "#E2E7EE",
  bubble: "#EEF1F5",
};

const SANS = '-apple-system, "SF Pro Display", "Helvetica Neue", Helvetica, Arial, sans-serif';
const UI = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';
const MONO = '"SF Mono", Menlo, "JetBrains Mono", Consolas, monospace';

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.33, 0, 0.2, 1);
const ramp = (f: number, a: number, b: number) =>
  interpolate(f, [a, b], [0, 1], { ...clamp, easing: ease });
const within = (f: number, [a, b]: readonly [number, number]) => f >= a && f < b;

// ============================================================================
// 1. README OPENER: Wall of text -> mintchip (immediate chips + table) ->
//    mintchip table highlight -> mintfig interactive figure (hover + cite)
// ============================================================================

const OS = {
  wall: [0, 70],
  chips: [70, 152],
  table: [152, 218],
  figure: [218, 330],
} as const;

const POP_AT = 103;
const POP_END = 146;
const HOVER_AT = 264;
const CLICK_AT = 280;

// Chat window at native 1:1 CSS pixels inside 1280x720 (inner column = 722 px >= 700 px -> .mf-v2)
const WIN = { x: 454, y: 22, w: 794, h: 676, bar: 36, input: 56, pad: 36 };
const AREA_H = WIN.h - WIN.bar - WIN.input; // 584 px
const TOP = { user1: 18, reply1: 68, user2: 472, reply2: 520 };
const SCROLL2 = 458;

const Html: React.FC<{ html: string; style?: React.CSSProperties; className?: string }> = React.memo(
  ({ html, style, className }) => (
    <div className={className} style={style} dangerouslySetInnerHTML={{ __html: html }} />
  ),
);

const WallText: React.FC<{ frame: number }> = ({ frame }) => {
  const text =
    "The ablation finished (5 seeds, 8k steps each). Retrieval did best: validation loss went from 1.84 to 1.32, " +
    "0.96, 0.74, 0.61, 0.52, 0.46, 0.43 and finally 0.42, which is inside the 0.38–0.48 target band, and accuracy " +
    "reached 0.82, a lift of +0.08 over the baseline (95% CI +0.05 to +0.11). The reranker reached 0.79 accuracy " +
    "(+0.05, 95% CI +0.02 to +0.08) with a final validation loss of 0.51. Warmup reached 0.75 (+0.01, 95% CI −0.02 " +
    "to +0.04), so its effect is not distinguishable from zero; its validation loss ended at 0.70. The baseline " +
    "reached 0.74 accuracy and a final validation loss of 0.78.";

  const shown = Math.floor(interpolate(frame, [2, 30], [0, text.length], clamp));
  const parts = text.split(/([-+−]?\d+(?:\.\d+)?)/);
  let pos = 0;
  let numIdx = 0;
  const nodes: React.ReactNode[] = [];

  parts.forEach((p, i) => {
    const start = pos;
    pos += p.length;
    if (start >= shown) return;
    const vis = p.slice(0, Math.max(0, shown - start));
    if (i % 2) {
      const lit = frame >= 32 + numIdx * 0.7;
      numIdx += 1;
      nodes.push(
        <span
          key={i}
          style={{
            background: lit ? "#FDE68A" : "transparent",
            borderRadius: 3,
            padding: lit ? "0 2px" : 0,
            color: C.pageInk,
            fontWeight: lit ? 600 : 400,
          }}
        >
          {vis}
        </span>,
      );
    } else {
      nodes.push(<span key={i}>{vis}</span>);
    }
  });

  return <p style={{ margin: 0, fontSize: 15.5, lineHeight: 1.62, color: C.pageInk }}>{nodes}</p>;
};

type Pt = { x: number; y: number; w: number; h: number };

const CursorIcon: React.FC<{ x: number; y: number; press: number }> = ({ x, y, press }) => (
  <svg
    width={24}
    height={28}
    viewBox="0 0 22 26"
    style={{
      position: "absolute",
      left: x - 3,
      top: y - 2,
      zIndex: 30,
      transform: `scale(${1 - press * 0.14})`,
      transformOrigin: "3px 2px",
    }}
  >
    <path
      d="M3 2 L3 21 L8 16.5 L11.5 24 L14.6 22.6 L11.2 15.3 L18 15.3 Z"
      fill="#111827"
      stroke="#FFFFFF"
      strokeWidth={1.8}
      strokeLinejoin="round"
    />
  </svg>
);

const relPos = (el: Element, root: HTMLElement): Pt => {
  const o = root.getBoundingClientRect();
  const s = o.width / root.offsetWidth || 1;
  const b = el.getBoundingClientRect();
  return {
    x: (b.left - o.left) / s,
    y: (b.top - o.top) / s,
    w: b.width / s,
    h: b.height / s,
  };
};

function openerCursorAt(frame: number, pts: { chip?: Pt; mark?: Pt }) {
  const press = (at: number) => interpolate(frame, [at - 2, at, at + 3], [0, 1, 0], clamp);
  if (pts.chip && within(frame, [82, 148])) {
    const tx = pts.chip.x + pts.chip.w * 0.65;
    const ty = pts.chip.y + pts.chip.h * 0.55;
    const p = ramp(frame, 83, POP_AT - 2);
    return {
      x: interpolate(p, [0, 1], [tx + 140, tx]),
      y: interpolate(p, [0, 1], [ty + 96, ty]),
      press: press(POP_AT - 1),
    };
  }
  if (pts.mark && within(frame, [246, 330])) {
    const tx = pts.mark.x + pts.mark.w / 2;
    const ty = pts.mark.y + pts.mark.h / 2;
    const p = ramp(frame, 247, HOVER_AT);
    return {
      x: interpolate(p, [0, 1], [tx + 170, tx]),
      y: interpolate(p, [0, 1], [ty + 110, ty]),
      press: press(CLICK_AT),
    };
  }
  return null;
}

function openerInputText(frame: number) {
  const q = "Can I see the loss curves?";
  if (frame >= 184 && frame < 224) {
    const n = Math.floor(interpolate(frame, [184, 210], [0, q.length], clamp));
    return { text: q.slice(0, n), active: true, cite: "" };
  }
  if (frame >= CLICK_AT + 4) {
    const follow = " does it hold at 10 seeds?";
    const n = Math.floor(interpolate(frame, [CLICK_AT + 8, CLICK_AT + 26], [0, follow.length], clamp));
    return { text: follow.slice(0, n) || "\u200b", active: true, cite: agentAssets.figure.cite };
  }
  return { text: "", active: false, cite: "" };
}

const OPENER_CAPTIONS: {
  id: number;
  at: readonly [number, number];
  eyebrow: string;
  accent: string;
  title: string;
  body: string;
  pill: string;
}[] = [
  {
    id: 0,
    at: OS.wall,
    eyebrow: "Before · Wall of text",
    accent: C.amber,
    title: "32 numbers in one paragraph.",
    body: "Your agent ran the ablation, then buried the answer in prose.",
    pill: "1 Text",
  },
  {
    id: 1,
    at: OS.chips,
    eyebrow: "mintchip · Inline",
    accent: C.mint,
    title: "Numbers carry their own shape.",
    body: "Sparklines and 95% intervals sit right in the sentence — click any chip for exact bounds.",
    pill: "2 Chips",
  },
  {
    id: 2,
    at: OS.table,
    eyebrow: "mintchip · Table",
    accent: C.mint,
    title: "One table, one shared scale.",
    body: "Every variant aligns on a single zero line so non-significant runs stand out immediately.",
    pill: "3 Table",
  },
  {
    id: 3,
    at: OS.figure,
    eyebrow: "mintfig · Figure",
    accent: C.mint,
    title: "A figure that states the result.",
    body: "Sized for chat, claims checked against the data. Hover to inspect, click to cite back.",
    pill: "4 Figure",
  },
];

const OpenerSidebar: React.FC<{ frame: number }> = ({ frame }) => {
  const active =
    OPENER_CAPTIONS.find((c) => within(frame, c.at)) ?? OPENER_CAPTIONS[OPENER_CAPTIONS.length - 1];
  const [a, b] = active.at;
  const isLast = active.id === OPENER_CAPTIONS.length - 1;
  const inP = active.id === 0 ? 1 : ramp(frame, a, a + 8);
  const outP = isLast ? 1 : 1 - ramp(frame, b - 6, b);

  return (
    <div
      style={{
        position: "absolute",
        left: 36,
        top: 0,
        width: 390,
        height: README_H,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "40px 0 36px",
        boxSizing: "border-box",
        fontFamily: SANS,
      }}
    >
      {/* Top brand tag */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: 4,
            background: C.mint,
          }}
        />
        <span
          style={{
            fontFamily: MONO,
            fontSize: 16,
            fontWeight: 700,
            color: C.ink,
            letterSpacing: 0.4,
          }}
        >
          mintfig
        </span>
        <span style={{ fontFamily: MONO, fontSize: 14, color: C.muted }}>+ mintchip</span>
      </div>

      {/* Main narrative caption */}
      <div
        style={{
          opacity: inP * outP,
          transform: `translateY(${(1 - inP) * 14}px)`,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "5px 12px",
            borderRadius: 999,
            background: C.panel,
            border: `1.5px solid ${active.accent}`,
            color: active.accent,
            fontSize: 13.5,
            fontWeight: 700,
            letterSpacing: 1.4,
            textTransform: "uppercase",
            fontFamily: MONO,
          }}
        >
          {active.eyebrow}
        </div>
        <div
          style={{
            color: C.ink,
            fontSize: 40,
            fontWeight: 780,
            lineHeight: 1.09,
            letterSpacing: -0.9,
            marginTop: 18,
          }}
        >
          {active.title}
        </div>
        <div
          style={{
            color: C.muted,
            fontSize: 19,
            lineHeight: 1.45,
            marginTop: 16,
          }}
        >
          {active.body}
        </div>
      </div>

      {/* Step pills */}
      <div style={{ display: "flex", gap: 8, flexWrap: "nowrap" }}>
        {OPENER_CAPTIONS.map((step) => {
          const isCur = step.id === active.id;
          const done = step.id < active.id;
          const borderColor = isCur ? step.accent : done ? "#2B4A4A" : C.line;
          const bgColor = isCur ? "#15233D" : C.bg;
          const txtColor = isCur ? step.accent : done ? "#7CA89C" : "#6B7894";
          return (
            <div
              key={step.id}
              style={{
                padding: "5px 10px",
                borderRadius: 8,
                border: `1.5px solid ${borderColor}`,
                background: bgColor,
                color: txtColor,
                fontFamily: MONO,
                fontSize: 12.5,
                fontWeight: isCur ? 700 : 500,
                whiteSpace: "nowrap",
              }}
            >
              {step.pill}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const OpenerChatWindow: React.FC<{ frame: number }> = ({ frame }) => {
  const col = useRef<HTMLDivElement>(null);
  const prose = useRef<HTMLDivElement>(null);
  const fig = useRef<HTMLDivElement>(null);
  const [pts, setPts] = useState<{ chip?: Pt; mark?: Pt; pop?: string }>({});

  useLayoutEffect(() => {
    if (!col.current) return;
    const root = col.current;
    const ciChip = prose.current?.querySelector(".mc-ci .mc-open");
    const pop = prose.current?.querySelector(".mc-ci .mc-pop");
    const marks = Array.from(
      fig.current?.querySelectorAll(`[data-mf="${agentAssets.figure.hover_key}"]`) ?? [],
    );
    const mark = marks.find((m) => m.getBoundingClientRect().width > 0);
    setPts({
      chip: ciChip ? relPos(ciChip, root) : undefined,
      mark: mark ? relPos(mark, root) : undefined,
      pop: pop?.innerHTML,
    });
  }, []);

  // Keep BOTH inline chips at full opacity immediately (no staggered delay).
  // Only toggle the dotted underline on the CI chip while its popover is open,
  // and update the mintfig hover tooltip + click-to-cite footer.
  useLayoutEffect(() => {
    const ciOpen = prose.current?.querySelector<HTMLElement>(".mc-ci .mc-open");
    if (ciOpen) {
      const lit = frame >= POP_AT && frame < POP_END;
      ciOpen.style.textDecoration = lit ? "underline dotted 1.5px" : "none";
      ciOpen.style.textUnderlineOffset = ".22em";
      ciOpen.style.background = lit ? "#E8F4FD" : "transparent";
      ciOpen.style.borderRadius = "4px";
    }

    const R = fig.current?.querySelector<HTMLElement>(".mf-root");
    const tip = R?.querySelector<HTMLElement>(".mf-tip");
    const note = R?.querySelector<HTMLElement>(".mf-note");
    const marks = Array.from(
      R?.querySelectorAll(`[data-mf="${agentAssets.figure.hover_key}"]`) ?? [],
    );
    const mark = marks.find((m) => m.getBoundingClientRect().width > 0);
    if (R && tip && mark) {
      const on = frame >= HOVER_AT;
      tip.hidden = !on;
      (mark as SVGElement).style.stroke = on ? "var(--mf-ui-ink)" : "";
      (mark as SVGElement).style.strokeWidth = on ? "1.5" : "";
      if (on) {
        tip.textContent = mark.getAttribute("aria-label");
        const b = relPos(mark, R);
        const x = b.x + b.w / 2 - tip.offsetWidth / 2;
        const y = b.y - tip.offsetHeight - 7;
        tip.style.left = `${Math.max(0, Math.min(x, R.clientWidth - tip.offsetWidth))}px`;
        tip.style.top = `${y < 0 ? b.y + b.h + 7 : y}px`;
      }
    }
    if (note) {
      note.textContent = frame >= CLICK_AT ? `copied: ${agentAssets.figure.cite}` : "";
      note.style.color = "#149E70";
      note.style.fontWeight = "600";
    }
  }, [frame]);

  // Smooth crossfade from wall of text to the COMPLETE upgraded reply (both chips + table immediately!)
  const wallOut = 1 - ramp(frame, 68, 74);
  const upgradedIn = ramp(frame, 68, 74);

  // Smooth highlight around the ALREADY-VISIBLE table during the table beat (no flashing/popping!)
  const tableHi = ramp(frame, OS.table[0], OS.table[0] + 9) * (1 - ramp(frame, OS.table[1] - 6, OS.table[1]));

  // Scroll smoothly to the second exchange (mintfig interactive figure)
  const scroll =
    SCROLL2 * ramp(frame, OS.figure[0], OS.figure[0] + 16) +
    10 * ramp(frame, CLICK_AT - 2, CLICK_AT + 8);

  const user2In = ramp(frame, OS.figure[0] + 4, OS.figure[0] + 12);
  const reply2In = ramp(frame, OS.figure[0] + 12, OS.figure[0] + 22);

  const cur = openerCursorAt(frame, pts);
  const typed = openerInputText(frame);

  const who = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13.5,
        fontWeight: 700,
        color: C.pageMuted,
        marginBottom: 8,
      }}
    >
      <span
        style={{
          width: 18,
          height: 18,
          borderRadius: 5,
          background: C.mintDark,
          display: "inline-block",
        }}
      />
      Agent
    </div>
  );

  return (
    <div
      data-mc-scheme="light"
      data-mf-scheme="light"
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        background: C.page,
        borderRadius: 14,
        border: `1.5px solid ${C.line}`,
        overflow: "hidden",
        color: C.pageInk,
        fontFamily: UI,
        boxSizing: "border-box",
      }}
    >
      <style>
        {agentAssets.chips.css}
        {`
          .readme-table-box table.mc-table { width: 100%; font-size: 15.5px; }
          .readme-table-box.is-hi tbody tr:first-child td {
            background: #DCFCE7;
          }
          .readme-table-box.is-hi tbody tr:first-child td:first-child {
            border-radius: 5px 0 0 5px;
            font-weight: 650;
          }
          .readme-table-box.is-hi tbody tr:first-child td:last-child {
            border-radius: 0 5px 5px 0;
          }
        `}
      </style>

      {/* Window title bar */}
      <div
        style={{
          height: WIN.bar,
          borderBottom: `1px solid ${C.pageLine}`,
          display: "flex",
          alignItems: "center",
          padding: "0 14px",
          gap: 8,
          background: "#F6F8FA",
        }}
      >
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <span
            key={c}
            style={{ width: 11, height: 11, borderRadius: 6, background: c, display: "inline-block" }}
          />
        ))}
        <span
          style={{
            flex: 1,
            textAlign: "center",
            fontSize: 13,
            fontWeight: 500,
            color: C.pageMuted,
            marginRight: 48,
          }}
        >
          agent · ablation-study
        </span>
      </div>

      {/* Scrollable chat area */}
      <div
        style={{
          position: "absolute",
          top: WIN.bar,
          left: 0,
          right: 0,
          height: AREA_H,
          overflow: "hidden",
        }}
      >
        <div
          ref={col}
          style={{
            position: "absolute",
            left: WIN.pad,
            width: WIN.w - 2 * WIN.pad,
            top: -scroll,
          }}
        >
          {/* User message 1 (present immediately from frame 0) */}
          <div style={{ position: "absolute", top: TOP.user1, right: 0 }}>
            <div
              style={{
                background: C.bubble,
                borderRadius: 16,
                padding: "9px 15px",
                fontSize: 15.5,
                color: C.pageInk,
              }}
            >
              How did the ablation go?
            </div>
          </div>

          {/* Agent reply 1 */}
          <div style={{ position: "absolute", top: TOP.reply1, left: 0, right: 0 }}>
            {who}
            <div style={{ position: "relative" }}>
              {/* Before: wall of text */}
              {frame < 76 && (
                <div style={{ position: "absolute", inset: 0, opacity: wallOut }}>
                  <WallText frame={frame} />
                </div>
              )}

              {/* After: complete mintchip reply (BOTH inline chips + table immediately visible!) */}
              <div style={{ opacity: upgradedIn }}>
                <div ref={prose}>
                  <Html
                    html={`<p style="margin:0;font-size:15.5px;line-height:1.65;color:#1A1D21">${agentAssets.chips.prose_html}</p>`}
                  />
                </div>

                {/* Table is ALWAYS visible once upgraded reply appears; smoothly highlighted during OS.table */}
                <div
                  className={`readme-table-box${tableHi > 0.35 ? " is-hi" : ""}`}
                  style={{
                    marginTop: 14,
                    marginLeft: -14,
                    marginRight: -14,
                    padding: "10px 14px 12px",
                    borderRadius: 10,
                    background: tableHi > 0.01 ? `rgba(240, 253, 248, ${tableHi})` : "#FFFFFF",
                    border: `2px solid rgba(20, 158, 112, ${tableHi})`,
                    position: "relative",
                  }}
                >
                  {tableHi > 0.02 && (
                    <div
                      style={{
                        position: "absolute",
                        top: -11,
                        right: 12,
                        padding: "1px 8px",
                        borderRadius: 999,
                        background: "#149E70",
                        color: "#FFFFFF",
                        fontSize: 11.5,
                        fontWeight: 700,
                        fontFamily: MONO,
                        opacity: tableHi,
                      }}
                    >
                      shared zero-line scale · −0.03 to +0.13
                    </div>
                  )}
                  <Html html={agentAssets.chips.table_html} />
                </div>
              </div>
            </div>
          </div>

          {/* User message 2 */}
          <div
            style={{
              position: "absolute",
              top: TOP.user2,
              right: 0,
              opacity: user2In,
              transform: `translateY(${(1 - user2In) * 10}px)`,
            }}
          >
            <div
              style={{
                background: C.bubble,
                borderRadius: 16,
                padding: "9px 15px",
                fontSize: 15.5,
                color: C.pageInk,
              }}
            >
              Can I see the loss curves?
            </div>
          </div>

          {/* Agent reply 2: mintfig interactive figure */}
          <div
            style={{
              position: "absolute",
              top: TOP.reply2,
              left: 0,
              right: 0,
              opacity: reply2In,
            }}
          >
            {who}
            <p style={{ margin: "0 0 8px", fontSize: 15.5, lineHeight: 1.5, color: C.pageInk }}>
              Here is validation loss for all four variants:
            </p>
            <div ref={fig}>
              <Html html={agentAssets.figure.fragment} />
            </div>
          </div>

          {/* Crisp popover for the +0.08 CI chip */}
          {pts.chip && pts.pop && within(frame, [POP_AT, POP_END]) && (
            <div
              style={{
                position: "absolute",
                left: Math.min(pts.chip.x, 450),
                top: pts.chip.y + pts.chip.h + 6,
                padding: "7px 11px",
                maxWidth: 260,
                border: "1.5px solid #149E70",
                borderRadius: 6,
                background: "#FFFFFF",
                color: C.pageInk,
                fontSize: 13.5,
                lineHeight: 1.45,
                zIndex: 20,
                opacity: ramp(frame, POP_AT, POP_AT + 3),
              }}
              dangerouslySetInnerHTML={{ __html: pts.pop }}
            />
          )}

          {cur && <CursorIcon x={cur.x} y={cur.y} press={cur.press} />}
        </div>
      </div>

      {/* Chat input bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: WIN.input,
          padding: "8px 22px 12px",
          boxSizing: "border-box",
          background: "#FFFFFF",
          borderTop: `1px solid ${C.pageLine}`,
        }}
      >
        <div
          style={{
            height: "100%",
            border: `1.5px solid ${typed.active ? "#3B82F6" : C.pageLine}`,
            borderRadius: 10,
            display: "flex",
            alignItems: "center",
            padding: "0 13px",
            fontSize: 14.5,
            color: typed.text ? C.pageInk : "#8A94A3",
            whiteSpace: "nowrap",
            overflow: "hidden",
          }}
        >
          {typed.text ? (
            <span>
              {typed.cite && (
                <span
                  style={{
                    background: "#E8F0FC",
                    color: "#1E40AF",
                    borderRadius: 4,
                    padding: "2px 6px",
                    fontFamily: MONO,
                    fontSize: 12.5,
                    fontWeight: 600,
                    marginRight: 4,
                  }}
                >
                  {typed.cite}
                </span>
              )}
              {typed.text}
              {typed.active && <span style={{ opacity: Math.floor(frame / 5) % 2 ? 0 : 1 }}>▍</span>}
            </span>
          ) : (
            "Message your agent…"
          )}
        </div>
      </div>
    </div>
  );
};

export const ReadmeOpener: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <OpenerSidebar frame={frame} />
      <OpenerChatWindow frame={frame} />
    </AbsoluteFill>
  );
};

// ============================================================================
// 2. README CHECK: Broken Matplotlib -> mintfig check -> Fixed SHIP ->
//    mint.explain -> figure-bench v0.1 stats (1280x720, zero grain)
// ============================================================================

const CS = {
  before: [0, 74],
  check: [74, 166],
  after: [166, 224],
  explain: [224, 270],
  stats: [270, 330],
} as const;

const BadgePill: React.FC<{ children: React.ReactNode; color?: string }> = ({
  children,
  color = C.mint,
}) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      padding: "7px 18px",
      borderRadius: 999,
      background: C.panel,
      border: `1.5px solid ${color}`,
      color,
      fontFamily: MONO,
      fontSize: 15,
      fontWeight: 700,
      letterSpacing: 0.8,
      textTransform: "uppercase",
    }}
  >
    <span style={{ width: 9, height: 9, borderRadius: 5, background: color }} />
    {children}
  </div>
);

const FlatCard: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({
  children,
  style,
}) => (
  <div
    style={{
      background: "#FFFFFF",
      borderRadius: 12,
      border: `1.5px solid ${C.line}`,
      padding: 10,
      position: "relative",
      boxSizing: "border-box",
      ...style,
    }}
  >
    {children}
  </div>
);

type CheckTermLine = { text: string; color?: string; at: number; bold?: boolean; bg?: string };

const FlatTerminal: React.FC<{
  command: string;
  typeFrom: number;
  typeFrames: number;
  lines: CheckTermLine[];
  fontSize: number;
  width: number;
  title?: string;
}> = ({ command, typeFrom, typeFrames, lines, fontSize, width, title = "zsh — plot.py" }) => {
  const frame = useCurrentFrame();
  const typed = Math.round(
    interpolate(frame, [typeFrom, typeFrom + typeFrames], [0, command.length], clamp),
  );
  const doneTyping = typed >= command.length;
  const cursorOn = Math.floor(frame / 6) % 2 === 0;

  return (
    <div
      style={{
        width,
        background: C.term,
        border: `1.5px solid ${C.line}`,
        borderRadius: 12,
        overflow: "hidden",
        fontFamily: MONO,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 14px",
          borderBottom: `1px solid ${C.line}`,
          background: C.termBar,
        }}
      >
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <div key={c} style={{ width: 10, height: 10, borderRadius: 5, background: c }} />
        ))}
        <span style={{ color: C.muted, fontSize: 13.5, marginLeft: 10, fontFamily: SANS }}>
          {title}
        </span>
      </div>
      <div
        style={{
          padding: "16px 18px 18px",
          fontSize,
          lineHeight: 1.52,
          color: C.ink,
          whiteSpace: "pre-wrap",
        }}
      >
        <div>
          <span style={{ color: C.mint, fontWeight: 700 }}>$ </span>
          {command.slice(0, typed)}
          {!doneTyping || (cursorOn && lines.every((l) => frame < l.at)) ? (
            <span style={{ background: C.ink, color: C.ink }}>▌</span>
          ) : null}
        </div>
        {lines.map((l, i) => {
          const o = ramp(frame, l.at, l.at + 4);
          return (
            <div
              key={i}
              style={{
                opacity: o,
                color: l.color ?? C.ink,
                fontWeight: l.bold ? 700 : 400,
                background: l.bg,
                borderRadius: 6,
                padding: l.bg ? "2px 8px" : undefined,
                margin: l.bg ? "3px -8px" : undefined,
              }}
            >
              {l.text}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const DEFECT_ITEMS = [
  { x: 0.515, y: 0.088, label: "Headline says 12 points — data says 8.", color: C.red, at: 10 },
  { x: 0.105, y: 0.89, label: "Y-axis starts at 0.6: bars exaggerate differences.", color: C.red, at: 26 },
  { x: 0.76, y: 0.925, label: "8.1 px text when viewed in a 700 px chat.", color: C.amber, at: 42 },
];

const CheckSceneBefore: React.FC<{ frame: number }> = ({ frame }) => {
  const out = 1 - ramp(frame, CS.before[1] - 5, CS.before[1]);
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        gap: 28,
        padding: "28px 44px",
        opacity: out,
        fontFamily: SANS,
      }}
    >
      <BadgePill color={C.amber}>Plain Matplotlib · What agents ship today</BadgePill>
      <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
        <FlatCard style={{ width: 690 }}>
          <div style={{ position: "relative" }}>
            <Img src={staticFile("before.png")} style={{ width: "100%", display: "block", borderRadius: 6 }} />
            {DEFECT_ITEMS.map((d, i) => {
              const p = ramp(frame, d.at, d.at + 6);
              return (
                <div
                  key={d.label}
                  style={{
                    position: "absolute",
                    left: `${d.x * 100}%`,
                    top: `${d.y * 100}%`,
                    width: 48,
                    height: 48,
                    marginLeft: -24,
                    marginTop: -24,
                    borderRadius: 24,
                    border: `4px solid ${d.color}`,
                    opacity: p,
                    transform: `scale(${0.65 + 0.35 * p})`,
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      top: -12,
                      right: -12,
                      width: 22,
                      height: 22,
                      borderRadius: 11,
                      background: d.color,
                      color: C.bg,
                      fontSize: 13,
                      fontWeight: 800,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {i + 1}
                  </span>
                </div>
              );
            })}
          </div>
        </FlatCard>

        <div style={{ display: "flex", flexDirection: "column", gap: 18, width: 470 }}>
          {DEFECT_ITEMS.map((d, i) => {
            const p = ramp(frame, d.at + 2, d.at + 9);
            return (
              <div
                key={d.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "14px 16px",
                  borderRadius: 12,
                  background: C.panel,
                  border: `1.5px solid ${C.line}`,
                  opacity: p,
                  transform: `translateY(${(1 - p) * 12}px)`,
                }}
              >
                <span
                  style={{
                    flex: "0 0 auto",
                    width: 32,
                    height: 32,
                    borderRadius: 16,
                    background: d.color,
                    color: C.bg,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 800,
                    fontSize: 18,
                  }}
                >
                  {i + 1}
                </span>
                <span style={{ color: C.ink, fontSize: 21, fontWeight: 650, lineHeight: 1.25 }}>
                  {d.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const CheckSceneAudit: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - CS.check[0];
  const dur = CS.check[1] - CS.check[0];
  const fadeIn = ramp(f, 0, 6);
  const fadeOut = 1 - ramp(f, dur - 6, dur);
  const pillIn = ramp(f, 58, 66);

  const lines: CheckTermLine[] = [
    { text: "figure.png: FIX FIRST", color: C.red, bold: true, at: 20 },
    { text: "  read at 700 px wide; PNG 1800×750 px; smallest text 8.1 px", color: C.muted, at: 24 },
    { text: "  claim: 'Removing retrieval costs 12 points of accuracy'", at: 28 },
    { text: "    12 points: NOT FOUND", color: C.red, bold: true, bg: "#2B1524", at: 32 },
    { text: "      closest: full model vs no retrieval: 0.82 − 0.74 = 8 points", color: C.mint, bold: true, at: 36 },
    { text: "  error bar_baseline_nonzero: value axis runs 0.6–0.85", color: C.red, at: 41 },
    { text: "  warning text_too_small: 11 texts under 11 px as read", color: C.amber, at: 45 },
    { text: "    fix: figsize width ≈ 4.7 in at dpi=150, or text ≥ 14 pt", color: C.mint, at: 49 },
    { text: "  warning interval_unlabelled: error bars never say what they are", color: C.amber, at: 53 },
  ];

  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        gap: 24,
        padding: "24px 36px",
        opacity: fadeIn * fadeOut,
        fontFamily: SANS,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, width: 396 }}>
          <FlatCard style={{ width: 396, padding: 8 }}>
            <Img src={staticFile("before.png")} style={{ width: "100%", display: "block", borderRadius: 6 }} />
          </FlatCard>
          <div
            style={{
              background: C.panel,
              border: `1.5px solid ${C.line}`,
              borderRadius: 10,
              padding: "12px 16px",
              fontFamily: MONO,
              fontSize: 15.5,
              lineHeight: 1.55,
              color: C.muted,
            }}
          >
            <div># in Python or PostToolUse hook</div>
            <div style={{ color: C.ink }}>
              <span style={{ color: C.blue }}>&gt;&gt;&gt;</span> report ={" "}
              <span style={{ color: C.mint }}>mint.check</span>(fig)
            </div>
          </div>
        </div>

        <FlatTerminal
          command="mintfig check plot.py"
          typeFrom={CS.check[0] + 4}
          typeFrames={14}
          lines={lines.map((l) => ({ ...l, at: CS.check[0] + l.at }))}
          fontSize={15.5}
          width={776}
        />
      </div>

      <div
        style={{
          opacity: pillIn,
          transform: `translateY(${(1 - pillIn) * 10}px)`,
          padding: "10px 26px",
          borderRadius: 999,
          background: C.panel,
          border: `1.5px solid ${C.mint}`,
          color: C.ink,
          fontSize: 21,
          fontWeight: 700,
        }}
      >
        Reads the numbers back out of the plot and checks the headline against them.
      </div>
    </AbsoluteFill>
  );
};

const CheckSceneAfter: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - CS.after[0];
  const dur = CS.after[1] - CS.after[0];
  const fadeIn = ramp(f, 0, 6);
  const fadeOut = 1 - ramp(f, dur - 6, dur);
  const shipP = ramp(f, 22, 30);

  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        gap: 26,
        padding: "24px 40px",
        opacity: fadeIn * fadeOut,
        fontFamily: SANS,
      }}
    >
      <BadgePill color={C.mint}>After the fix hints · Still plain Matplotlib</BadgePill>
      <div style={{ display: "flex", alignItems: "center", gap: 30 }}>
        <FlatCard style={{ width: 600, padding: 12 }}>
          <Img src={staticFile("after.png")} style={{ width: "100%", display: "block", borderRadius: 6 }} />
          <div
            style={{
              position: "absolute",
              bottom: -18,
              right: 16,
              background: C.mint,
              color: C.bg,
              fontWeight: 800,
              fontSize: 22,
              padding: "6px 18px",
              borderRadius: 999,
              opacity: shipP,
              transform: `scale(${0.8 + 0.2 * shipP})`,
            }}
          >
            ✓ ship: true
          </div>
        </FlatCard>

        <FlatTerminal
          command="mintfig check plot.py"
          typeFrom={CS.after[0] + 3}
          typeFrames={10}
          fontSize={16}
          width={560}
          lines={[
            { text: "figure.png: SHIP", color: C.mint, bold: true, at: CS.after[0] + 15 },
            { text: "  smallest text 15.3 px at 700 px", color: C.muted, at: CS.after[0] + 18 },
            { text: "  claim: 'Removing retrieval costs", at: CS.after[0] + 21 },
            { text: "          8 points of accuracy'", at: CS.after[0] + 21 },
            { text: "    8 points: found", color: C.mint, bold: true, bg: "#112D29", at: CS.after[0] + 24 },
            { text: "    0.82 − 0.74 = 8 points", color: C.mint, at: CS.after[0] + 27 },
          ]}
        />
      </div>
      <div style={{ color: C.muted, fontSize: 20, fontWeight: 500, marginTop: 8 }}>
        Your plot, your style — legends, colours, and fonts stay yours.
      </div>
    </AbsoluteFill>
  );
};

const CheckSceneExplain: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - CS.explain[0];
  const dur = CS.explain[1] - CS.explain[0];
  const fadeIn = ramp(f, 0, 6);
  const fadeOut = 1 - ramp(f, dur - 6, dur);

  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        gap: 24,
        padding: "24px 44px",
        opacity: fadeIn * fadeOut,
        fontFamily: SANS,
      }}
    >
      <BadgePill color={C.blue}>Or let mintfig draw it · Message-first by default</BadgePill>
      <FlatCard style={{ width: 780, padding: 12 }}>
        <Img src={staticFile("mintfig.png")} style={{ width: "100%", display: "block", borderRadius: 6 }} />
      </FlatCard>
      <div
        style={{
          background: C.term,
          border: `1.5px solid ${C.line}`,
          borderRadius: 10,
          padding: "12px 22px",
          fontFamily: MONO,
          fontSize: 18,
          color: C.ink,
          lineHeight: 1.5,
          whiteSpace: "pre",
        }}
      >
        <span style={{ color: C.blue }}>mint.explain</span>(
        <span style={{ color: C.mint }}>"Removing retrieval costs 8 points of accuracy"</span>,
        {"\n    "}
        <span style={{ color: C.blue }}>mint.compare</span>(acc, error=ci, error_label=
        <span style={{ color: C.mint }}>"95% CI, 5 seeds"</span>))
      </div>
    </AbsoluteFill>
  );
};

const StatBlock: React.FC<{
  label: string;
  rows: { name: string; n: number; denom: number; color: string }[];
  startFrame: number;
}> = ({ label, rows, startFrame }) => {
  const frame = useCurrentFrame();

  return (
    <div style={{ width: 1020, fontFamily: SANS }}>
      <div style={{ color: C.ink, fontSize: 25, fontWeight: 750, marginBottom: 12 }}>{label}</div>
      {rows.map((r, i) => {
        const p = ramp(frame, startFrame + i * 3, startFrame + i * 3 + 14);
        const shown = Math.round(r.n * p);
        return (
          <div
            key={r.name}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              marginBottom: 9,
            }}
          >
            <div
              style={{
                width: 245,
                color: C.muted,
                fontSize: 19,
                fontWeight: 600,
                textAlign: "right",
              }}
            >
              {r.name}
            </div>
            <div
              style={{
                flex: 1,
                height: 30,
                background: "#16213B",
                borderRadius: 7,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.max(r.n === 0 ? 0 : 2, (r.n / r.denom) * 100 * p)}%`,
                  height: "100%",
                  background: r.color,
                  borderRadius: 7,
                }}
              />
            </div>
            <div
              style={{
                width: 106,
                color: r.color,
                fontSize: 26,
                fontWeight: 800,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {shown}/{r.denom}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const CheckSceneStats: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - CS.stats[0];
  const fadeIn = ramp(f, 0, 7);

  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        gap: 24,
        padding: "24px 44px",
        opacity: fadeIn,
        fontFamily: SANS,
      }}
    >
      <BadgePill color={C.mint}>figure-bench v0.1 · 60 tasks · fresh Sonnet 5.5 per task</BadgePill>
      <StatBlock
        label="Zero-defect figures at reading width (all 5 layout & text checks)"
        startFrame={CS.stats[0] + 4}
        rows={[
          { name: "plain Matplotlib", n: 21, denom: 60, color: C.red },
          { name: "+ mint.check hook", n: 48, denom: 60, color: C.blue },
          { name: "mintfig", n: 57, denom: 60, color: C.mint },
        ]}
      />
      <StatBlock
        label="Headline states the verified quantitative answer"
        startFrame={CS.stats[0] + 13}
        rows={[
          { name: "plain Matplotlib", n: 36, denom: 60, color: C.red },
          { name: "+ mint.check hook", n: 39, denom: 60, color: C.blue },
          { name: "mintfig", n: 53, denom: 60, color: C.mint },
        ]}
      />
      <div style={{ fontFamily: MONO, fontSize: 16, color: C.muted, marginTop: 2 }}>
        composite: 93.5 mintfig · 89.2 + hook · 81.6 plain Matplotlib · pip install mintfig
      </div>
    </AbsoluteFill>
  );
};

export const ReadmeCheck: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {within(frame, CS.before) && <CheckSceneBefore frame={frame} />}
      {within(frame, CS.check) && <CheckSceneAudit frame={frame} />}
      {within(frame, CS.after) && <CheckSceneAfter frame={frame} />}
      {within(frame, CS.explain) && <CheckSceneExplain frame={frame} />}
      {frame >= CS.stats[0] && <CheckSceneStats frame={frame} />}
    </AbsoluteFill>
  );
};

export const ReadmeGifsRoot: React.FC = () => (
  <>
    <Composition
      id="ReadmeOpener"
      component={ReadmeOpener}
      width={README_W}
      height={README_H}
      fps={README_FPS}
      durationInFrames={OPENER_DURATION}
    />
    <Composition
      id="ReadmeCheck"
      component={ReadmeCheck}
      width={README_W}
      height={README_H}
      fps={README_FPS}
      durationInFrames={CHECK_DURATION}
    />
  </>
);
