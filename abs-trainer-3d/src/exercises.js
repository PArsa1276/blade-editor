// Exercises from the video, in the same order.
// Each keyframe has a time t (0..1 in one cycle), a pose and the abs effort (0..1).
// Angles are in degrees. Hip/shoulder x < 0 = move forward; knee x > 0 = bend.

const merge = (...parts) => {
  const out = {};
  for (const p of parts) {
    for (const [joint, val] of Object.entries(p)) out[joint] = { ...(out[joint] || {}), ...val };
  }
  return out;
};

// Seated on the floor, lean back, hands on the floor behind.
const SEATED = {
  root: { y: 0.13, rx: -45 },
  spine: { x: 8 },
  head: { x: 55 },
  lShoulder: { x: 58, z: 18 }, rShoulder: { x: 58, z: -18 },
  lElbow: { x: -8 }, rElbow: { x: -8 },
  lHip: { x: -75, z: 4 }, rHip: { x: -75, z: -4 },
  lKnee: { x: 55 }, rKnee: { x: 55 },
  lAnkle: { x: 10 }, rAnkle: { x: 10 },
};

// Flat on the back.
const LYING = {
  root: { y: 0.12, rx: -90 },
  spine: { x: 0 },
  head: { x: 8 },
  lShoulder: { x: -10, z: 12 }, rShoulder: { x: -10, z: -12 },
  lHip: { x: 0, z: 3 }, rHip: { x: 0, z: -3 },
  lKnee: { x: 4 }, rKnee: { x: 4 },
  lAnkle: { x: 30 }, rAnkle: { x: 30 },
};

const legs = (hip, knee, zL = 0, zR = zL, extra = {}) => ({
  lHip: { x: hip, z: zL + 4 }, rHip: { x: hip, z: zR - 4 },
  lKnee: { x: knee }, rKnee: { x: knee },
  ...extra,
});

// Swap left and right of a pose (for "each side" exercises).
export function mirrorFlat(flat) {
  const out = {};
  for (const [key, value] of Object.entries(flat)) {
    const [joint, axis] = key.split('.');
    let target = key;
    if (/^l[A-Z]/.test(joint)) target = 'r' + key.slice(1);
    else if (/^r[A-Z]/.test(joint)) target = 'l' + key.slice(1);
    // Rotations about y and z change sign in a mirror. root.y / root.z are positions.
    const isRotYZ = joint === 'root' ? axis === 'ry' || axis === 'rz' : axis === 'y' || axis === 'z';
    out[target] = isRotYZ ? -value : value;
  }
  return out;
}

