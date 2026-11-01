# Shamshir user guide

Shamshir is a free video editor that your AI assistant uses for you. You say what you want in
normal words. The assistant looks at your videos, measures the music and the style of a
reference video, edits, and checks the result. Everything runs on your own computer.

## 1. Install (one time)

1. Install Python 3.10 or newer and ffmpeg.
2. In the `shamshir` folder, run:
   `pip install -e ".[captions]"`
3. Connect Shamshir to Claude Code:
   `claude mcp add --scope user shamshir -- shamshir`
4. Recommended: install the editing skill, so the assistant knows the best way to work:
   `cp -r skill/shamshir-edit ~/.claude/skills/`
5. Close Claude Code and open it again.

Optional parts:
- Google Flow (AI video clips with your own Google account): `pip install -e ".[flow]"`
- Kinetograph (After-Effects-style titles and graphics): Node.js, then
  `npx skills add 0xS4N4TG/kinetograph` and `npm i -D kinetograph` in your project folder.

## 2. Prepare your files

- Put your clips, music and reference video in one folder.
- Use simple file names, for example `clip1.mp4`, `song.mp3`, `ref.mp4`.
- Sharp clips with a lot of movement give the best edits. 3 to 10 clips are enough for a
  15-second edit.

## 3. What to say (examples)

- "Make a 15-second vertical hype edit from the clips in `~/videos/trip` on `song.mp3`.
  Start with the title «Trip»."
- "Analyze `ref.mp4` and make an edit of my clips with the same rhythm and feeling. Then
  compare it with the reference."
- "Remove the pauses from `talk.mp4`, add word-by-word captions, and make it vertical."
- "Put `logo.png` in the top-right corner and keep the file under 50 MB."
- "Make clip 2 slow motion in the middle (speed ramp) and stabilize it."
- "Add 🔥 next to the title."
- "Make an animated intro title with Kinetograph and put it on the edit."
- "Make an 8-second clip of a cat on the moon with Google Flow and put it in the edit."

## 4. Tips for the best result

- **Give a reference.** A video whose style you like is the best direction.
- **Say the length and format.** For example "15 seconds, 9:16 for Instagram".
- **Ask for a preview first.** "Show me a preview before the final render."
- **Change in small steps.** "Faster cuts", "fewer flashes", "slow motion at second 8".
  Small changes render fast because unchanged clips are reused.
- **Ask for a check.** "Check the result and compare it with the reference."

## 5. Ready styles

| Style | Feeling |
|---|---|
| hype | a cut on every beat, zoom punches, flashes, shake |
| phonk | high-contrast black and white, much shake and flash |
| cinematic | slow cuts, fades, slow zoom, letterbox, film colours |
| smooth | calm and warm |
| glitch | glitches and cyber colours |

## 6. What Shamshir can do

- See your footage frame by frame and measure cuts, camera moves, shake, flashes, music beats.
- Copy the edit style of a reference onto your own clips, cut on the beat.
- Trim, speed, speed ramps (with sound), reverse, stabilize, vertical crop that follows motion.
- 11 colour looks and your own `.cube` LUTs.
- Zoom punch, slow zoom, shake, flash, strobe, RGB split, glitch, blur, motion blur, grain,
  vignette, letterbox, transitions.
- Text in 7 styles and 8 animations, with correct Persian and Arabic. Colour emoji.
- Captions from speech (word-by-word highlight). Removal of pauses (jump cuts).
- Logo and picture-in-picture overlays. Music, ducking, sound effects, loudness for social media.
- Quality check and side-by-side comparison with the reference.
- Optional: AI clips from Google Flow; motion graphics from Kinetograph.

## 7. Google Flow (optional)

1. Ask the assistant: "Run flow_setup". Start Chrome with the command it gives you.
2. In that Chrome window, log in to your Google account and open a Flow project.
3. Ask for a clip. First only the prompt is typed and you see a screenshot (no credits are
   spent). The clip is made only after you agree.
- Your own Flow credits are used. If Flow asks you to approve credits, you approve it in the
  browser yourself; Shamshir never does it for you.
- Automating the Flow website may be against Google's terms. Use it at your own risk. If Google
  changes the website, this part can stop working.

## 8. Limits

- Shamshir does not make new scenes by itself; it edits your footage (and Google Flow clips).
- Complex After Effects work (masks, tracked 3D text, particles) is not copied exactly. Shamshir
  gets close with rhythm, flashes, shake, zooms, colour, speed and text; Kinetograph adds
  designed motion graphics.
- Captions need the `captions` extra (faster-whisper).
