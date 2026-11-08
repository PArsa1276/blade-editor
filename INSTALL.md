# Blade Editor: installation (step by step)

> **Beta:** Blade Editor may still have bugs. If something goes wrong, please report it in
> [Issues](https://github.com/PArsa1276/blade-editor/issues/new/choose) with the exact error text.
>
> **Short way (needs Node.js):** quit the Claude app and run `npx github:PArsa1276/blade-editor`
> in a terminal. It does all the steps below. Use this guide if you want to go step by step.

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

### Step 2: Get Claude

You can use Claude in one of two ways. Choose **A** if you are not sure.

**A. The Claude app (easiest).** Download it from https://claude.ai/download, install it,
open it and log in with your Claude account. You do not need to install anything else for
Claude. (Blade Editor works in the app's **Code** tab and also in normal chats.)

**B. Claude Code in the terminal.** Copy this command into the terminal and press `Enter`:
- **Windows**: `irm https://claude.ai/install.ps1 | iex`
- **Mac / Linux**: `curl -fsSL https://claude.ai/install.sh | bash`

Then close the terminal, open it again, type `claude`, press `Enter` and log in.

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
it to the Claude app and to Claude Code. **Before you start, quit the Claude app completely**
(Windows: right-click the Claude icon near the clock and click **Quit**; Mac: `Cmd+Q`).
You still use the terminal for this one step only.

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

Open the Claude app again (or type `claude` in the terminal if you chose B in step 2).
Start a new chat or a new **Code** session and write:
```
Do you have the blade-editor tools? Call start_here.
```

You will see: Claude says it has the Blade Editor tools and asks if you want this guide.
(Terminal users can also type `/mcp`: the list shows **blade-editor** and **connected**.)

Optional, for Google Flow clips: in Chrome open `chrome://extensions`, turn on **Developer mode**,
click **Load unpacked** and choose the folder `.blade-editor/chrome-extension` in your home folder
(Windows: `C:\Users\<you>\.blade-editor\chrome-extension`). You do this only once.

Optional, NVIDIA graphics card for fast captions: when the installer finds an NVIDIA card, it first looks
for the CUDA 12 libraries that other programs already have (PyTorch, ComfyUI, CUDA Toolkit, cuDNN, Anaconda)
and uses them; only when none are found does it download them (about 1 GB). If Blade says "GPU failed" or "cublas64_12.dll is not found", run this in
the terminal (Windows) and then open Claude again:
```
%USERPROFILE%\.blade-editor\venv\Scripts\python.exe -m pip install "nvidia-cublas-cu12" "nvidia-cudnn-cu12>=9,<10"
```
(In PowerShell, write `$HOME` instead of `%USERPROFILE%`.) The graphics driver must also support CUDA 12.
Without this, captions are made on the CPU: correct, but slower.

Installation is complete. You never need to do Part 1 again.