export const EXERCISES = [
  {
    id: 'hops',
    name: 'پا داخل، پا بیرون',
    en: 'Seated leg hops over dumbbell',
    dose: '۳۰ تکرار',
    type: 'reps', target: 30, sets: 3,
    repsPerCycle: 2, cycle: 2.2,
    video: [8, 13],
    props: [{ pos: [0, 0, 0.72], upright: true }],
    muscles: ['راست شکمی (پایین)', 'خم‌کننده‌های لگن', 'مورب‌ها'],
    steps: [
      'روی زمین بنشین، دست‌ها پشت سر روی زمین و بالاتنه حدود ۴۵ درجه عقب.',
      'یک دمبل را عمودی جلوی پاها بگذار.',
      'پاها را جفت و زانوها را خم نگه دار؛ پاها زمین را لمس نمی‌کنند.',
      'زانوها را بالا بیاور و پاها را از روی دمبل به سمت دیگر ببر.',
      'هر بار رد شدن از روی دمبل = یک تکرار.',
    ],
    cues: ['بالاتنه ثابت بماند؛ فقط پاها حرکت کنند.', 'شکم را سفت نگه دار و نفس را حبس نکن.'],
    mistakes: ['تکیه دادن کامل به دست‌ها', 'گذاشتن پا روی زمین بین تکرارها', 'گرد کردن زیاد کمر'],
    keys: [
      { t: 0, label: 'پاها سمت چپ دمبل', abs: 0.5, pose: merge(SEATED, legs(-72, 55, 22)) },
      { t: 0.25, label: 'زانو بالا، رد شدن از روی دمبل', abs: 1, pose: merge(SEATED, { root: { rx: -52 } }, legs(-122, 122, 0)) },
      { t: 0.5, label: 'پاها سمت راست دمبل', abs: 0.5, pose: merge(SEATED, legs(-72, 55, -22)) },
      { t: 0.75, label: 'زانو بالا، رد شدن از روی دمبل', abs: 1, pose: merge(SEATED, { root: { rx: -52 } }, legs(-122, 122, 0)) },
      { t: 1, label: 'پاها سمت چپ دمبل', abs: 0.5, pose: merge(SEATED, legs(-72, 55, 22)) },
    ],
  },
  {
    id: 'tuck-open',
    name: 'پا تو، پا باز، پا بسته',
    en: 'Seated tuck – open – close',
    dose: '۱۵ تکرار',
    type: 'reps', target: 15, sets: 3,
    repsPerCycle: 1, cycle: 3.0,
    video: [13, 20],
    props: [{ pos: [0, 0, 0.72], upright: true }],
    muscles: ['راست شکمی', 'خم‌کننده‌های لگن', 'نزدیک‌کننده‌های ران'],
    steps: [
      'در همان حالت نشسته و عقب، زانوها را به سمت سینه بکش (پا تو).',
      'پاها را صاف کن و از هم باز کن؛ دمبل بین دو پا است (پا باز).',
      'پاهای صاف را به هم بچسبان، بالای دمبل (پا بسته).',
      'دوباره زانوها را به سینه بکش (پا داخل).',
    ],
    cues: ['پاها در کل حرکت بالای زمین بمانند.', 'موقع باز کردن پاها بازدم کن.'],
    mistakes: ['حرکت سریع و بدون کنترل', 'پایین آمدن پاها و برخورد با دمبل'],
    keys: [
      { t: 0, label: 'پا تو (زانو به سینه)', abs: 1, pose: merge(SEATED, legs(-118, 125, 0)) },
      { t: 0.33, label: 'پا باز', abs: 0.7, pose: merge(SEATED, { root: { rx: -50 } }, legs(-70, 12, 28, -28)) },
      { t: 0.62, label: 'پا بسته', abs: 0.8, pose: merge(SEATED, { root: { rx: -50 } }, legs(-70, 12, 0)) },
      { t: 1, label: 'پا داخل', abs: 1, pose: merge(SEATED, legs(-118, 125, 0)) },
    ],
  },
  {
    id: 'single-leg',
    name: 'تک‌پا دور دمبل',
    en: 'Single-leg pass over dumbbell',
    dose: '۳ ست هر طرف',
    note: 'تعداد تکرار در ویدیو گفته نشده؛ پیشنهاد: ۱۰ تکرار.',
    type: 'reps', target: 10, sets: 3, sides: true,
    repsPerCycle: 1, cycle: 2.6,
    video: [20, 26],
    props: [{ pos: [0.26, 0, 0.62], upright: true }],
    muscles: ['راست شکمی (پایین)', 'مورب‌ها', 'خم‌کننده لگن'],
    steps: [
      'بنشین و عقب برو. دمبل کمی سمت پای کاری است.',
      'پای دیگر خم و آرام است.',
      'پای کاری را از بیرون دمبل بالا بیاور و از رویش به داخل ببر (پا بیرون ← پا تو).',
      'دوباره از روی دمبل به بیرون برگردان (پا باز).',
      'تمام تکرارها را با یک پا انجام بده، بعد پا را عوض کن.',
    ],
    cues: ['لگن را نچرخان.', 'پای کاری تقریباً صاف بماند.'],
    mistakes: ['کمک گرفتن از پای دیگر', 'افتادن پا روی زمین'],
    keys: [
      { t: 0, label: 'پا بیرون دمبل', abs: 0.5, pose: merge(SEATED, { lHip: { x: -55, z: 30 }, lKnee: { x: 18 }, rHip: { x: -58, z: -10 }, rKnee: { x: 80 } }) },
      { t: 0.3, label: 'پا بالا، از روی دمبل', abs: 1, pose: merge(SEATED, { lHip: { x: -105, z: 12 }, lKnee: { x: 45 }, rHip: { x: -58, z: -10 }, rKnee: { x: 80 } }) },
      { t: 0.55, label: 'پا تو (داخل دمبل)', abs: 0.7, pose: merge(SEATED, { lHip: { x: -58, z: -8 }, lKnee: { x: 22 }, rHip: { x: -58, z: -14 }, rKnee: { x: 80 } }) },
      { t: 0.78, label: 'پا بالا، برگشت', abs: 1, pose: merge(SEATED, { lHip: { x: -105, z: 12 }, lKnee: { x: 45 }, rHip: { x: -58, z: -10 }, rKnee: { x: 80 } }) },
      { t: 1, label: 'پا باز (بیرون)', abs: 0.5, pose: merge(SEATED, { lHip: { x: -55, z: 30 }, lKnee: { x: 18 }, rHip: { x: -58, z: -10 }, rKnee: { x: 80 } }) },
    ],
  },
  {
    id: 'v-up',
    name: 'وی‌آپ، دست بین پاها',
    en: 'V-up, reach between legs',
    dose: '۱۰ تکرار',
    type: 'reps', target: 10, sets: 3,
    repsPerCycle: 1, cycle: 2.8,
    video: [26, 34],
    props: [{ pos: [-0.5, 0, 0.55], upright: true }, { pos: [-0.5, 0, 0.75], upright: true }],
    muscles: ['راست شکمی (کامل)', 'خم‌کننده‌های لگن'],
    steps: [
      'دو دمبل را کنار هم بگذار و صاف روی زمین دراز بکش.',
      'دست‌ها را بالای سر ببر.',
      'هم‌زمان پاها و بالاتنه را بالا بیاور (شکل V).',
      'با دو دست بین پاها برس.',
      'آرام و کنترل‌شده برگرد.',
    ],
    cues: ['بالا رفتن: بازدم. پایین آمدن: دم.', 'چانه را کمی پایین نگه دار.'],
    mistakes: ['پرت کردن دست‌ها برای بالا رفتن', 'محکم افتادن روی زمین'],
    keys: [
      { t: 0, label: 'دراز کش، دست‌ها بالای سر', abs: 0.2, pose: merge(LYING, { lShoulder: { x: -168, z: 8 }, rShoulder: { x: -168, z: -8 } }) },
      { t: 0.42, label: 'پا بالا، دست بین پاها', abs: 1, pose: merge(LYING, { spine: { x: 52 }, head: { x: 35 }, lShoulder: { x: -88, z: -3 }, rShoulder: { x: -88, z: 3 }, lHip: { x: -62, z: 9 }, rHip: { x: -62, z: -9 }, lKnee: { x: 18 }, rKnee: { x: 18 }, lAnkle: { x: 10 }, rAnkle: { x: 10 } }) },
      { t: 0.55, label: 'مکث در بالا', abs: 1, pose: merge(LYING, { spine: { x: 54 }, head: { x: 35 }, lShoulder: { x: -90, z: -3 }, rShoulder: { x: -90, z: 3 }, lHip: { x: -64, z: 9 }, rHip: { x: -64, z: -9 }, lKnee: { x: 18 }, rKnee: { x: 18 }, lAnkle: { x: 10 }, rAnkle: { x: 10 } }) },
      { t: 1, label: 'برگشت آرام', abs: 0.2, pose: merge(LYING, { lShoulder: { x: -168, z: 8 }, rShoulder: { x: -168, z: -8 } }) },
    ],
  },
  {
    id: 'cross-touch',
    name: 'دست به پای مخالف، نوبتی',
    en: 'Alternating cross toe touch',
    dose: '۲۰ تکرار هر طرف',
    type: 'reps', target: 40, sets: 3,
    repsPerCycle: 2, cycle: 2.8,
    video: [34, 40],
    props: [],
    muscles: ['مورب‌ها', 'راست شکمی'],
    steps: [
      'دراز بکش؛ دست‌ها باز و بالای سر روی زمین.',
      'یک پا را صاف بالا بیاور.',
      'هم‌زمان با دست مخالف به نوک آن پا برس (بالاتنه می‌چرخد).',
      'برگرد و سمت دیگر را انجام بده (نوبتی).',
    ],
    cues: ['چرخش از کمر باشد، نه فقط از شانه.', 'پای پایین نزدیک زمین بماند.'],
    mistakes: ['خم کردن زیاد زانوی پای بالا', 'کشیدن گردن با سر'],
    keys: [
      { t: 0, label: 'دراز کش، دست‌ها باز', abs: 0.2, pose: merge(LYING, { lShoulder: { x: -172, z: 40 }, rShoulder: { x: -172, z: -40 } }) },
      { t: 0.25, label: 'پای راست بالا، دست چپ به پای راست', abs: 1, pose: merge(LYING, { spine: { x: 50, y: -24, z: -8 }, head: { x: 35 }, lShoulder: { x: -98, z: -30 }, lElbow: { x: -5 }, rShoulder: { x: -165, z: -45 }, rHip: { x: -78, z: -6 }, rKnee: { x: 6 }, lKnee: { x: 15 }, rAnkle: { x: 10 } }) },
      { t: 0.5, label: 'برگشت', abs: 0.2, pose: merge(LYING, { lShoulder: { x: -172, z: 40 }, rShoulder: { x: -172, z: -40 } }) },
      { t: 0.75, label: 'پای چپ بالا، دست راست به پای چپ', abs: 1, mirrorOf: 1 },
      { t: 1, label: 'برگشت', abs: 0.2, pose: merge(LYING, { lShoulder: { x: -172, z: 40 }, rShoulder: { x: -172, z: -40 } }) },
    ],
  },
  {
    id: 'side-tuck',
    name: 'جمع کردن پا به سمت سینه، هر طرف',
    en: 'Seated side tuck',
    dose: '۱۵ تکرار هر طرف',
    type: 'reps', target: 30, sets: 3,
    repsPerCycle: 2, cycle: 3.2,
    video: [40, 48],
    props: [],
    muscles: ['راست شکمی (پایین)', 'مورب‌ها'],
    steps: [
      'بنشین، دست‌ها پشت سر، بالاتنه عقب.',
      'پاها را جفت و تقریباً صاف بالای زمین نگه دار.',
      'تنه ثابت؛ زانوها را به سمت یک طرف سینه بکش.',
      'پاها را صاف کن، بعد به سمت طرف دیگر بکش.',
      'سطح حرفه‌ای: پاها را بالاتر نگه دار.',
    ],
    cues: ['«تنت ثابت باشه، پات بیاد داخل»', 'جمع کردن: بازدم.'],
    mistakes: ['حرکت دادن بالاتنه به جای پاها', 'گذاشتن پا روی زمین'],
    keys: [
      { t: 0, label: 'پاها صاف، بالای زمین', abs: 0.6, pose: merge(SEATED, legs(-58, 12, 0)) },
      { t: 0.25, label: 'زانوها به سمت چپ سینه', abs: 1, pose: merge(SEATED, { spine: { x: 14 } }, legs(-112, 118, 16)) },
      { t: 0.5, label: 'پاها صاف', abs: 0.6, pose: merge(SEATED, legs(-58, 12, 0)) },
      { t: 0.75, label: 'زانوها به سمت راست سینه', abs: 1, pose: merge(SEATED, { spine: { x: 14 } }, legs(-112, 118, -16)) },
      { t: 1, label: 'پاها صاف', abs: 0.6, pose: merge(SEATED, legs(-58, 12, 0)) },
    ],
  },
  {
    id: 'db-v-up',
    name: 'وی‌آپ با دو دمبل',
    en: 'Dumbbell V-up',
    dose: '۱۰ تکرار',
    note: 'برای کسانی که شکم قوی دارند. ساده‌تر: با یک دمبل.',
    type: 'reps', target: 10, sets: 3, held: 'both',
    repsPerCycle: 1, cycle: 3.2,
    video: [48, 62],
    props: [],
    muscles: ['راست شکمی (کامل)', 'خم‌کننده‌های لگن', 'شانه (ثبات)'],
    steps: [
      'دو دمبل را بگیر و دراز بکش.',
      'دمبل‌ها را بالای سر نگه دار، پاها صاف.',
      'پاها را تا حدود عمود بالا بیاور و هم‌زمان بالاتنه را بالا ببر.',
      'دمبل‌ها را به سمت پاها ببر.',
      'آرام برگرد. ساده‌تر: با یک دمبل.',
    ],
    cues: ['دست‌ها صاف بمانند.', 'وزن دمبل را با شکم کنترل کن، نه با تاب دادن.'],
    mistakes: ['دمبل سنگین', 'افتادن سریع پاها'],
    keys: [
      { t: 0, label: 'دراز کش، دمبل بالای سر', abs: 0.3, pose: merge(LYING, { lShoulder: { x: -150, z: 6 }, rShoulder: { x: -150, z: -6 } }) },
      { t: 0.45, label: 'پاها عمود، دمبل به سمت پا', abs: 1, pose: merge(LYING, { spine: { x: 40 }, head: { x: 35 }, lShoulder: { x: -105, z: 4 }, rShoulder: { x: -105, z: -4 }, lHip: { x: -86, z: 5 }, rHip: { x: -86, z: -5 }, lKnee: { x: 10 }, rKnee: { x: 10 }, lAnkle: { x: 5 }, rAnkle: { x: 5 } }) },
      { t: 0.57, label: 'مکث در بالا', abs: 1, pose: merge(LYING, { spine: { x: 42 }, head: { x: 35 }, lShoulder: { x: -102, z: 4 }, rShoulder: { x: -102, z: -4 }, lHip: { x: -88, z: 5 }, rHip: { x: -88, z: -5 }, lKnee: { x: 10 }, rKnee: { x: 10 }, lAnkle: { x: 5 }, rAnkle: { x: 5 } }) },
      { t: 1, label: 'برگشت آرام', abs: 0.3, pose: merge(LYING, { lShoulder: { x: -150, z: 6 }, rShoulder: { x: -150, z: -6 } }) },
    ],
  },
  {
    id: 'cross-crunch',
    name: 'کرانچ دست ضربدری با زانو',
    en: 'Cross-arm crunch with knee raise',
    dose: '۲۰ ثانیه',
    type: 'time', target: 20, sets: 3,
    repsPerCycle: 2, cycle: 2.4,
    video: [62, 65.5],
    props: [{ pos: [0.45, 0, 0.55], upright: true }],
    muscles: ['راست شکمی (بالا)', 'مورب‌ها'],
    steps: [
      'دراز بکش و دست‌ها را ضربدری روی سینه بگذار.',
      'کتف‌ها را از زمین جدا کن (کرانچ).',
      'هم‌زمان یک زانو را به سمت سینه بیاور.',
      'برگرد و با زانوی دیگر تکرار کن.',
      '۲۰ ثانیه بدون توقف.',
    ],
    cues: ['کمر پایین روی زمین بماند.', 'ریتم ثابت داشته باش.'],
    mistakes: ['بالا آوردن با گردن', 'حبس کردن نفس'],
    keys: [
      { t: 0, label: 'دراز کش، دست ضربدری', abs: 0.4, pose: merge(LYING, { spine: { x: 12 }, lShoulder: { x: -60, z: -40 }, rShoulder: { x: -60, z: 40 }, lElbow: { x: -115 }, rElbow: { x: -115 } }) },
      { t: 0.25, label: 'کرانچ + زانوی راست', abs: 1, pose: merge(LYING, { spine: { x: 40 }, head: { x: 35 }, lShoulder: { x: -60, z: -40 }, rShoulder: { x: -60, z: 40 }, lElbow: { x: -115 }, rElbow: { x: -115 }, rHip: { x: -95, z: -4 }, rKnee: { x: 100 } }) },
      { t: 0.5, label: 'برگشت', abs: 0.4, pose: merge(LYING, { spine: { x: 12 }, lShoulder: { x: -60, z: -40 }, rShoulder: { x: -60, z: 40 }, lElbow: { x: -115 }, rElbow: { x: -115 } }) },
      { t: 0.75, label: 'کرانچ + زانوی چپ', abs: 1, mirrorOf: 1 },
      { t: 1, label: 'برگشت', abs: 0.4, pose: merge(LYING, { spine: { x: 12 }, lShoulder: { x: -60, z: -40 }, rShoulder: { x: -60, z: 40 }, lElbow: { x: -115 }, rElbow: { x: -115 } }) },
    ],
  },
  {
    id: 'side-extend',
    name: 'جمع و باز کردن پا کنار دو دمبل',
    en: 'Seated tuck & side extend',
    dose: '۳۰ ثانیه',
    type: 'time', target: 30, sets: 3,
    repsPerCycle: 2, cycle: 3.2,
    video: [65.5, 71],
    props: [{ pos: [0.09, 0, 0.7], upright: true }, { pos: [-0.09, 0, 0.7], upright: true }],
    muscles: ['مورب‌ها', 'راست شکمی (پایین)'],
    steps: [
      'دو دمبل را عمودی کنار هم جلوی خودت بگذار.',
      'بنشین، دست‌ها پشت سر، بالاتنه عقب.',
      'زانوها را بالای دمبل‌ها جمع کن.',
      'پاها را به یک طرف دمبل‌ها صاف کن، دوباره جمع کن.',
      'به طرف دیگر صاف کن. ۳۰ ثانیه ادامه بده.',
    ],
    cues: ['پاها به دمبل نخورند.', 'دست‌ها فقط تکیه‌گاه هستند.'],
    mistakes: ['کم کردن دامنه حرکت', 'نشستن صاف (بدون عقب رفتن)'],
    keys: [
      { t: 0, label: 'زانوها جمع، بالای دمبل', abs: 1, pose: merge(SEATED, { root: { rx: -52 } }, legs(-122, 122, 0)) },
      { t: 0.25, label: 'پاها صاف، سمت راست', abs: 0.7, pose: merge(SEATED, legs(-68, 14, -30)) },
      { t: 0.5, label: 'زانوها جمع', abs: 1, pose: merge(SEATED, { root: { rx: -52 } }, legs(-122, 122, 0)) },
      { t: 0.75, label: 'پاها صاف، سمت چپ', abs: 0.7, pose: merge(SEATED, legs(-68, 14, 30)) },
      { t: 1, label: 'زانوها جمع', abs: 1, pose: merge(SEATED, { root: { rx: -52 } }, legs(-122, 122, 0)) },
    ],
  },
];
