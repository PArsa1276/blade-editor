# Blade Editor: step-by-step guide for beginners

Read this guide from top to bottom and do each step in order. You do not need to know anything
about computers or video editing. After each step, the guide tells you what you will see. If
you see something different, go to "Problems and solutions" at the end.

---

## What is Blade Editor?

Blade Editor is a free video editor. You do not edit by hand. You write what you want, for example
"make a 15-second edit of my clips on this song", and an AI assistant (Claude) makes the video
for you on your own computer.

## What you need

- A computer with Windows 10/11 or macOS (Linux also works).
- An internet connection (only for the installation).
- A Claude account with a paid plan (Pro or Max) from https://claude.ai.
- About 30 minutes for the first installation. You do it only one time.

## Words in this guide

- **Terminal**: a window where you type commands. On Windows it is called **PowerShell**.
- **Command**: a line of text that you copy, paste into the terminal and then press **Enter**.
- **Folder**: a place on your computer that holds files (for example "Desktop" or "Documents").

How to copy and paste a command: select the command in this guide, press `Ctrl+C`
(Mac: `Cmd+C`), click in the terminal, press `Ctrl+V` (Mac: `Cmd+V`), then press `Enter`.

---

## Part 1: Installation (one time only)

### Step 1: Open the terminal

- **Windows**: press the `Windows` key, type `PowerShell`, and click **Windows PowerShell**.
- **Mac**: press `Cmd+Space`, type `Terminal`, and press `Enter`.

You will see: a window with text and a blinking cursor.

### Step 2: Install Claude Code

Copy this command into the terminal and press `Enter`.

- **Windows**:
  ```
  irm https://claude.ai/install.ps1 | iex
  ```
- **Mac / Linux**:
  ```
  curl -fsSL https://claude.ai/install.sh | bash
  ```

Wait until it stops. Then **close the terminal and open it again** (step 1).

Now type this command and press `Enter`:
```
claude
```
The first time, Claude Code asks you to log in. Follow the text on the screen: a browser
page opens, you log in with your Claude account, and you come back to the terminal.

You will see: a box with "Welcome to Claude Code". Type `/exit` and press `Enter` to close it.

### Step 3: Download Blade Editor

1. Open this link in your browser:
   https://github.com/PArsa1276/blade-editor/archive/refs/heads/main.zip
   A ZIP file named `blade-editor-main.zip` downloads.
2. Open your **Downloads** folder. Right-click the ZIP file and click **Extract All**
   (Mac: double-click the ZIP file).
3. Open the extracted folders until you see the files `install.ps1` and `install.sh`. Go one
   level back: the folder that holds these files is named `blade-editor-main`. Rename it to
   `blade-editor` (right-click, **Rename**) and move it to your **Documents** folder.

You will see: the folder `Documents/blade-editor` with files like `install.ps1`, `install.sh` and
`README.md` in it.

### Step 4: Run the Blade Editor installer

The installer installs everything Blade Editor needs (Python, ffmpeg, Blade Editor itself) and connects
it to Claude Code.

- **Windows**: open PowerShell (step 1) and run these two commands, one after the other:
  ```
  cd $HOME\Documents\blade-editor
  ```
  ```
  powershell -ExecutionPolicy Bypass -File install.ps1
  ```
- **Mac / Linux**: open Terminal (step 1) and run these two commands, one after the other:
  ```
  cd ~/Documents/blade-editor
  ```
  ```
  bash install.sh
  ```

The installer can take 5 to 15 minutes. It can ask for your computer password (Mac/Linux) or
show a "Do you allow this app to make changes?" window (Windows). Accept.

You will see at the end: **Blade Editor is ready.**

If the installer says "Close this window, open a new PowerShell and run this file again",
do that: close PowerShell, open it again and repeat this step.

### Step 5: Check that Blade Editor works

In the terminal, type `claude` and press `Enter`. Then type:
```
/mcp
```
and press `Enter`.

You will see: a list with **blade-editor** and the word **connected**. Press `Esc`.

Installation is complete. You never need to do Part 1 again.

---

## Part 2: Your first edit

### Step 6: Put your files in one folder

1. On your **Desktop**, make a new folder named `my-edit`
   (right-click on the Desktop, then **New**, then **Folder**).
2. Copy into this folder:
   - your video clips (3 to 10 clips is good),
   - one music file (for example `song.mp3`),
   - optional: a video whose editing style you like (name it `ref.mp4`).

Tip: short, sharp clips with a lot of movement give the best result.

### Step 7: Open Claude Code in that folder

- **Windows**: open the `my-edit` folder. Click on the address bar at the top of the window
  (where the folder path is), type `powershell` and press `Enter`. A PowerShell window opens
  in this folder. Type `claude` and press `Enter`.
- **Mac**: open Terminal, type `cd ` (with a space after it), drag the `my-edit` folder from
  Finder into the Terminal window, and press `Enter`. Then type `claude` and press `Enter`.

