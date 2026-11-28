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

export const BRAILLE_FPS = 30;
export const BRAILLE_SECONDS = 24.5;
export const BRAILLE_DURATION = Math.round(BRAILLE_SECONDS * BRAILLE_FPS); // 735 frames @ 30fps

// Colors harmonized with mintfig style="pine" + style="editorial"
const C = {
  bg: "#09110F",
  bgCard: "#101E1A",
  border: "#1F362F",
  ink: "#EEF5F2",
  muted: "#8FA9A0",
  mint: "#38DDA9",
  mintDeep: "#149E70",
  terracotta: "#D44D27",
  blue: "#69B4F8",
  white: "#FFFFFF",
};

const SANS = '-apple-system, "SF Pro Display", "Helvetica Neue", Helvetica, Arial, sans-serif';
const SERIF = 'Georgia, "Newsreader", "Source Serif 4", serif';
const MONO = '"SF Mono", Menlo, "JetBrains Mono", Consolas, monospace';

const CLAMP = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);

const useScale = () => {
  const { width, height } = useVideoConfig();
  const s = Math.min(width / 1920, height / 1080);
  const square = width / height < 1.3;
  return { width, height, s, square };
};

const sceneOpacity = (frame: number, durationInFrames: number, fps: number) => {
  const fIn = Math.max(1, Math.round(0.35 * fps));
  const fOut = Math.max(1, Math.round(0.35 * fps));
  return interpolate(
    frame,
    [0, fIn, Math.max(fIn + 1, durationInFrames - fOut), durationInFrames],
    [0, 1, 1, 0],
    CLAMP,
  );
};

const Backdrop: React.FC<{ flat?: boolean }> = ({ flat = false }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  if (flat) {
    return <AbsoluteFill style={{ backgroundColor: C.bg }} />;
  }
  const drift = interpolate(frame, [0, durationInFrames], [0, 48], CLAMP);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(1200px 760px at 14% ${12 + drift / 8}%, rgba(56,221,169,0.12), transparent 60%),
                     radial-gradient(960px 700px at 88% 92%, rgba(212,77,39,0.08), transparent 60%), ${C.bg}`,
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${C.border}55 1px, transparent 1px), linear-gradient(90deg, ${C.border}55 1px, transparent 1px)`,
          backgroundSize: "64px 64px",
          backgroundPosition: `${drift}px ${drift}px`,
          maskImage: "radial-gradient(ellipse at center, black 28%, transparent 82%)",
        }}
      />
    </AbsoluteFill>
  );
};

const Wordmark: React.FC<{ size: number }> = ({ size }) => (
  <div style={{ display: "inline-flex", alignItems: "center", gap: size * 0.24, fontFamily: SANS }}>
    <div
      style={{
        width: size * 0.86,
        height: size * 0.86,
        borderRadius: size * 0.22,
        background: `linear-gradient(135deg, ${C.mint}, ${C.mintDeep})`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <svg width={size * 0.52} height={size * 0.52} viewBox="0 0 24 24">
        <path d="M4 20V11M10 20V6M16 20v-6" stroke={C.bg} strokeWidth={3.2} strokeLinecap="round" />
        <path
          d="M14.5 6.5l2.2 2.2L21 4.4"
          stroke={C.bg}
          strokeWidth={2.6}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
    <span style={{ color: C.ink, fontSize: size, fontWeight: 800, letterSpacing: -size * 0.03 }}>
      mintfig
    </span>
  </div>
);

const Pill: React.FC<{
  children: React.ReactNode;
  accent?: string;
  bg?: string;
  s: number;
}> = ({ children, accent = C.mint, bg = C.bgCard, s }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10 * s,
      padding: `${9 * s}px ${22 * s}px`,
      borderRadius: 999,
      border: `${Math.max(1, 2 * s)}px solid ${accent}66`,
      background: bg,
      color: accent,
      fontFamily: MONO,
      fontSize: 22 * s,
      fontWeight: 700,
      letterSpacing: 0.6 * s,
    }}
  >
    {children}
  </div>
);

