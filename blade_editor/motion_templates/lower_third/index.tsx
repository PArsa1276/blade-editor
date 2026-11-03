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

// Lower third: an accent plate grows from the side (width, not scale: text is never squashed),
// name and role slide in staggered, a light sweep crosses the plate during the hold, fast exit.
const LowerThird = ({ name, role, color, accent, plate }: any) => {
  const frame = useCurrentFrame();
  const total = Math.round(DUR * FPS);
  const rtl = RTL.test(name + (role ?? ""));
  const grow = interpolate(frame, [0, 12], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const n = spring({ frame: frame - 6, fps: FPS, config: { damping: 14 } });
  const r = spring({ frame: frame - 10, fps: FPS, config: { damping: 14 } });
  const out = exitT(frame, total);
  const pw = W * 0.62, ph = 170 * k, x0 = rtl ? W - W * 0.06 - pw : W * 0.06, y0 = H * (H > W ? 0.64 : 0.74);  // 9:16: above the platform buttons
  const sweep = interpolate(frame, [20, 20 + FPS], [-0.2, 1.2], clamp);
  const wNow = pw * grow * (1 - out);
  return (
    <AbsoluteFill>
      <Layer x={rtl ? x0 + pw - wNow : x0} y={y0}>
        <Rect width={wNow} height={ph} radius={18 * k} fill={plate} opacity={0.88} />
      </Layer>
      <Layer x={rtl ? x0 + pw - wNow : x0} y={y0}>
        <Rect width={Math.min(wNow, 12 * k)} height={ph} radius={6 * k} fill={accent} effects={[glow({ radius: 12 * k })]} />
      </Layer>
      {sweep > 0 && sweep < 1 ? <Layer x={x0 + pw * sweep} y={y0} opacity={0.18}><Rect width={40 * k} height={ph} fill="#FFFFFF" /></Layer> : null}
      <div dir={rtl ? "rtl" : "ltr"} style={{ position: "absolute", top: y0 + 18 * k, left: x0 + 40 * k, width: pw - 70 * k,
        fontFamily: "Vazirmatn", color, opacity: (1 - out) }}>
        <div style={{ fontSize: 64 * k, lineHeight: 1.1, opacity: n, transform: `translateX(${(rtl ? 1 : -1) * (1 - n) * 40 * k}px)` }}>{name}</div>
        <div style={{ fontSize: 34 * k, color: accent, opacity: r, transform: `translateX(${(rtl ? 1 : -1) * (1 - r) * 40 * k}px)` }}>{role}</div>
      </div>
    </AbsoluteFill>);
};
registerRoot(() => <Composition id="Main" component={LowerThird} durationInFrames={Math.round(DUR * FPS)} fps={FPS} width={W} height={H}
  background={env.BLADE_BG ?? "transparent"} defaultProps={{ name: "Parsa", role: "Video editor", color: "#FFFFFF", accent: "#FFD400", plate: "#111318" }} />);
