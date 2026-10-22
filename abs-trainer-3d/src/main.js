import '@fontsource/vazirmatn/400.css';
import '@fontsource/vazirmatn/700.css';
import '@fontsource/vazirmatn/800.css';
import './style.css';

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { createFigure, createGhost, createDumbbell, applyPose, flattenPose, setHeldDumbbells, POSE_KEYS } from './figure.js';
import { EXERCISES, mirrorFlat } from './exercises.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const faNum = (n) => String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]);

// ---------- Scene ----------
const viewport = $('viewport');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: params.has('shot') });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
viewport.prepend(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x15161b);
scene.fog = new THREE.Fog(0x15161b, 6, 14);

const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 50);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.minDistance = 1;
controls.maxDistance = 7;
controls.maxPolarAngle = Math.PI * 0.495;
controls.autoRotateSpeed = 1.2;

scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x2a1e18, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(2.5, 4.5, 3);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -2, right: 2, top: 2, bottom: -2, near: 0.5, far: 12 });
sun.shadow.bias = -0.0005;
scene.add(sun);
const rim = new THREE.DirectionalLight(0xff8a3d, 0.9);
rim.position.set(-3, 2, -3);
scene.add(rim);

// Gym floor with orange lines, like in the video
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(14, 14),
  new THREE.MeshStandardMaterial({ color: 0x2b2d33, roughness: 0.95 }),
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);
const lineMat = new THREE.MeshStandardMaterial({ color: 0xff7a1a, roughness: 0.7 });
for (const [w, d, x, z] of [[0.06, 3.2, 1.05, 0.3], [0.06, 3.2, -1.05, 0.3], [2.16, 0.06, 0, 1.9]]) {
  const line = new THREE.Mesh(new THREE.PlaneGeometry(w, d), lineMat);
  line.rotation.x = -Math.PI / 2;
  line.position.set(x, 0.002, z);
  line.receiveShadow = true;
  scene.add(line);
}
const grid = new THREE.GridHelper(6, 30, 0x3a3e48, 0x30333c);
grid.position.y = 0.001;
grid.material.transparent = true;
grid.material.opacity = 0.35;
scene.add(grid);

const figure = createFigure();
scene.add(figure.root);
const ghostStart = createGhost(0x46c2ff);
const ghostPeak = createGhost(0xff7a1a);
scene.add(ghostStart.root, ghostPeak.root);

const propGroup = new THREE.Group();
scene.add(propGroup);

// ---------- Camera presets ----------
const CAMS = {
  front: { pos: [0, 0.9, 2.7], target: [0, 0.3, 0.25] },
  side: { pos: [2.7, 0.75, 0.3], target: [0, 0.3, 0.25] },
  diag: { pos: [2.0, 1.25, 2.1], target: [0, 0.3, 0.2] },
  top: { pos: [0, 3.1, 0.6], target: [0, 0, 0.25] },
};
let camTween = null;
function setCamera(name, instant = false) {
  const c = CAMS[name];
  const to = { pos: new THREE.Vector3(...c.pos), target: new THREE.Vector3(...c.target) };
  if (instant) {
    camera.position.copy(to.pos);
    controls.target.copy(to.target);
    controls.update();
    return;
  }
  camTween = { from: { pos: camera.position.clone(), target: controls.target.clone() }, to, t: 0 };
}
document.querySelectorAll('[data-cam]').forEach((b) => b.addEventListener('click', () => setCamera(b.dataset.cam)));
$('autoRotate').addEventListener('click', (e) => {
  controls.autoRotate = !controls.autoRotate;
  e.currentTarget.classList.toggle('on', controls.autoRotate);
});

// ---------- Exercise data ----------
for (const ex of EXERCISES) {
  ex.flatKeys = ex.keys.map((k) => ({ ...k }));
  ex.flatKeys.forEach((k, i) => {
    k.flat = k.mirrorOf !== undefined ? mirrorFlat(ex.flatKeys[k.mirrorOf].flat) : flattenPose(k.pose);
    if (k.mirrorOf !== undefined && i < k.mirrorOf) throw new Error('mirrorOf must point back');
  });
  ex.peakIndex = ex.flatKeys.reduce((best, k, i) => (k.abs > ex.flatKeys[best].abs ? i : best), 0);
}

const smooth = (x) => x * x * (3 - 2 * x);

function sample(ex, t, mirrored) {
  const keys = ex.flatKeys;
  let i = 0;
  while (i < keys.length - 2 && t >= keys[i + 1].t) i++;
  const a = keys[i];
  const b = keys[i + 1];
  const s = smooth(THREE.MathUtils.clamp((t - a.t) / (b.t - a.t), 0, 1));
  const flat = {};
  for (const key of POSE_KEYS) flat[key] = a.flat[key] + (b.flat[key] - a.flat[key]) * s;
  return {
    flat: mirrored ? mirrorFlat(flat) : flat,
    abs: a.abs + (b.abs - a.abs) * s,
    label: s < 0.5 ? a.label : b.label,
    segment: i,
  };
}