### Step 8: Say what you want

The first time, Claude asks if you want this guide. Answer as you like.

Then type your request in normal words and press `Enter`. You can copy one of these:

```
Make a 15-second vertical edit for Instagram from the clips in this folder, on the music file,
in hype style. Put the title "My Trip" at the start. Show me a preview first.
```

```
Analyze ref.mp4 and make an edit of my clips with the same rhythm and feeling.
Then compare it with ref.mp4.
```

You can write in any language.

### Step 9: Allow the actions

Claude asks for permission before it uses a tool, for example:
"Do you want to allow blade-editor - auto_edit?"
Choose **Yes** (or **Yes, and don't ask again** for Blade Editor tools).

### Step 10: Watch the result

When the edit is ready, Claude tells you the file name, for example `edit.mp4`. The file is in
the `my-edit` folder. Double-click it to watch it.

### Step 11: Change it until you like it

Just say what to change, for example:

```
Make the cuts faster.
```
```
Use fewer flashes and add slow motion at second 8.
```
```
Change the title color to yellow and add 🔥 next to it.
```
```
Put logo.png in the top-right corner.
```

When you are happy, say:
```
Make the final version and check its quality.
```

---

## Part 3: More things you can ask for

| You want | Write this |
|---|---|
| Captions for a talking video | `Add word-by-word captions to talk.mp4` |
| Remove the pauses in a talk | `Remove the silent pauses from talk.mp4` |
| Vertical video from a wide video | `Make video.mp4 vertical (9:16) and keep the person in frame` |
| Steady a shaky clip | `Stabilize clip2.mp4` |
| Slow motion in one moment | `Add a speed ramp: slow motion at second 3 of clip1.mp4` |
| Same style as a video you like | `Copy the editing style of ref.mp4 onto my clips` |
| Smaller file | `Keep the file under 50 MB` |
| Different look | `Use a cinematic style` (or: `phonk`, `smooth`, `glitch`) |

Styles: **hype** (a cut on every beat, punches, flashes), **phonk** (black-and-white, much
shake), **cinematic** (slow, film look, black bars), **smooth** (calm, warm), **glitch**
(digital glitches).

---

## Part 4: Optional extras

### AI video clips with Google Flow

This makes new clips with Google's AI (Veo) and your own Google account. It uses your Flow
credits.

1. In the Blade Editor folder terminal run: `~/.blade-editor/venv/bin/python -m pip install playwright`
   (Windows: `$HOME\.blade-editor\venv\Scripts\python.exe -m pip install playwright`).
2. In Claude Code, write: `Run flow_setup`. Claude gives you one command. Run it in a new
   terminal: a separate Chrome window opens.
3. In that Chrome window, log in to Google and open a project at https://labs.google/fx/tools/flow
4. Ask Claude: `Make a clip of a cat on the moon with Google Flow and put it in the edit.`
   First you see a picture of the typed prompt; nothing is spent. Say "yes" to make it.
- If Flow asks you to approve credits, click approve in the Chrome window yourself.
- Automating the Flow website may be against Google's terms. Use it at your own risk.

### Animated titles (Kinetograph)

1. Install Node.js from https://nodejs.org (the "LTS" button).
2. In the terminal run: `npx skills add 0xS4N4TG/kinetograph`
3. In your `my-edit` folder run: `npm i -D kinetograph`
4. Ask Claude: `Make an animated intro title with Kinetograph and put it on the edit.`
A graphics card makes this fast; without one it works but is slower.

---

## Problems and solutions

| You see | Do this |
|---|---|
| `claude` is not recognized / command not found | Close the terminal, open it again, and try again. If it still fails, repeat step 2. |
| The installer says Python or ffmpeg is missing | Close the terminal, open a new one, and run step 4 again. |
| Windows says "running scripts is disabled" | Use exactly the command in step 4 (`powershell -ExecutionPolicy Bypass -File install.ps1`). |
| `/mcp` does not show blade-editor | Run step 4 again, then close and open Claude Code. |
| "File not found" | The file must be in the folder where you started `claude` (step 7). Check the file name. |
| The video is very slow to make | Ask for "a preview first" and a shorter length. Long 4K clips are slow. |
| Persian/Arabic letters look wrong | Tell Claude: "The text looks wrong, please check it with view_frames". |
| Anything else | Copy the error text and paste it to Claude: "I see this error, please fix it." |

## Limits

- Blade Editor edits your own clips. It makes new scenes only with Google Flow (optional).
- Very complex After Effects work (masks, 3D tracked text, particles) is not copied exactly.
  Blade Editor gets close with rhythm, flashes, shake, zooms, colour, speed and text.
- Do not delete or move the `Documents/blade-editor` folder until the installation is done. After
  the installation you can delete it; Blade Editor stays installed in `~/.blade-editor`.
