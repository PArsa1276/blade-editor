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

// Kinetic words: one word at a time, big, on a beat grid (beat = seconds per word, e.g. from
// analyze_music); each punches in (scale overshoot) and the previous one leaves fast; key words
// (in "highlight") get the accent colour and a bigger punch.
const Kinetic = ({ text, beat, highlight, color, accent, size }: any) => {
  const frame = useCurrentFrame();
  const total = Math.round(DUR * FPS);
  const words = String(text).split(/\s+/).filter(Boolean);
  const step = Math.max(4, Math.round(Number(beat) * FPS));
  const i = Math.min(words.length - 1, Math.floor(frame / step));
  const local = frame - i * step;
  const key = String(highlight ?? "").split(/[\s,]+/).filter(Boolean).includes(words[i]);
  const s = spring({ frame: local, fps: FPS, config: { damping: key ? 8 : 12, stiffness: 220 } });
  const leave = i < words.length - 1 ? interpolate(local, [step - 3, step], [0, 1], clamp) : exitT(frame, total);
  const shake = key && local < 6 ? Math.sin(local * 3) * 8 * k : 0;
  const fs = (size ?? 170) * k * (key ? 1.25 : 1);
  return (
    <AbsoluteFill>
      <div dir={RTL.test(words[i]) ? "rtl" : "ltr"} style={{ position: "absolute", top: H * 0.45 - fs * 0.6, width: "100%",
        textAlign: "center", fontFamily: "Vazirmatn", fontSize: fs, color: key ? accent : color,
        opacity: Math.min(1, s * 1.5) * (1 - leave), textShadow: "0 8px 30px rgba(0,0,0,0.5)",
        transform: `translateX(${shake}px) scale(${(0.5 + 0.5 * s) * (1 + leave * 0.3)})` }}>{words[i]}</div>
    </AbsoluteFill>);
};
registerRoot(() => <Composition id="Main" component={Kinetic} durationInFrames={Math.round(DUR * FPS)} fps={FPS} width={W} height={H}
  background={env.BLADE_BG ?? "transparent"} defaultProps={{ text: "MAKE IT LOUD", beat: 0.5, highlight: "LOUD", color: "#FFFFFF", accent: "#FFD400", size: 170 }} />);