// ---------- State ----------
const state = {
  ex: EXERCISES[0],
  t: 0,
  playing: true,
  speed: 1,
  mirrored: false,
  showGhost: false,
  showMuscle: true,
  workout: null,
};

function buildList() {
  const list = $('exerciseList');
  list.innerHTML = '';
  EXERCISES.forEach((ex, i) => {
    const li = document.createElement('li');
    li.dataset.index = i;
    li.innerHTML = `<div><div class="name"></div><div class="dose"></div></div>`;
    li.querySelector('.name').textContent = ex.name;
    li.querySelector('.dose').textContent = ex.dose;
    li.addEventListener('click', () => {
      if (state.workout) stopWorkout();
      selectExercise(i);
    });
    list.appendChild(li);
  });
}

function fillList(el, items) {
  el.innerHTML = '';
  for (const text of items) {
    const li = document.createElement('li');
    li.textContent = text;
    el.appendChild(li);
  }
}

function selectExercise(index, mirrored = false) {
  const ex = EXERCISES[index];
  state.ex = ex;
  state.t = 0;
  state.mirrored = mirrored;
  document.querySelectorAll('#exerciseList li').forEach((li) => li.classList.toggle('active', Number(li.dataset.index) === index));
  $('exTitle').textContent = `${faNum(index + 1)}. ${ex.name}`;
  $('exDose').textContent = `${ex.dose} · ${ex.en}`;
  fillList($('steps'), ex.steps);
  fillList($('cues'), ex.cues);
  fillList($('mistakes'), ex.mistakes);
  $('muscles').innerHTML = ex.muscles.map((m) => `<span>${m}</span>`).join('');
  $('exNote').textContent = ex.note || '';
  $('exNote').classList.toggle('hidden', !ex.note);
  $('switchSide').classList.toggle('hidden', !ex.sides);
  setHeldDumbbells(figure, ex.held);
  setHeldDumbbells(ghostStart, ex.held);
  setHeldDumbbells(ghostPeak, ex.held);
  buildProps();
  buildTicks();
  updateSideBadge();
  syncVideoToExercise();
}

function buildProps() {
  propGroup.clear();
  for (const p of state.ex.props) {
    const db = createDumbbell(1);
    const x = state.mirrored ? -p.pos[0] : p.pos[0];
    if (p.upright) db.position.set(x, 0.146, p.pos[2]);
    else {
      db.rotation.z = Math.PI / 2;
      db.position.set(x, 0.075, p.pos[2]);
    }
    db.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    propGroup.add(db);
  }
}

function buildTicks() {
  const ticks = $('ticks');
  ticks.innerHTML = '';
  state.ex.flatKeys.forEach((k, i) => {
    if (i === state.ex.flatKeys.length - 1) return;
    const span = document.createElement('span');
    span.style.left = `${k.t * 100}%`;
    span.title = k.label;
    span.addEventListener('click', () => { state.t = k.t; setPlaying(false); });
    ticks.appendChild(span);
  });
}

function updateSideBadge() {
  const badge = $('sideBadge');
  if (!state.ex.sides) { badge.classList.add('hidden'); return; }
  badge.classList.remove('hidden');
  badge.textContent = state.mirrored ? 'طرف راست' : 'طرف چپ';
}

function setPlaying(p) {
  state.playing = p;
  $('playBtn').textContent = p ? '⏸' : '▶';
  const v = $('refVideo');
  if (v.src) (p ? v.play().catch(() => {}) : v.pause());
}

// ---------- Controls ----------
$('playBtn').addEventListener('click', () => setPlaying(!state.playing));
$('speed').addEventListener('change', (e) => {
  state.speed = Number(e.target.value);
  $('refVideo').playbackRate = state.speed;
});
$('timeline').addEventListener('input', (e) => {
  state.t = Number(e.target.value) / 1000;
  setPlaying(false);
});
function stepKey(dir) {
  setPlaying(false);
  const times = state.ex.flatKeys.map((k) => k.t);
  if (dir > 0) state.t = times.find((t) => t > state.t + 0.001) ?? 0;
  else state.t = [...times].reverse().find((t) => t < state.t - 0.001) ?? times[times.length - 2];
  if (state.t >= 1) state.t = 0;
}
$('prevKey').addEventListener('click', () => stepKey(-1));
$('nextKey').addEventListener('click', () => stepKey(1));
$('ghostToggle').addEventListener('change', (e) => { state.showGhost = e.target.checked; });
$('muscleToggle').addEventListener('change', (e) => { state.showMuscle = e.target.checked; });
$('jointToggle').addEventListener('change', (e) => {
  figure.root.traverse((o) => { if (o.userData.jointMarker) o.visible = e.target.checked; });
});
$('switchSide').addEventListener('click', () => {
  state.mirrored = !state.mirrored;
  buildProps();
  updateSideBadge();
});
window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.code === 'Space') { e.preventDefault(); setPlaying(!state.playing); }
  if (e.code === 'ArrowLeft') stepKey(1);
  if (e.code === 'ArrowRight') stepKey(-1);
});

