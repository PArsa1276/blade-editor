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

// Call to action: a pill rises with a spring, its text follows 4 frames later, a "press" at the
// payoff (scale down and back) with a ring, a soft pulse during the hold, fast exit.
const Cta = ({ text, color, accent, textColor }: any) => {
  const frame = useCurrentFrame();
  const total = Math.round(DUR * FPS);
  const rise = spring({ frame, fps: FPS, config: { damping: 12 } });
  const label = spring({ frame: frame - 4, fps: FPS, config: { damping: 14 } });
  const press = Math.round(0.9 * FPS);
  const p = frame >= press ? interpolate(frame, [press, press + 4, press + 10], [1, 0.9, 1], clamp) : 1;
  const ring = frame >= press ? interpolate(frame, [press, press + 18], [0, 1], clamp) : 0;
  const pulse = frame > press + 10 ? 1 + Math.sin((frame - press) / FPS * 4) * 0.02 : 1;
  const out = exitT(frame, total);
  const pw = W * 0.6, ph = 150 * k, y = H * (H > W ? 0.66 : 0.72);  // above the TikTok/Reels buttons
  return (
    <AbsoluteFill style={{ opacity: 1 - out }}>
      {ring > 0 && ring < 1 ? <Layer x={W / 2} y={y + ph / 2} scale={1 + ring * 0.5} origin="center" opacity={1 - ring}>
        <Rect width={pw} height={ph} x={-pw / 2} y={-ph / 2} radius={ph / 2} fill="transparent" stroke={{ color: accent, width: 5 * k }} /></Layer> : null}
      <Layer x={W / 2} y={y + ph / 2 + (1 - rise) * 200 * k} scale={p * pulse} origin="center">
        <Rect width={pw} height={ph} x={-pw / 2} y={-ph / 2} radius={ph / 2} fill={accent} effects={[glow({ radius: 24 * k })]} />
      </Layer>
      <div dir={RTL.test(text) ? "rtl" : "ltr"} style={{ position: "absolute", top: y + ph * 0.18 + (1 - rise) * 200 * k,
        width: "100%", textAlign: "center", fontFamily: "Vazirmatn", fontSize: 64 * k, color: textColor,
        opacity: label, transform: `scale(${p * pulse})` }}>{text}</div>
    </AbsoluteFill>);
};
registerRoot(() => <Composition id="Main" component={Cta} durationInFrames={Math.round(DUR * FPS)} fps={FPS} width={W} height={H}
  background={env.BLADE_BG ?? "transparent"} defaultProps={{ text: "FOLLOW", color: "#FFFFFF", accent: "#FFD400", textColor: "#111111" }} />);