// ---------------------------------------------------------------------------
// Scene 1: Hook + live CLI typing
// ---------------------------------------------------------------------------

const SceneHook: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { s } = useScale();

  const op = sceneOpacity(frame, dur, fps);
  const riseTitle = spring({ frame: frame - Math.round(0.15 * fps), fps, config: { damping: 18, mass: 0.7 } });
  const riseCmd = spring({ frame: frame - Math.round(0.55 * fps), fps, config: { damping: 18, mass: 0.7 } });

  const cmd = "mintfig show checkout_canary.png --braille --width 116";
  const typedLen = Math.floor(
    interpolate(frame, [Math.round(0.75 * fps), Math.round(2.45 * fps)], [0, cmd.length], CLAMP),
  );
  const cursorOn = Math.floor(frame / Math.max(1, Math.round(0.35 * fps))) % 2 === 0;

  return (
    <AbsoluteFill
      style={{
        opacity: op,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: `${80 * s}px ${110 * s}px`,
        gap: 34 * s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 22 * s }}>
        <Wordmark size={54 * s} />
        <Pill s={s}>2×4 UNICODE BRAILLE · 24-BIT ANSI</Pill>
      </div>

      <div
        style={{
          opacity: riseTitle,
          transform: `translateY(${(1 - riseTitle) * 32 * s}px)`,
          textAlign: "center",
          maxWidth: 1460 * s,
        }}
      >
        <div
          style={{
            fontFamily: SERIF,
            fontSize: 82 * s,
            fontWeight: 700,
            lineHeight: 1.08,
            color: C.ink,
            letterSpacing: -1.5 * s,
          }}
        >
          Publication charts —
          <br />
          <span style={{ color: C.mint }}>right inside your terminal.</span>
        </div>
        <div
          style={{
            marginTop: 24 * s,
            fontFamily: SANS,
            fontSize: 32 * s,
            color: C.muted,
            fontWeight: 500,
          }}
        >
          Zero image viewer. Zero extra deps. Built for SSH, tmux, and coding agents.
        </div>
      </div>

      <div
        style={{
          opacity: riseCmd,
          transform: `translateY(${(1 - riseCmd) * 24 * s}px)`,
          marginTop: 12 * s,
          padding: `${24 * s}px ${38 * s}px`,
          borderRadius: 18 * s,
          background: "#0E1916",
          border: `${Math.max(1, 2 * s)}px solid ${C.mint}55`,
          fontFamily: MONO,
          fontSize: 32 * s,
          color: C.ink,
          display: "flex",
          alignItems: "center",
          gap: 16 * s,
          minWidth: 1180 * s,
        }}
      >
        <span style={{ color: C.mint, fontWeight: 700 }}>$</span>
        <span>
          {cmd.slice(0, typedLen)}
          <span
            style={{
              display: "inline-block",
              width: 15 * s,
              height: 34 * s,
              background: C.mint,
              marginLeft: 4 * s,
              verticalAlign: "middle",
              opacity: cursorOn ? 1 : 0,
            }}
          />
        </span>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene 2: One Call, Two Surfaces (Editorial Print <-> 2x4 Braille)
// ---------------------------------------------------------------------------

const SceneDualSurface: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { s, square } = useScale();

  const op = sceneOpacity(frame, dur, fps);
  const leftP = spring({ frame: frame - Math.round(0.2 * fps), fps, config: { damping: 18, mass: 0.7 } });
  const arrowP = spring({ frame: frame - Math.round(1.1 * fps), fps, config: { damping: 16, mass: 0.6 } });
  const rightP = spring({ frame: frame - Math.round(1.4 * fps), fps, config: { damping: 18, mass: 0.7 } });

  return (
    <AbsoluteFill
      style={{
        opacity: op,
        padding: `${52 * s}px ${72 * s}px`,
        display: "flex",
        flexDirection: "column",
        gap: 28 * s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div
            style={{
              fontFamily: MONO,
              fontSize: 21 * s,
              color: C.mint,
              fontWeight: 700,
              letterSpacing: 1.4 * s,
              textTransform: "uppercase",
            }}
          >
            ONE CALL · TWO SURFACES
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 48 * s,
              fontWeight: 800,
              color: C.ink,
              marginTop: 6 * s,
              letterSpacing: -0.8 * s,
            }}
          >
            Same <span style={{ fontFamily: MONO, color: C.mint }}>mint.explain()</span> — Editorial print or Braille SSH
          </div>
        </div>
        <Wordmark size={34 * s} />
      </div>

      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: square ? "column" : "row",
          alignItems: "center",
          justifyContent: "center",
          gap: 28 * s,
        }}
      >
        {/* Left: Editorial figure */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 14 * s,
            opacity: leftP,
            transform: `translateX(${(1 - leftP) * -40 * s}px)`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 * s }}>
            <Pill s={s} accent={C.white} bg="#00A087">
              PNG / SVG / HTML
            </Pill>
            <span style={{ fontFamily: SANS, fontSize: 22 * s, color: C.muted }}>
              3-panel ECDF · beeswarm · booktabs scorecard
            </span>
          </div>
          <div
            style={{
              background: C.white,
              borderRadius: 16 * s,
              padding: 14 * s,
              border: `${Math.max(1, 2 * s)}px solid #DCE5E1`,
            }}
          >
            <Img
              src={staticFile("braille/repo_header_hero.png")}
              style={{ width: "100%", height: "auto", display: "block", borderRadius: 8 * s }}
            />
          </div>
        </div>

        {/* Center bridge */}
        <div
          style={{
            opacity: arrowP,
            transform: `scale(${0.7 + 0.3 * arrowP})`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8 * s,
            padding: `${12 * s}px ${16 * s}px`,
            borderRadius: 16 * s,
            background: C.bgCard,
            border: `${Math.max(1, 2 * s)}px solid ${C.mint}66`,
          }}
        >
          <span style={{ fontFamily: MONO, fontSize: 34 * s, color: C.mint, fontWeight: 800 }}>
            {square ? "↓" : "→"}
          </span>
          <span style={{ fontFamily: MONO, fontSize: 17 * s, color: C.muted, fontWeight: 700 }}>
            --braille
          </span>
        </div>

        {/* Right: Matching Ghostty 2x4 Braille terminal */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 14 * s,
            opacity: rightP,
            transform: `translateX(${(1 - rightP) * 40 * s}px)`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 * s }}>
            <Pill s={s} accent={C.mint} bg="#0F1715">
              --braille --width 116
            </Pill>
            <span style={{ fontFamily: SANS, fontSize: 22 * s, color: C.muted }}>
              Same 3 panels in 2×4 Braille &amp; box table
            </span>
          </div>
          <div style={{ borderRadius: 16 * s, overflow: "hidden" }}>
            <Img
              src={staticFile("braille/repo_header_braille.png")}
              style={{ width: "100%", height: "auto", display: "block" }}
            />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene 3: Every Chart Form in 2x4 Braille (4-item animated deck)
