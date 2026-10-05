# macOS test plan

The macOS part of `context_hud.py` is experimental. It was written from the documentation of Tk and Python, and nobody has run it on a Mac yet. Windows is the only platform where the HUD has been used for real.

If you have a Mac and a few minutes, this page lists what to check and what to send back. You don't need to read the code. Skip any step you can't do, a partial report is still useful.

## What you need

- A Mac with Claude Desktop, signed in, with at least one Cowork conversation.
- Python 3 with tkinter. Check with: `python3 -c "import tkinter; print(tkinter.TkVersion)"`. The Python documentation says Tk 8.5.12 is the minimum, and the installer from python.org ships 8.6. Tell me which number you get.
- `context_hud.py` from this repository. Nothing to install.

## Before you paste anything

`--debug` and the log file contain your macOS user name in folder paths, and `--debug` also lists the titles of your Cowork conversations. Replace both with `xxx` before posting. The HUD never sends anything anywhere, but a public issue is public.

## Steps

Run every command from the folder that holds `context_hud.py`.

**1. Environment.** Run `sw_vers`, `python3 --version`, and the Tk command above. Note the Claude Desktop version (Claude menu, About).

**2. Data folder.** Run:

    ls ~/Library/Application\ Support/Claude/
    ls ~/Library/Application\ Support/Claude/IndexedDB/
    ls ~/Library/Application\ Support/Claude/Local\ Storage/leveldb | head

Expected: a folder named `https_claude.ai_0.indexeddb.blob` inside `IndexedDB`, and some `.ldb` or `.log` files in `leveldb`. This is the main open question of the port: the HUD assumes the same layout as on Windows. Paste the three listings (names only, not file contents). If the folder is missing, say so, that alone is a useful result.

**3. Version and diagnostics.**

    python3 context_hud.py --version
    python3 context_hud.py --debug

Expected: `context_hud.py 0.1.0`, then a table, a `Files decoded:` list with a time in ms for each file (or `ignored (...)` for files it could not read), and the `Folders:` list showing the Claude folder. Paste the output with titles and user name blanked.

**4. Table with real conversations.** Open a Cowork conversation in Claude Desktop, let it finish one answer, then run `python3 context_hud.py --once`. Expected: one row per recent conversation, with the number of tokens, the model, and the age of the data. Paste it, blanked.

**5. The window.** Run `python3 context_hud.py` and leave it open. Check each point and answer yes, no, or what you saw:

- Does a small dark window appear, without a title bar?
- Does it stay above other windows, including Claude Desktop?
- Can you drag it with the mouse?
- Does a Python icon appear in the Dock, and does it steal focus from the app you were using?
- Quit it from the menu (step 6), run it again. Does it come back at the same place?
- Double-click on it: does the list of conversations open and close?
- With the list open, click on a row: does the row get pinned (the footer says "pinned")?

**6. Menu.** Open the menu with a two-finger click, then with Ctrl + click. The code binds both, plus Button-2. Does the menu open each time? Does Ctrl + click also pin a row when you do it on one?

**7. Mouse wheel.** Over the HUD: Ctrl + wheel changes the size, Shift + wheel the opacity, Option + wheel the width. Say which of the three work. Shift + wheel is the one I trust least, macOS may turn it into a horizontal scroll.

**8. Opacity and always on top.** In the menu, change the opacity to 50 %, then untick "Always on top". Does the window become see-through, and does it go behind other windows?

**9. Alert.** Stop the HUD and start it with a low alert level so that any conversation triggers it: `python3 context_hud.py --warn 5`. Expected: the border flashes red for about 4 seconds and the system beep plays (the menu entry "Alert sound" must be ticked). Say whether you heard the beep and saw the flash. If the sound is missing, the flash is still the signal that counts.

**10. Second instance.** With the HUD running, run `python3 context_hud.py` again in another terminal. Expected: it exits at once and prints `A HUD is already running.`

**11. Fallback window.** Only if step 5 went wrong. Run `python3 context_hud.py --framed`. This uses a normal window with a title bar. Does it work better?

**12. Reset.** `context_hud_state.json` is created next to the script and holds your settings and position. Delete it to start from scratch.

## What to send back

Open an issue titled "macOS test report" and paste: the output of steps 1 to 4 (blanked), the answers of steps 5 to 11 as a short list, and a screenshot of the HUD if you can (hide the conversation titles first). Any error, even a partial one, helps more than silence.

## What this does not cover

Intel versus Apple silicon, multiple screens, Spaces and full-screen apps, and the permission prompts macOS may show when a program reads another app's folder. I don't know yet whether macOS asks for anything there, so if a prompt appears, please describe it.
