import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const FPS = 30;

// Scene boundaries in frames (30 fps, 40 s total).
const SCENES = {
  hook: [0, 120],
  before: [120, 330],
  check: [330, 640],
  after: [640, 850],
  explain: [850, 970],
  stats: [970, 1110],
  cta: [1110, 1200],
} as const;
export const DURATION = SCENES.cta[1];

const C = {
  bg: "#0B1020",
  panel: "#121A2E",
  line: "#22304F",
  ink: "#EEF2FA",
  muted: "#93A0BC",
  mint: "#34D8A0",
  red: "#FF5D6C",
  amber: "#F6B941",
  blue: "#7FB2FF",
};
const SANS = '-apple-system, "SF Pro Display", "Helvetica Neue", Helvetica, Arial, sans-serif';
const MONO = '"SF Mono", Menlo, "JetBrains Mono", Consolas, monospace';

// ------------------------------------------------------------------ helpers

const useLayout = () => {
  const { width, height } = useVideoConfig();
  const square = width / height < 1.3;
  return { width, height, square };
};

const fade = (frame: number, dur: number, inF = 10, outF = 10) =>
  interpolate(frame, [0, inF, dur - outF, dur], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const useRise = (delay: number, damping = 18) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping, mass: 0.6 } });
};

const Rise: React.FC<{ delay: number; children: React.ReactNode; style?: React.CSSProperties; dy?: number }> = ({
  delay,
  children,
  style,
  dy = 30,
}) => {
  const p = useRise(delay);
  return (
    <div style={{ opacity: p, transform: `translateY(${(1 - p) * dy}px)`, ...style }}>{children}</div>
  );
};

const Scene: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ opacity: fade(frame, dur) }}>{children}</AbsoluteFill>;
};

const Chip: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = C.muted }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 12,
      padding: "10px 22px",
      borderRadius: 999,
      border: `2px solid ${C.line}`,
      background: "rgba(18,26,46,0.85)",
      color,
      fontFamily: SANS,
      fontSize: 28,
      fontWeight: 600,
      letterSpacing: 0.2,
    }}
  >
    {children}
  </div>
);

const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div
    style={{
      background: "#FFFFFF",
      borderRadius: 18,
      padding: 18,
      boxShadow: "0 30px 80px rgba(0,0,0,0.45)",
      position: "relative",
      ...style,
    }}
  >
    {children}
  </div>
);

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, DURATION], [0, 60]);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(1200px 800px at 15% ${10 + drift / 6}%, rgba(52,216,160,0.10), transparent 60%),
                     radial-gradient(1000px 700px at 90% 100%, rgba(127,178,255,0.10), transparent 60%), ${C.bg}`,
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${C.line}33 1px, transparent 1px), linear-gradient(90deg, ${C.line}33 1px, transparent 1px)`,
          backgroundSize: "60px 60px",
          backgroundPosition: `${drift}px ${drift}px`,
          maskImage: "radial-gradient(ellipse at center, black 30%, transparent 80%)",
        }}
      />
    </AbsoluteFill>
  );
};