// ---------------------------------------------------------------------------

const FORM_SLIDES = [
  {
    num: "01",
    name: "Wide 2-Panel ECDF + Beeswarm",
    tag: "layout=[['a','b']] · width=116",
    desc: "Side-by-side 2-column composer with p50/p95/p99 markers and deterministic beeswarm dots.",
    img: "braille/02_wide_ecdf_and_swarm.png",
  },
  {
    num: "02",
    name: "Scatter + OLS Fit + Pareto Hull",
    tag: "mint.relate(fit=True, frontier=True)",
    desc: "Grouped Braille scatter with dashed least-squares fit and Pareto frontier envelope.",
    img: "braille/03_relate_pareto_fit.png",
  },
  {
    num: "03",
    name: "Paired Before / After Slopegraph",
    tag: "mintfig diff base.json head.json --braille",
    desc: "Sub-pixel Braille connectors with inline color-coded deltas across benchmarks.",
    img: "braille/04_change_slopegraph.png",
  },
  {
    num: "04",
    name: "A/B Rollout Forest Plot",
    tag: "mint.forest(..., pooled=...)",
    desc: "Null reference line, 95% CI whiskers, pooled summary diamond, and aligned tabular readout.",
    img: "braille/05_forest_ab_rollout.png",
  },
] as const;

