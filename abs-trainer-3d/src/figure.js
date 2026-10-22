import * as THREE from 'three';

// Body sizes in metres.
const SIZE = {
  hipWidth: 0.1,
  torso: 0.5,
  shoulderWidth: 0.2,
  upperArm: 0.29,
  forearm: 0.27,
  thigh: 0.44,
  shin: 0.43,
};

const DEG = Math.PI / 180;

// Pose keys. All angles are in degrees. root.y is in metres.
export const POSE_KEYS = [
  'root.y', 'root.z', 'root.rx', 'root.ry', 'root.rz',
  'spine.x', 'spine.y', 'spine.z',
  'head.x', 'head.y',
  'lShoulder.x', 'lShoulder.y', 'lShoulder.z', 'lElbow.x',
  'rShoulder.x', 'rShoulder.y', 'rShoulder.z', 'rElbow.x',
  'lHip.x', 'lHip.y', 'lHip.z', 'lKnee.x', 'lAnkle.x',
  'rHip.x', 'rHip.y', 'rHip.z', 'rKnee.x', 'rAnkle.x',
];

export function flattenPose(pose) {
  const flat = {};
  for (const key of POSE_KEYS) {
    const [joint, axis] = key.split('.');
    flat[key] = pose[joint]?.[axis] ?? 0;
  }
  return flat;
}

function capsule(radius, length, material) {
  const geo = new THREE.CapsuleGeometry(radius, length, 6, 14);
  geo.translate(0, -length / 2, 0);
  const mesh = new THREE.Mesh(geo, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

export function createDumbbell(scale = 1) {
  const group = new THREE.Group();
  const plateMat = new THREE.MeshStandardMaterial({ color: 0x1b1b1f, roughness: 0.55, metalness: 0.2 });
  const handleMat = new THREE.MeshStandardMaterial({ color: 0xb8bcc4, roughness: 0.3, metalness: 0.9 });
  const ringMat = new THREE.MeshStandardMaterial({ color: 0x9be15d, roughness: 0.5 });
  const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 0.16, 16), handleMat);
  group.add(handle);
  for (const sign of [-1, 1]) {
    const plate = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.07, 28), plateMat);
    plate.position.y = sign * 0.11;
    plate.castShadow = true;
    group.add(plate);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.006, 8, 28), ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = sign * 0.146;
    group.add(ring);
  }
  group.scale.setScalar(scale);
  return group;
}

