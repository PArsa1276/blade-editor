import { AbsoluteFill, Composition, Layer, Rect, Text, interpolate, registerRoot, spring,
         useCurrentFrame, useVideoConfig, registerFont, staticFile, glow } from '@kinetographdev/core';

registerFont({ family: 'Vazirmatn Black', path: staticFile('Vazirmatn-Black.ttf') });

const Title = () => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 12 } });
  const bar = interpolate(frame, [5, 25], [0, 700], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill>
      <Layer x={width / 2 - 350} y={height / 2 + 90}>
        <Rect width={bar} height={14} radius={7} fill="#FFE600" effects={[glow({ radius: 20 })]} />
      </Layer>
      <Layer x={width / 2} y={height / 2 - 120} scale={s} origin="center">
        <Text id="native" font="Vazirmatn Black" size={120} color="#fff" x={-160} y={-90}>بلید ادیتور</Text>
      </Layer>
      <div dir="rtl" style={{ position: 'absolute', top: height / 2 + 160, width: '100%', textAlign: 'center',
        fontFamily: 'Vazirmatn Black', fontSize: 64, color: '#00E5FF', opacity: interpolate(frame, [15, 30], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>
        ادیت رایگان، سریع و حرفه‌ای
      </div>
    </AbsoluteFill>
  );
};

registerRoot(() => <Composition background={(globalThis as any).process?.env?.BLADE_BG ?? "transparent"} id="Title" component={Title} durationInFrames={60} fps={30} width={1080} height={1920} />);