// ---------- Reference video ----------
$('videoFile').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const v = $('refVideo');
  v.src = URL.createObjectURL(file);
  v.classList.remove('hidden');
  v.playbackRate = state.speed;
  v.addEventListener('loadedmetadata', syncVideoToExercise, { once: true });
});
function syncVideoToExercise() {
  const v = $('refVideo');
  if (!v.src) return;
  v.currentTime = state.ex.video[0];
  if (state.playing) v.play().catch(() => {});
}
$('refVideo').addEventListener('timeupdate', () => {
  const v = $('refVideo');
  if (v.currentTime >= state.ex.video[1] || v.currentTime < state.ex.video[0] - 0.5) v.currentTime = state.ex.video[0];
});

// ---------- Sound ----------
let audioCtx = null;
function beep(freq = 880, dur = 0.12) {
  try {
    audioCtx ??= new AudioContext();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + dur);
  } catch { /* no audio */ }
}

// ---------- Workout mode ----------
// Steps: countdown -> work -> (rest) -> next set / next side / next exercise.
function buildPlan() {
  const sets = Number($('setsInput').value) || 3;
  const plan = [];
  EXERCISES.forEach((ex, index) => {
    for (let s = 1; s <= sets; s++) {
      const sides = ex.sides ? [false, true] : [false];
      for (const mirrored of sides) plan.push({ index, set: s, sets, mirrored });
    }
  });
  return plan;
}

function startWorkout() {
  state.workout = { plan: buildPlan(), step: 0, phase: 'countdown', left: 5, reps: 0, paused: false };
  $('workoutHud').classList.remove('hidden');
  $('workoutBtn').textContent = '■ پایان تمرین';
  enterStep();
}

function stopWorkout() {
  state.workout = null;
  $('workoutHud').classList.add('hidden');
  $('workoutBtn').textContent = '▶ شروع تمرین کامل';
  setPlaying(true);
}

function enterStep() {
  const w = state.workout;
  const item = w.plan[w.step];
  if (!item) {
    $('hudStatus').textContent = 'تمام شد!';
    $('hudBig').textContent = '🎉';
    $('hudSub').textContent = 'آفرین! همه حرکت‌ها انجام شد.';
    w.phase = 'done';
    setPlaying(false);
    beep(660, 0.2); setTimeout(() => beep(990, 0.3), 220);
    return;
  }
  selectExercise(item.index, item.mirrored);
  w.phase = 'countdown';
  w.left = 5;
  w.reps = 0;
  w.lastCycle = 0;
  setPlaying(false);
  state.t = 0;
}

function workoutTick(dt) {
  const w = state.workout;
  if (!w || w.paused || w.phase === 'done') return;
  const item = w.plan[w.step];
  const ex = EXERCISES[item.index];
  const sideText = ex.sides ? (item.mirrored ? ' · طرف راست' : ' · طرف چپ') : '';
  const setText = `ست ${faNum(item.set)} از ${faNum(item.sets)}${sideText}`;

  if (w.phase === 'countdown') {
    const before = Math.ceil(w.left);
    w.left -= dt;
    if (Math.ceil(w.left) !== before && w.left > 0) beep(660);
    $('hudStatus').textContent = `آماده شو · ${setText}`;
    $('hudBig').textContent = faNum(Math.max(1, Math.ceil(w.left)));
    $('hudSub').textContent = ex.name;
    if (w.left <= 0) {
      w.phase = 'work';
      w.left = ex.target;
      w.reps = 0;
      w.progress = 0;
      state.t = 0;
      setPlaying(true);
      beep(1100, 0.25);
    }
  } else if (w.phase === 'work') {
    $('hudStatus').textContent = setText;
    if (ex.type === 'time') {
      w.left -= dt;
      $('hudBig').textContent = faNum(Math.max(0, Math.ceil(w.left)));
      $('hudSub').textContent = 'ثانیه باقی‌مانده';
      if (w.left <= 0) finishWork();
    } else {
      $('hudBig').textContent = `${faNum(w.reps)}/${faNum(ex.target)}`;
      $('hudSub').textContent = 'تکرار';
      if (w.reps >= ex.target) finishWork();
    }
  } else if (w.phase === 'rest') {
    const before = Math.ceil(w.left);
    w.left -= dt;
    if (w.left <= 3 && Math.ceil(w.left) !== before && w.left > 0) beep(660);
    $('hudStatus').textContent = 'استراحت';
    $('hudBig').textContent = faNum(Math.max(0, Math.ceil(w.left)));
    const next = w.plan[w.step + 1];
    $('hudSub').textContent = next ? `بعدی: ${EXERCISES[next.index].name}` : '';
    if (w.left <= 0) {
      w.step++;
      enterStep();
    }
  }
}

