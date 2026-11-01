// 3D turn of a video clip around the vertical axis, with stops (Kinetograph).
// Put the clip in public/clip.mp4 next to this file. Props: {"stops": [0, 180, 360], "turnFrames": 18}
import { AbsoluteFill, Camera, Composition, Layer, Video, Easing, interpolate, registerRoot,
         staticFile, useCurrentFrame, useVideoConfig, dropShadow } from '@kinetographdev/core';

type Props = { stops: number[]; turnFrames: number; holdFrames: number };

const Spin = ({ stops, turnFrames, holdFrames }: Props) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  // Keyframes: hold at each stop, then an eased turn to the next one.
  const times: number[] = [], angles: number[] = [];
  let t = 0;
  stops.forEach((a, i) => {
    times.push(t); angles.push(a); t += holdFrames;
    if (i < stops.length - 1) { times.push(t); angles.push(a); t += turnFrames; }
  });
  const rotateY = interpolate(frame, times, angles, {
    easing: Easing.inOut(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill>
      <Camera perspective={1400} />
      <Layer x={width / 2} y={height / 2} origin="center" rotateY={rotateY}
             effects={[dropShadow({ y: 30, blur: 60, color: 'rgba(0,0,0,0.6)' })]}>
        <Video src={staticFile('clip.mp4')} width={width * 0.8} height={height * 0.8}
               x={-width * 0.4} y={-height * 0.4} fit="cover" />
      </Layer>
    </AbsoluteFill>
  );
};

registerRoot(() => (
  <Composition id="Spin3D" component={Spin} durationInFrames={120} fps={30} width={1080} height={1920}
    background={(globalThis as any).process?.env?.BLADE_BG ?? '#000000'}
    defaultProps={{ stops: [0, 180, 360], turnFrames: 18, holdFrames: 24 }} />
));
