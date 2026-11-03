import { AbsoluteFill, Composition, Layer, Rect, Ellipse, interpolate, registerRoot, spring, Easing,
         useCurrentFrame, useVideoConfig, registerFont, staticFile, glow } from "@kinetographdev/core";

const env = ((globalThis as any).process?.env ?? {}) as Record<string, string>;
const W = Number(env.BLADE_W ?? 1080), H = Number(env.BLADE_H ?? 1920);
const FPS = Number(env.BLADE_FPS ?? 30), DUR = Number(env.BLADE_DUR ?? 3);
registerFont({ family: "Vazirmatn", path: staticFile("Vazirmatn-Black.ttf") });
const RTL = /[֐-ࣿ]/;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const k = Math.min(W, H) / 1080;
// Exit: the last 0.45 s, faster than the entrance; gone before the last frame.
const exitT = (frame: number, total: number) =>
  interpolate(frame, [total - Math.round(0.45 * FPS), total - 2], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });

// Big title: words rise in with a staggered spring (overshoot), an accent bar draws under it,
// a ring expands at the landing (payoff), a slow float during the hold, fast exit.
const Word = ({ w, i, color }: { w: string; i: number; color: string }) => {
  const frame = useCurrentFrame();
  const s = spring({ frame: frame - i * 4, fps: FPS, config: { damping: 11, stiffness: 140 } });
  return <span style={{ display: "inline-block", margin: "0 0.12em", color,
    transform: `translateY(${(1 - s) * 90 * k}px) scale(${0.6 + 0.4 * s})`, opacity: Math.min(1, s * 1.4) }}>{w}</span>;
};
const Title = ({ text, subtitle, color, accent, size }: any) => {
  const frame = useCurrentFrame();
  const total = Math.round(DUR * FPS);
  const words = String(text).split(/\s+/).filter(Boolean);
  const landed = words.length * 4 + 10;
  const out = exitT(frame, total);
  const float = Math.sin(frame / FPS * 2.2) * 6 * k * (frame > landed ? 1 : 0);
  const bar = interpolate(frame, [landed - 6, landed + 10], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const ring = frame >= landed ? interpolate(frame, [landed, landed + 18], [0, 1], clamp) : 0;
  const sub = interpolate(frame, [landed + 4, landed + 16], [0, 1], clamp);
  const fs = (size ?? 150) * k;
  const cy = H * 0.45;
  return (
    <AbsoluteFill style={{ opacity: 1 - out }}>
      {ring > 0 && ring < 1 ? (
        <Layer x={W / 2} y={cy} scale={0.4 + ring * 1.4} origin="center" opacity={1 - ring}>
          <Ellipse width={W * 0.7} height={W * 0.7} x={-W * 0.35} y={-W * 0.35} fill="transparent" stroke={{ color: accent, width: 6 * k }} />
        </Layer>) : null}
      <Layer x={W / 2 - (W * 0.55 * bar) / 2} y={cy + fs * 0.75 + float}>
        <Rect width={W * 0.55 * bar} height={14 * k} radius={7 * k} fill={accent} effects={[glow({ radius: 18 * k })]} />
      </Layer>
      <div dir={RTL.test(text) ? "rtl" : "ltr"} style={{ position: "absolute", top: cy - fs * 0.7 + float - out * 60 * k,
        width: "100%", display: "flex", justifyContent: "center", flexWrap: "wrap", fontFamily: "Vazirmatn",
        fontSize: fs, lineHeight: 1.1, textShadow: "0 6px 24px rgba(0,0,0,0.45)" }}>
        {words.map((w: string, i: number) => <Word key={i} w={w} i={i} color={color} />)}
      </div>
      {subtitle ? <div dir={RTL.test(subtitle) ? "rtl" : "ltr"} style={{ position: "absolute", top: cy + fs * 0.95 + float,
        width: "100%", textAlign: "center", fontFamily: "Vazirmatn", fontSize: fs * 0.36, color,
        opacity: sub * 0.85, transform: `translateY(${(1 - sub) * 20 * k}px)` }}>{subtitle}</div> : null}
    </AbsoluteFill>);
};
registerRoot(() => <Composition id="Main" component={Title} durationInFrames={Math.round(DUR * FPS)} fps={FPS} width={W} height={H}
  background={env.BLADE_BG ?? "transparent"} defaultProps={{ text: "BLADE EDITOR", subtitle: "", color: "#FFFFFF", accent: "#FFD400", size: 150 }} />);