function finishWork() {
  const w = state.workout;
  beep(990, 0.3);
  const next = w.plan[w.step + 1];
  const item = w.plan[w.step];
  // No rest between the left and right side of the same set.
  if (next && next.index === item.index && next.set === item.set) {
    w.step++;
    enterStep();
    w.left = 3;
    return;
  }
  w.phase = 'rest';
  w.left = Number($('restInput').value) || 30;
  setPlaying(false);
}

// Called by the animation loop when the playhead moves forward.
function countReps(prevT, newT, wrapped) {
  const w = state.workout;
  if (!w || w.phase !== 'work' || state.ex.type !== 'reps') return;
  const n = state.ex.repsPerCycle;
  const before = Math.floor(prevT * n);
  const after = wrapped ? n + Math.floor(newT * n) : Math.floor(newT * n);
  if (after > before) {
    w.reps += after - before;
    beep(1320, 0.06);
  }
}

$('workoutBtn').addEventListener('click', () => (state.workout ? stopWorkout() : startWorkout()));
$('hudStop').addEventListener('click', stopWorkout);
$('hudPause').addEventListener('click', (e) => {
  const w = state.workout;
  if (!w) return;
  w.paused = !w.paused;
  e.currentTarget.textContent = w.paused ? '▶ ادامه' : '⏸ توقف';
  if (w.phase === 'work') setPlaying(!w.paused);
});
$('hudSkip').addEventListener('click', () => {
  const w = state.workout;
  if (!w || w.phase === 'done') return;
  w.step++;
  enterStep();
});

// ---------- Loop ----------
function resize() {
  const { clientWidth: w, clientHeight: h } = viewport;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  // Portrait screens (phones): widen the view so the whole body stays visible.
  camera.fov = camera.aspect < 1 ? Math.min(75, (42 / camera.aspect) * 0.75) : 42;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(viewport);

const clock = new THREE.Clock();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.1);

  if (state.playing) {
    const prev = state.t;
    state.t += (dt * state.speed) / state.ex.cycle;
    const wrapped = state.t >= 1;
    if (wrapped) state.t -= 1;
    countReps(prev, state.t, wrapped);
  }
  workoutTick(dt);

  const s = sample(state.ex, state.t, state.mirrored);
  applyPose(figure, s.flat);
  figure.absMat.opacity = state.showMuscle ? 0.25 + 0.6 * s.abs : 0;
  figure.absMat.emissiveIntensity = state.showMuscle ? 0.2 + 1.6 * s.abs : 0;
  $('effortFill').style.width = `${Math.round(s.abs * 100)}%`;
  $('phaseLabel').textContent = s.label;
  $('timeline').value = Math.round(state.t * 1000);

  ghostStart.root.visible = ghostPeak.root.visible = state.showGhost;
  if (state.showGhost) {
    const keys = state.ex.flatKeys;
    applyPose(ghostStart, state.mirrored ? mirrorFlat(keys[0].flat) : keys[0].flat);
    const peak = keys[state.ex.peakIndex].flat;
    applyPose(ghostPeak, state.mirrored ? mirrorFlat(peak) : peak);
  }

  if (camTween) {
    camTween.t = Math.min(1, camTween.t + dt * 2.2);
    const k = smooth(camTween.t);
    camera.position.lerpVectors(camTween.from.pos, camTween.to.pos, k);
    controls.target.lerpVectors(camTween.from.target, camTween.to.target, k);
    if (camTween.t >= 1) camTween = null;
  }
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

// ---------- Start ----------
buildList();
const startIndex = Math.max(0, EXERCISES.findIndex((e) => e.id === params.get('ex')));
selectExercise(startIndex, params.get('side') === 'r');
setCamera(params.get('cam') || 'diag', true);
if (params.has('t')) {
  state.t = Number(params.get('t'));
  setPlaying(false);
}
if (params.has('ghost')) {
  state.showGhost = true;
  $('ghostToggle').checked = true;
}
resize();
frame();