const SceneBrailleForms: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { s } = useScale();

  const op = sceneOpacity(frame, dur, fps);
  const perSlide = dur / FORM_SLIDES.length;
  const activeIdx = Math.min(FORM_SLIDES.length - 1, Math.floor(frame / perSlide));
  const localFrame = frame - activeIdx * perSlide;
  const cardIn = interpolate(localFrame, [0, Math.max(1, Math.round(0.32 * fps))], [0, 1], {
    ...CLAMP,
    easing: EASE_OUT,
  });

  const active = FORM_SLIDES[activeIdx];

  return (
    <AbsoluteFill
      style={{
        opacity: op,
        padding: `${52 * s}px ${72 * s}px`,
        display: "flex",
        flexDirection: "column",
        gap: 28 * s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div
            style={{
              fontFamily: MONO,
              fontSize: 21 * s,
              color: C.mint,
              fontWeight: 700,
              letterSpacing: 1.4 * s,
            }}
          >
            EVERY FORM IN 2×4 BRAILLE
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 46 * s,
              fontWeight: 800,
              color: C.ink,
              marginTop: 6 * s,
            }}
          >
            Full chart grammar — zero compromises in text terminals
          </div>
        </div>
        <Wordmark size={34 * s} />
      </div>

      <div style={{ flex: 1, display: "flex", gap: 40 * s, alignItems: "center" }}>
        {/* Left sidebar checklist */}
        <div style={{ width: 520 * s, display: "flex", flexDirection: "column", gap: 16 * s }}>
          {FORM_SLIDES.map((item, idx) => {
            const isAct = idx === activeIdx;
            return (
              <div
                key={item.num}
                style={{
                  padding: `${20 * s}px ${24 * s}px`,
                  borderRadius: 16 * s,
                  background: isAct ? "#132620" : C.bgCard,
                  border: `${Math.max(1, 2 * s)}px solid ${isAct ? C.mint : C.border}`,
                  opacity: isAct ? 1 : 0.52,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 * s }}>
                  <span
                    style={{
                      fontFamily: MONO,
                      fontSize: 20 * s,
                      fontWeight: 800,
                      color: isAct ? C.mint : C.muted,
                    }}
                  >
                    {item.num}
                  </span>
                  <span
                    style={{
                      fontFamily: SANS,
                      fontSize: 26 * s,
                      fontWeight: 700,
                      color: C.ink,
                    }}
                  >
                    {item.name}
                  </span>
                </div>
                {isAct && (
                  <>
                    <div
                      style={{
                        marginTop: 10 * s,
                        fontFamily: MONO,
                        fontSize: 18 * s,
                        color: C.mint,
                      }}
                    >
                      {item.tag}
                    </div>
                    <div
                      style={{
                        marginTop: 8 * s,
                        fontFamily: SANS,
                        fontSize: 21 * s,
                        color: C.muted,
                        lineHeight: 1.35,
                      }}
                    >
                      {item.desc}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>

        {/* Right live terminal preview */}
        <div
          style={{
            flex: 1,
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: cardIn,
            transform: `translateY(${(1 - cardIn) * 20 * s}px)`,
          }}
        >
          <Img
            src={staticFile(active.img)}
            style={{
              maxWidth: "100%",
              maxHeight: 780 * s,
              width: "auto",
              height: "auto",
              objectFit: "contain",
              borderRadius: 14 * s,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene 4: 24-Bit True-Color Matrices, KPI Cards & mintchip Braille Tables
// ---------------------------------------------------------------------------

const SceneRichTerminal: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { s } = useScale();

  const op = sceneOpacity(frame, dur, fps);
  const p1 = spring({ frame: frame - Math.round(0.15 * fps), fps, config: { damping: 18, mass: 0.7 } });
  const p2 = spring({ frame: frame - Math.round(0.55 * fps), fps, config: { damping: 18, mass: 0.7 } });
  const p3 = spring({ frame: frame - Math.round(0.95 * fps), fps, config: { damping: 18, mass: 0.7 } });

  const cards = [
    {
      p: p1,
      badge: "24-bit ANSI Matrix",
      img: "braille/06_matrix_confusion_truecolor.png",
      caption: "Row-normalized confusion heatmap with solid true-color cell fills",
    },
    {
      p: p2,
      badge: "PR KPI Summary Card",
      img: "braille/07_kpi_summary_card.png",
      caption: "Rounded KPI tiles, inline sparklines & 72-col Braille companion panel",
    },
    {
      p: p3,
      badge: "mintchip --braille",
      img: "braille/08_mintchip_braille_table.png",
      caption: "Shared-scale terminal tables in pine/mint_dark with inline micro-chips",
    },
  ];

  return (
    <AbsoluteFill
      style={{
        opacity: op,
        padding: `${52 * s}px ${64 * s}px`,
        display: "flex",
        flexDirection: "column",
        gap: 26 * s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div
            style={{
              fontFamily: MONO,
              fontSize: 21 * s,
              color: C.mint,
              fontWeight: 700,
              letterSpacing: 1.4 * s,
            }}
          >
            TRUE-COLOR HEATMAPS · KPI CARDS · MINTCHIP TABLES
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 46 * s,
              fontWeight: 800,
              color: C.ink,
              marginTop: 6 * s,
            }}
          >
            Built for PR reviews, CI logs, and live terminal dashboards
          </div>
        </div>
        <Wordmark size={34 * s} />
      </div>

      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1.18fr 0.82fr",
          gap: 28 * s,
          alignItems: "stretch",
        }}
      >
        {/* Left column: wide Confusion Matrix + ultra-wide mintchip table stacked */}
        <div style={{ display: "flex", flexDirection: "column", gap: 22 * s, justifyContent: "space-between" }}>
          {[cards[0], cards[2]].map((c) => (
            <div
              key={c.badge}
              style={{
                opacity: c.p,
                transform: `translateY(${(1 - c.p) * 26 * s}px)`,
                display: "flex",
                flexDirection: "column",
                gap: 12 * s,
                background: C.bgCard,
                border: `${Math.max(1, 2 * s)}px solid ${C.border}`,
                borderRadius: 18 * s,
                padding: `${16 * s}px ${20 * s}px`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14 * s }}>
                <Pill s={s} accent={C.mint} bg="#0C1714">
                  {c.badge}
                </Pill>
                <span style={{ fontFamily: SANS, fontSize: 19 * s, color: C.muted }}>
                  {c.caption}
                </span>
              </div>
              <Img
                src={staticFile(c.img)}
                style={{
                  width: "100%",
                  maxHeight: c.badge.startsWith("24-bit") ? 360 * s : 240 * s,
                  height: "auto",
                  objectFit: "contain",
                  borderRadius: 10 * s,
                }}
              />
            </div>
          ))}
        </div>

        {/* Right column: full-height PR KPI Summary Card */}
        <div
          style={{
            opacity: cards[1].p,
            transform: `translateY(${(1 - cards[1].p) * 26 * s}px)`,
            display: "flex",
            flexDirection: "column",
            gap: 14 * s,
            background: C.bgCard,
            border: `${Math.max(1, 2 * s)}px solid ${C.border}`,
            borderRadius: 18 * s,
            padding: `${18 * s}px ${20 * s}px`,
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 * s }}>
            <Pill s={s} accent={C.mint} bg="#0C1714">
              {cards[1].badge}
            </Pill>
          </div>
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Img
              src={staticFile(cards[1].img)}
              style={{
                width: "100%",
                maxHeight: 670 * s,
                height: "auto",
                objectFit: "contain",
                borderRadius: 10 * s,
              }}
            />
          </div>
          <div style={{ fontFamily: SANS, fontSize: 20 * s, color: C.muted, lineHeight: 1.35 }}>
            {cards[1].caption}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene 5: Instant 15-second Demo CTA
// ---------------------------------------------------------------------------

const SceneCTA: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { s } = useScale();

  const fIn = Math.max(1, Math.round(0.35 * fps));
  const op = interpolate(frame, [0, fIn], [0, 1], CLAMP);
  const pop = spring({ frame: frame - Math.round(0.2 * fps), fps, config: { damping: 16, mass: 0.7 } });

  return (
    <AbsoluteFill
      style={{
        opacity: op,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 32 * s,
        padding: `${80 * s}px`,
      }}
    >
      <Wordmark size={78 * s} />

      <div
        style={{
          fontFamily: SERIF,
          fontSize: 54 * s,
          fontWeight: 700,
          color: C.ink,
          textAlign: "center",
          maxWidth: 1200 * s,
        }}
      >
        Editorial print. 2×4 Braille terminals. One API.
      </div>

      <div
        style={{
          transform: `scale(${0.92 + 0.08 * pop})`,
          padding: `${24 * s}px ${48 * s}px`,
          borderRadius: 20 * s,
          background: "#0E1D18",
          border: `${Math.max(1, 2.5 * s)}px solid ${C.mint}`,
          fontFamily: MONO,
          fontSize: 40 * s,
          fontWeight: 700,
          color: C.mint,
        }}
      >
        $ uvx mintfig demo
      </div>

      <div
        style={{
          display: "flex",
          gap: 24 * s,
          flexWrap: "wrap",
          justifyContent: "center",
          fontFamily: MONO,
          fontSize: 23 * s,
          color: C.muted,
        }}
      >
        <span>pip install &quot;mintfig[chip]&quot;</span>
        <span style={{ color: C.border }}>·</span>
        <span>mintfig watch train.csv --braille</span>
        <span style={{ color: C.border }}>·</span>
        <span>mintfig mcp --install</span>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Root composition (supports 30fps MP4 & 15fps zero-grain README GIF)
// ---------------------------------------------------------------------------

export const BrailleShowcase: React.FC<{ flatBg?: boolean }> = ({ flatBg = false }) => {
  const { fps } = useVideoConfig();
  const s1 = Math.round(3.5 * fps);
  const s2 = Math.round(5.5 * fps);
  const s3 = Math.round(7.5 * fps);
  const s4 = Math.round(5.0 * fps);
  const s5 = Math.round(3.0 * fps);

  return (
    <AbsoluteFill>
      <Backdrop flat={flatBg} />
      <Sequence from={0} durationInFrames={s1}>
        <SceneHook dur={s1} />
      </Sequence>
      <Sequence from={s1} durationInFrames={s2}>
        <SceneDualSurface dur={s2} />
      </Sequence>
      <Sequence from={s1 + s2} durationInFrames={s3}>
        <SceneBrailleForms dur={s3} />
      </Sequence>
      <Sequence from={s1 + s2 + s3} durationInFrames={s4}>
        <SceneRichTerminal dur={s4} />
      </Sequence>
      <Sequence from={s1 + s2 + s3 + s4} durationInFrames={s5}>
        <SceneCTA dur={s5} />
      </Sequence>
    </AbsoluteFill>
  );
};
