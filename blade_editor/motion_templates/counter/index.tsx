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

// Counter: counts up with an ease-out (clamped, so it lands exactly on the value), tabular digits
// (no jitter), a scale pop + ring at the landing (payoff), label fades in under it.
const Counter = ({ value, prefix, suffix, label, color, accent }: any) => {
  const frame = useCurrentFrame();
  const total = Math.round(DUR * FPS);
  const end = Math.round(Math.min(total * 0.55, 1.6 * FPS));
  const t = interpolate(frame, [4, end], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const shown = Math.round(Number(value) * t).toLocaleString("en-US");
  const pop = frame >= end ? spring({ frame: frame - end, fps: FPS, config: { damping: 9, stiffness: 200 } }) : 0;
  const scale = 1 + 0.12 * Math.sin(Math.min(1, pop) * Math.PI);
  const ring = frame >= end ? interpolate(frame, [end, end + 16], [0, 1], clamp) : 0;
  const enter = spring({ frame, fps: FPS, config: { damping: 13 } });
  const out = exitT(frame, total);
  const lab = interpolate(frame, [end - 4, end + 8], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ opacity: 1 - out }}>
      {ring > 0 && ring < 1 ? <Layer x={W / 2} y={H * 0.45} scale={0.5 + ring} origin="center" opacity={1 - ring}>
        <Ellipse width={W * 0.6} height={W * 0.6} x={-W * 0.3} y={-W * 0.3} fill="transparent" stroke={{ color: accent, width: 6 * k }} /></Layer> : null}
      <div style={{ position: "absolute", top: H * 0.45 - 120 * k, width: "100%", textAlign: "center", fontFamily: "Vazirmatn",
        fontSize: 200 * k, color, fontVariantNumeric: "tabular-nums", opacity: Math.min(1, enter * 1.5),
        transform: `translateY(${(1 - enter) * 60 * k}px) scale(${scale})`, textShadow: `0 0 40px ${accent}55` }}>
        {prefix}{shown}{suffix}</div>
      <div dir={RTL.test(label) ? "rtl" : "ltr"} style={{ position: "absolute", top: H * 0.45 + 120 * k, width: "100%",
        textAlign: "center", fontFamily: "Vazirmatn", fontSize: 54 * k, color: accent, opacity: lab }}>{label}</div>
    </AbsoluteFill>);
};
registerRoot(() => <Composition id="Main" component={Counter} durationInFrames={Math.round(DUR * FPS)} fps={FPS} width={W} height={H}
  background={env.BLADE_BG ?? "transparent"} defaultProps={{ value: 12400, prefix: "", suffix: "+", label: "followers", color: "#FFFFFF", accent: "#FFD400" }} />);