const Wordmark: React.FC<{ size: number }> = ({ size }) => (
  <div style={{ display: "flex", alignItems: "center", gap: size * 0.25, fontFamily: SANS }}>
    <div
      style={{
        width: size * 0.8,
        height: size * 0.8,
        borderRadius: size * 0.22,
        background: `linear-gradient(135deg, ${C.mint}, #1FA97C)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: `0 0 ${size * 0.6}px rgba(52,216,160,0.35)`,
      }}
    >
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24">
        <path d="M4 20V11M10 20V6M16 20v-6" stroke={C.bg} strokeWidth={3.2} strokeLinecap="round" />
        <path d="M14.5 6.5l2.2 2.2L21 4.4" stroke={C.bg} strokeWidth={2.6} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
    <span style={{ color: C.ink, fontSize: size, fontWeight: 800, letterSpacing: -size * 0.03 }}>mintfig</span>
  </div>
);

// ------------------------------------------------------------------ terminal

type TermLine = { text: string; color?: string; at: number; bold?: boolean; bg?: string };

const Terminal: React.FC<{
  command: string;
  typeFrom: number;
  typeFrames: number;
  lines: TermLine[];
  fontSize: number;
  width: number | string;
  title?: string;
}> = ({ command, typeFrom, typeFrames, lines, fontSize, width, title = "zsh — plot.py" }) => {
  const frame = useCurrentFrame();
  const typed = Math.round(
    interpolate(frame, [typeFrom, typeFrom + typeFrames], [0, command.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );
  const cursorOn = Math.floor(frame / 15) % 2 === 0;
  const doneTyping = typed >= command.length;
  return (
    <div
      style={{
        width,
        background: "#0A0F1C",
        border: `2px solid ${C.line}`,
        borderRadius: 18,
        boxShadow: "0 30px 80px rgba(0,0,0,0.5)",
        overflow: "hidden",
        fontFamily: MONO,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "14px 18px",
          borderBottom: `2px solid ${C.line}`,
          background: "#0E1527",
        }}
      >
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <div key={c} style={{ width: 14, height: 14, borderRadius: 7, background: c }} />
        ))}
        <span style={{ color: C.muted, fontSize: 20, marginLeft: 14, fontFamily: SANS }}>{title}</span>
      </div>
      <div style={{ padding: "22px 26px 26px", fontSize, lineHeight: 1.5, color: C.ink, whiteSpace: "pre-wrap" }}>
        <div>
          <span style={{ color: C.mint }}>$ </span>
          {command.slice(0, typed)}
          {!doneTyping || (cursorOn && lines.every((l) => frame < l.at)) ? (
            <span style={{ background: C.ink, color: C.ink, opacity: cursorOn ? 1 : 0 }}>▌</span>
          ) : null}
        </div>
        {lines.map((l, i) => {
          const o = interpolate(frame, [l.at, l.at + 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const x = interpolate(frame, [l.at, l.at + 8], [-12, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div
              key={i}
              style={{
                opacity: o,
                transform: `translateX(${x}px)`,
                color: l.color ?? C.ink,
                fontWeight: l.bold ? 700 : 400,
                background: l.bg,
                borderRadius: 8,
                padding: l.bg ? "2px 10px" : undefined,
                margin: l.bg ? "4px -10px" : undefined,
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

// ------------------------------------------------------------------ scenes

const Hook: React.FC = () => {
  const { square } = useLayout();
  const big = square ? 84 : 104;
  return (
    <Scene dur={SCENES.hook[1] - SCENES.hook[0]}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
        <div style={{ fontFamily: SANS, textAlign: "center" }}>
          <Rise delay={4}>
            <div style={{ color: C.ink, fontSize: big, fontWeight: 800, letterSpacing: -2, lineHeight: 1.08 }}>
              Your agent just made a chart.
            </div>
          </Rise>
          <Rise delay={38} style={{ marginTop: 44 }}>
            <div style={{ color: C.mint, fontSize: big * 0.62, fontWeight: 700 }}>Is the number in the title true?</div>
          </Rise>
          <Rise delay={64} style={{ marginTop: 14 }}>
            <div style={{ color: C.blue, fontSize: big * 0.62, fontWeight: 700 }}>Can anyone read it in a chat?</div>
          </Rise>
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

// Positions on before.png (fractions of the image) for the three defects.
const DEFECTS = [
  { x: 0.51, y: 0.093, label: "Says 12 points. The data says 8.", color: C.red, at: 36 },
  { x: 0.105, y: 0.89, label: "Axis starts at 0.6: bars exaggerate", color: C.red, at: 74 },
  { x: 0.76, y: 0.925, label: "8 px text in a 700 px chat column", color: C.amber, at: 112 },
];

const Ring: React.FC<{ x: number; y: number; color: string; at: number; r: number }> = ({ x, y, color, at, r }) => {
  const p = useRise(at, 12);
  const frame = useCurrentFrame();
  const pulse = 1 + 0.06 * Math.sin((frame - at) / 5);
  return (
    <div
      style={{
        position: "absolute",
        left: `${x * 100}%`,
        top: `${y * 100}%`,
        width: r * 2,
        height: r * 2,
        marginLeft: -r,
        marginTop: -r,
        borderRadius: r,
        border: `5px solid ${color}`,
        boxShadow: `0 0 24px ${color}88`,
        opacity: p,
        transform: `scale(${(0.4 + 0.6 * p) * pulse})`,
      }}
    />
  );
};

const BeforeFigure: React.FC<{ width: number; rings: boolean; ringR?: number }> = ({ width, rings, ringR = 46 }) => (
  <Card style={{ width, padding: 10 }}>
    <div style={{ position: "relative" }}>
      <Img src={staticFile("before.png")} style={{ width: "100%", display: "block", borderRadius: 8 }} />
      {rings && DEFECTS.map((d) => <Ring key={d.label} {...d} r={ringR} />)}
    </div>
  </Card>
);

const Before: React.FC = () => {
  const { square } = useLayout();
  const figW = square ? 980 : 1080;
  return (
    <Scene dur={SCENES.before[1] - SCENES.before[0]}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 36, fontFamily: SANS }}>
        <Rise delay={0}>
          <Chip>What an agent ships today · plain Matplotlib</Chip>
        </Rise>
        <div style={{ display: "flex", flexDirection: square ? "column" : "row", alignItems: "center", gap: 40 }}>
          <Rise delay={6}>
            <BeforeFigure width={figW} rings />
          </Rise>
          <div style={{ display: "flex", flexDirection: "column", gap: 24, width: square ? figW : 640 }}>
            {DEFECTS.map((d, i) => (
              <Rise key={d.label} delay={d.at + 4} dy={20}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                    color: C.ink,
                    fontSize: square ? 32 : 36,
                    fontWeight: 650,
                    lineHeight: 1.2,
                  }}
                >
                  <span
                    style={{
                      flex: "0 0 auto",
                      width: 48,
                      height: 48,
                      borderRadius: 24,
                      background: d.color,
                      color: C.bg,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 800,
                      fontSize: 28,
                    }}
                  >
                    {i + 1}
                  </span>
                  {d.label}
                </div>
              </Rise>
            ))}
          </div>
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

const CHECK_LINES = (start: number, step: number): TermLine[] => {
  const rows: Omit<TermLine, "at">[] = [
    { text: "figure.png: FIX FIRST", color: C.red, bold: true },
    { text: "  read at 700 px wide; PNG 1800×750 px; smallest text 8.1 px", color: C.muted },
    { text: "  claim: 'Removing retrieval costs 12 points of accuracy'" },
    { text: "    12 points: NOT FOUND", color: C.red, bold: true, bg: "rgba(255,93,108,0.12)" },
    { text: "      closest: full model vs no retrieval: 0.82 − 0.74 = 8 points", color: C.mint, bold: true },
    { text: "  error bar_baseline_nonzero: the value axis runs 0.6–0.85", color: C.red },
    { text: "  warning text_too_small: 11 texts under 11 px as read", color: C.amber },
    { text: "    fix: figsize width ≈ 4.7 in at dpi=150, or text ≥ 14 pt", color: C.mint },
    { text: "  warning interval_unlabelled: the error bars never say what they are", color: C.amber },
    { text: "  facts read from the plotted data:", color: C.muted },
    { text: "    - intervals of full model and no retrieval do not overlap", color: C.blue },
  ];
  return rows.map((r, i) => ({ ...r, at: start + i * step }));
};

const Check: React.FC = () => {
  const { square } = useLayout();
  const frame = useCurrentFrame();
  const dur = SCENES.check[1] - SCENES.check[0];
  const tagline = useRise(232);
  return (
    <Scene dur={dur}>
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          flexDirection: square ? "column" : "row",
          gap: square ? 30 : 40,
          padding: square ? 40 : 60,
        }}
      >
        <Rise delay={0} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 22 }}>
          <BeforeFigure width={square ? 520 : 560} rings={false} />
          {!square && (
            <div style={{ fontFamily: MONO, color: C.muted, fontSize: 24, width: 560 }}>
              <span style={{ color: C.muted }}># in Python</span>
              <br />
              <span style={{ color: C.blue }}>&gt;&gt;&gt;</span> report = mint.check(fig)
              <br />
              <span style={{ color: C.muted }}># or from a shell or agent loop →</span>
            </div>
          )}
        </Rise>
        <Rise delay={6}>
          <Terminal
            command="mintfig check plot.py"
            typeFrom={14}
            typeFrames={30}
            lines={CHECK_LINES(56, 16)}
            fontSize={square ? 19 : 23}
            width={square ? 1000 : 1180}
          />
        </Rise>
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end", paddingBottom: square ? 36 : 54 }}>
        <div
          style={{
            opacity: tagline * interpolate(frame, [dur - 14, dur], [1, 0], { extrapolateLeft: "clamp" }),
            transform: `translateY(${(1 - tagline) * 20}px)`,
            fontFamily: SANS,
            fontSize: square ? 34 : 40,
            fontWeight: 700,
            color: C.ink,
            background: "rgba(11,16,32,0.92)",
            border: `2px solid ${C.mint}`,
            borderRadius: 999,
            padding: "14px 34px",
          }}
        >
          It reads the numbers back out of the plot and checks the title against them.
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

const ShipBadge: React.FC<{ at: number; size?: number }> = ({ at, size = 40 }) => {
  const p = useRise(at, 10);
  const { square } = useLayout();
  const place: React.CSSProperties = square
    ? { top: -size * 1.05, right: -size * 1.1 }
    : { bottom: -size * 1.35, right: 0 };
  return (
    <div
      style={{
        position: "absolute",
        ...place,
        transform: `scale(${p}) rotate(${(1 - p) * -20}deg)`,
        background: C.mint,
        color: C.bg,
        fontFamily: SANS,
        fontWeight: 800,
        fontSize: size,
        padding: `${size * 0.3}px ${size * 0.6}px`,
        borderRadius: 999,
        boxShadow: `0 10px 40px rgba(52,216,160,0.5)`,
      }}
    >
      ✓ ship: true
    </div>
  );
};

const After: React.FC = () => {
  const { square } = useLayout();
  return (
    <Scene dur={SCENES.after[1] - SCENES.after[0]}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 34, fontFamily: SANS }}>
        <Rise delay={0}>
          <Chip color={C.mint}>After the fix hints · still plain Matplotlib</Chip>
        </Rise>
        <div style={{ display: "flex", flexDirection: square ? "column" : "row", alignItems: "center", gap: square ? 30 : 50 }}>
          <Rise delay={6}>
            <Card style={{ width: square ? 760 : 900, padding: 14 }}>
              <Img src={staticFile("after.png")} style={{ width: "100%", display: "block" }} />
              <ShipBadge at={70} size={square ? 32 : 38} />
            </Card>
          </Rise>
          <Rise delay={20}>
            <Terminal
              command="mintfig check plot.py"
              typeFrom={22}
              typeFrames={20}
              fontSize={square ? 19 : 22}
              width={square ? 980 : 760}
              lines={[
                { text: "figure.png: SHIP", color: C.mint, bold: true, at: 52 },
                { text: "  smallest text 15.3 px at 700 px", color: C.muted, at: 62 },
                { text: "  claim: 'Removing retrieval costs", at: 72 },
                { text: "          8 points of accuracy'", at: 72 },
                { text: "    8 points: found", color: C.mint, bold: true, at: 86, bg: "rgba(52,216,160,0.12)" },
                { text: "    full model vs no retrieval:", color: C.mint, at: 92 },
                { text: "    0.82 − 0.74 = 8 points", color: C.mint, at: 92 },
              ]}
            />
          </Rise>
        </div>
        <Rise delay={120} style={{ marginTop: 44 }}>
          <div style={{ color: C.muted, fontSize: square ? 30 : 34, fontWeight: 600 }}>
            Your plot, your style. Legends, colours and fonts stay yours.
          </div>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};

const Explain: React.FC = () => {
  const { square } = useLayout();
  return (
    <Scene dur={SCENES.explain[1] - SCENES.explain[0]}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 34, fontFamily: SANS }}>
        <Rise delay={0}>
          <Chip color={C.blue}>Or let mintfig draw it: the takeaway is the title</Chip>
        </Rise>
        <Rise delay={8}>
          <Card style={{ width: square ? 940 : 1120, padding: 14 }}>
            <Img src={staticFile("mintfig.png")} style={{ width: "100%", display: "block" }} />
          </Card>
        </Rise>
        <Rise delay={22}>
          <div style={{ fontFamily: MONO, fontSize: square ? 22 : 27, color: C.ink, textAlign: "left", lineHeight: 1.5, whiteSpace: "pre" }}>
            <span style={{ color: C.blue }}>mint.explain</span>(<span style={{ color: C.mint }}>"Removing retrieval costs 8 points…"</span>,
            <br />
            {"    "}
            <span style={{ color: C.blue }}>mint.compare</span>(acc, error=ci, error_label=
            <span style={{ color: C.mint }}>"95% CI, 5 seeds"</span>))
          </div>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};

const StatRow: React.FC<{
  label: string;
  rows: { name: string; n: number; color: string }[];
  at: number;
  width: number;
  square: boolean;
}> = ({ label, rows, at, width, square }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ width, fontFamily: SANS }}>
      <Rise delay={at}>
        <div style={{ color: C.ink, fontSize: square ? 36 : 42, fontWeight: 750, marginBottom: 18 }}>{label}</div>
      </Rise>
      {rows.map((r, i) => {
        const p = spring({ frame: frame - at - 10 - i * 8, fps, config: { damping: 22, mass: 0.8 } });
        const shown = Math.round(r.n * p);
        return (
          <div key={r.name} style={{ display: "flex", alignItems: "center", gap: 22, marginBottom: 14, opacity: Math.min(1, p * 2) }}>
            <div style={{ width: square ? 250 : 300, color: C.muted, fontSize: square ? 28 : 32, fontWeight: 600, textAlign: "right" }}>
              {r.name}
            </div>
            <div style={{ flex: 1, height: square ? 44 : 52, background: "#18223B", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ width: `${(r.n / 15) * 100 * p}%`, height: "100%", background: r.color, borderRadius: 10 }} />
            </div>
            <div style={{ width: square ? 130 : 150, color: r.color, fontSize: square ? 38 : 46, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
              {shown}/15
            </div>
          </div>
        );
      })}
    </div>
  );
};

const Stats: React.FC = () => {
  const { square, width } = useLayout();
  const w = square ? width - 120 : 1500;
  return (
    <Scene dur={SCENES.stats[1] - SCENES.stats[0]}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: square ? 40 : 50, fontFamily: SANS }}>
        <Rise delay={0}>
          <Chip>figure-bench · 15 analysis tasks · AI agents, same data</Chip>
        </Rise>
        <StatRow
          label="Figures shipped with a text or layout defect"
          at={8}
          width={w}
          square={square}
          rows={[
            { name: "plain Matplotlib", n: 13, color: C.red },
            { name: "mintfig", n: 0, color: C.mint },
          ]}
        />
        <StatRow
          label="Headline states the correct number"
          at={40}
          width={w}
          square={square}
          rows={[
            { name: "plain Matplotlib", n: 4, color: C.red },
            { name: "mintfig", n: 15, color: C.mint },
          ]}
        />
        <Rise delay={80}>
          <div style={{ color: C.muted, fontSize: square ? 20 : 22, textAlign: "center", maxWidth: w }}>
            Final submissions. Plain: agents told nothing about display width or checks. Method and data in evals/figure_bench.
          </div>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};

const Cta: React.FC = () => {
  const { square } = useLayout();
  const frame = useCurrentFrame();
  const dur = SCENES.cta[1] - SCENES.cta[0];
  const opacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const code = (t: string) => (
    <div
      style={{
        fontFamily: MONO,
        fontSize: square ? 34 : 40,
        color: C.ink,
        background: "#0A0F1C",
        border: `2px solid ${C.line}`,
        borderRadius: 14,
        padding: "16px 30px",
      }}
    >
      <span style={{ color: C.mint }}>{t.startsWith("pip") ? "$ " : ">>> "}</span>
      {t}
    </div>
  );
  return (
    <AbsoluteFill style={{ opacity, alignItems: "center", justifyContent: "center", gap: 40, fontFamily: SANS }}>
      <Rise delay={0}>
        <Wordmark size={square ? 120 : 140} />
      </Rise>
      <Rise delay={8}>
        <div style={{ color: C.ink, fontSize: square ? 40 : 48, fontWeight: 700, textAlign: "center" }}>
          Figures whose claims are checked against the data.
        </div>
      </Rise>
      <Rise delay={16} style={{ display: "flex", gap: 26, flexDirection: square ? "column" : "row", alignItems: "center" }}>
        {code("pip install mintfig")}
        {code("mint.check(fig)")}
      </Rise>
      <Rise delay={24}>
        <div style={{ color: C.muted, fontSize: square ? 30 : 34, fontWeight: 600 }}>
          github.com/blaiszik/mintfig · MIT
        </div>
      </Rise>
      <div style={{ position: "absolute", bottom: 0, left: 0, height: 8, width: `${(frame / dur) * 100}%`, background: C.mint }} />
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ composition

const at = (k: keyof typeof SCENES) => ({ from: SCENES[k][0], durationInFrames: SCENES[k][1] - SCENES[k][0] });

export const MintCheck: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg }}>
    <Background />
    <Sequence {...at("hook")}>
      <Hook />
    </Sequence>
    <Sequence {...at("before")}>
      <Before />
    </Sequence>
    <Sequence {...at("check")}>
      <Check />
    </Sequence>
    <Sequence {...at("after")}>
      <After />
    </Sequence>
    <Sequence {...at("explain")}>
      <Explain />
    </Sequence>
    <Sequence {...at("stats")}>
      <Stats />
    </Sequence>
    <Sequence {...at("cta")}>
      <Cta />
    </Sequence>
  </AbsoluteFill>
);