export function createFigure() {
  const skin = new THREE.MeshStandardMaterial({ color: 0xd9a27c, roughness: 0.6 });
  const shirt = new THREE.MeshStandardMaterial({ color: 0x24262c, roughness: 0.8 });
  const shorts = new THREE.MeshStandardMaterial({ color: 0x15161a, roughness: 0.85 });
  const sock = new THREE.MeshStandardMaterial({ color: 0x2b2b30, roughness: 0.9 });
  const hair = new THREE.MeshStandardMaterial({ color: 0x1a1412, roughness: 0.9 });
  const absMat = new THREE.MeshStandardMaterial({
    color: 0xff5a36, emissive: 0xff2d00, emissiveIntensity: 0.0,
    transparent: true, opacity: 0.0, roughness: 0.5,
  });
  const jointMat = new THREE.MeshStandardMaterial({ color: 0x46c2ff, emissive: 0x1a6aff, emissiveIntensity: 0.6 });

  const joints = {};
  const root = new THREE.Group();
  joints.root = root;

  // Pelvis
  const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 14), shorts);
  pelvis.scale.set(1.15, 0.75, 0.85);
  pelvis.position.y = 0.02;
  pelvis.castShadow = true;
  root.add(pelvis);

  // Spine / torso
  const spine = new THREE.Group();
  spine.position.y = 0.06;
  root.add(spine);
  joints.spine = spine;

  const waist = capsule(0.125, 0.18, shirt);
  waist.rotation.z = Math.PI; // grow upwards
  waist.position.y = 0.0;
  waist.scale.set(1.1, 1, 0.8);
  spine.add(waist);
  const chest = capsule(0.15, 0.2, shirt);
  chest.rotation.z = Math.PI;
  chest.position.y = 0.18;
  chest.scale.set(1.25, 1, 0.85);
  spine.add(chest);

  // Abs highlight (front of the waist)
  const abs = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.2, 4, 12), absMat);
  abs.scale.set(1.25, 1, 0.45);
  abs.position.set(0, 0.17, 0.09);
  abs.renderOrder = 2;
  spine.add(abs);

  const neck = new THREE.Group();
  neck.position.y = SIZE.torso;
  spine.add(neck);
  joints.head = neck;
  const neckMesh = capsule(0.05, 0.06, skin);
  neckMesh.rotation.z = Math.PI;
  neck.add(neckMesh);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.105, 24, 18), skin);
  head.scale.set(0.92, 1.1, 1);
  head.position.y = 0.15;
  head.castShadow = true;
  neck.add(head);
  const hairMesh = new THREE.Mesh(new THREE.SphereGeometry(0.108, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2.4), hair);
  hairMesh.scale.set(0.6, 1.1, 1.05);
  hairMesh.position.y = 0.16;
  neck.add(hairMesh);
  const beard = new THREE.Mesh(new THREE.SphereGeometry(0.08, 16, 12, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), hair);
  beard.position.set(0, 0.12, 0.035);
  beard.scale.set(1, 1.1, 0.9);
  neck.add(beard);
  // Nose: shows where the face points
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.018, 0.04, 10), skin);
  nose.rotation.x = Math.PI / 2;
  nose.position.set(0, 0.16, 0.105);
  neck.add(nose);

  // Arms
  for (const side of ['l', 'r']) {
    const sign = side === 'l' ? 1 : -1;
    const shoulder = new THREE.Group();
    shoulder.position.set(sign * SIZE.shoulderWidth, SIZE.torso - 0.06, 0);
    spine.add(shoulder);
    joints[side + 'Shoulder'] = shoulder;
    const deltoid = new THREE.Mesh(new THREE.SphereGeometry(0.068, 16, 12), skin);
    deltoid.castShadow = true;
    shoulder.add(deltoid);
    shoulder.add(capsule(0.055, SIZE.upperArm, skin));

    const elbow = new THREE.Group();
    elbow.position.y = -SIZE.upperArm;
    shoulder.add(elbow);
    joints[side + 'Elbow'] = elbow;
    elbow.add(capsule(0.045, SIZE.forearm, skin));
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.045, 14, 10), skin);
    hand.scale.set(0.8, 1.2, 0.6);
    hand.position.y = -SIZE.forearm - 0.04;
    hand.castShadow = true;
    elbow.add(hand);

    // Dumbbell held in the hand (hidden by default)
    const held = createDumbbell(0.85);
    held.rotation.z = Math.PI / 2;
    held.position.y = -SIZE.forearm - 0.05;
    held.visible = false;
    elbow.add(held);
    joints[side + 'Held'] = held;

    const elbowDot = new THREE.Mesh(new THREE.SphereGeometry(0.02, 8, 6), jointMat);
    elbowDot.userData.jointMarker = true;
    elbow.add(elbowDot);
  }

  // Legs
  for (const side of ['l', 'r']) {
    const sign = side === 'l' ? 1 : -1;
    const hip = new THREE.Group();
    hip.position.set(sign * SIZE.hipWidth, 0, 0);
    root.add(hip);
    joints[side + 'Hip'] = hip;
    const thigh = capsule(0.085, SIZE.thigh, shorts);
    hip.add(thigh);
    // Bare part of the thigh (shorts end above the knee)
    const lowerThigh = capsule(0.075, 0.14, skin);
    lowerThigh.position.y = -SIZE.thigh + 0.16;
    hip.add(lowerThigh);

    const knee = new THREE.Group();
    knee.position.y = -SIZE.thigh;
    hip.add(knee);
    joints[side + 'Knee'] = knee;
    knee.add(capsule(0.06, SIZE.shin, skin));

    const ankle = new THREE.Group();
    ankle.position.y = -SIZE.shin;
    knee.add(ankle);
    joints[side + 'Ankle'] = ankle;
    const foot = new THREE.Mesh(new THREE.CapsuleGeometry(0.045, 0.14, 4, 10), sock);
    foot.rotation.x = Math.PI / 2;
    foot.position.set(0, -0.04, 0.06);
    foot.castShadow = true;
    ankle.add(foot);

    const kneeDot = new THREE.Mesh(new THREE.SphereGeometry(0.022, 8, 6), jointMat);
    kneeDot.userData.jointMarker = true;
    knee.add(kneeDot);
  }

  for (const j of Object.values(joints)) j.rotation.order = 'XYZ';

  return { root, joints, absMat };
}

export function applyPose(figure, flat) {
  const { joints } = figure;
  joints.root.position.set(0, flat['root.y'], flat['root.z']);
  joints.root.rotation.set(flat['root.rx'] * DEG, flat['root.ry'] * DEG, flat['root.rz'] * DEG);
  joints.spine.rotation.set(flat['spine.x'] * DEG, flat['spine.y'] * DEG, flat['spine.z'] * DEG);
  joints.head.rotation.set(flat['head.x'] * DEG, flat['head.y'] * DEG, 0);
  for (const s of ['l', 'r']) {
    joints[s + 'Shoulder'].rotation.set(flat[s + 'Shoulder.x'] * DEG, flat[s + 'Shoulder.y'] * DEG, flat[s + 'Shoulder.z'] * DEG);
    joints[s + 'Elbow'].rotation.set(flat[s + 'Elbow.x'] * DEG, 0, 0);
    joints[s + 'Hip'].rotation.set(flat[s + 'Hip.x'] * DEG, flat[s + 'Hip.y'] * DEG, flat[s + 'Hip.z'] * DEG);
    joints[s + 'Knee'].rotation.set(flat[s + 'Knee.x'] * DEG, 0, 0);
    joints[s + 'Ankle'].rotation.set(flat[s + 'Ankle.x'] * DEG, 0, 0);
  }
}

export function setHeldDumbbells(figure, mode) {
  figure.joints.lHeld.visible = mode === 'both' || mode === 'left';
  figure.joints.rHeld.visible = mode === 'both' || mode === 'right';
}

// Make a see-through copy of the figure (for "ghost" start/end poses).
export function createGhost(color) {
  const fig = createFigure();
  const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.18, depthWrite: false });
  fig.root.traverse((o) => {
    if (o.isMesh) {
      o.material = mat;
      o.castShadow = false;
      o.receiveShadow = false;
      if (o.userData.jointMarker) o.visible = false;
    }
  });
  return fig;
}
