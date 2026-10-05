# Cowork Context HUD

**See your Cowork context fill up before it compacts.**

[Français](README.fr.md)

![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue)
![Source-available](https://img.shields.io/badge/source-available-blue)
![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-lightgrey)
![Windows: tested](https://img.shields.io/badge/Windows-tested-brightgreen)
![macOS: experimental, not tested](https://img.shields.io/badge/macOS-experimental%2C%20not%20tested-orange)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)

![Cowork Context HUD following a conversation as it fills up, crossing the red compaction mark, then flashing its border](assets/demo.gif)

*Captured on Windows, with made-up demo data and invented conversation titles.*

Auto-compaction has cut me off in the middle of a task more times than I can count. As far as I can tell, Cowork doesn't show how full a conversation is, so you only notice once it has already happened. I wanted a number I could glance at, so I wrote this: a small window that stays on top and shows the context of your active Cowork conversation, with a red mark where compaction has kicked in for you before, and an alert when you get close to it.

It's one Python file, with no dependency outside the standard library, and it reads the local cache of Claude Desktop without ever writing to it. Anthropic's request for a built-in indicator, [issue #37568](https://github.com/anthropics/claude-code/issues/37568), was closed as not planned by the inactivity bot and locked.

## Install

You need Python 3.8 or newer with tkinter. The installer from python.org for Windows includes it.

**Windows** (the platform I use and tested)

1. Get the code: `git clone https://github.com/Kayhalan/cowork-context-hud.git`, then `cd cowork-context-hud`. You can also download `context_hud.py` alone, it's the whole program.
2. Open some Cowork conversations in Claude Desktop. The HUD can only show a conversation after Claude Desktop has cached it.
3. Start it without a console window. In PowerShell:

        Start-Process pythonw.exe -ArgumentList "context_hud.py" -WindowStyle Hidden

   In cmd:

        start /b pythonw "context_hud.py"

   To see messages in the terminal instead, run `python context_hud.py`.
4. To stop it, right-click on it and choose Quit.

**macOS** (experimental, nobody has run it on a Mac yet)

1. Check that tkinter is there: `python3 -c "import tkinter; print(tkinter.TkVersion)"`.
2. Clone the repository as above and run `python3 context_hud.py` from its folder.
3. If it works, or if it doesn't, please tell me. [TESTS_MACOS.md](TESTS_MACOS.md) lists what to check and what to send back. If the borderless window misbehaves, try `python3 context_hud.py --framed`.

Linux isn't supported. If you want to try it anyway, `--data-dir` lets you point it at a Claude Desktop data folder.

## Use

| Action | Windows | macOS |
|---|---|---|
| Move | Drag | Drag |
| Show or hide all conversations | Double-click | Double-click |
| Pin a conversation (list shown) | Click on its row | Click on its row |
| Size | Ctrl + wheel | Ctrl + wheel |
| Opacity | Shift + wheel | Shift + wheel |
| Width | Alt + wheel | Option + wheel |
| Menu | Right-click | Right-click or Ctrl + click |

The menu also has the alert level (60, 70, 80 or 90 % of the compaction threshold), the alert sound, always on top, the language (English or French) and a reset for the look. Settings are remembered.

By default the HUD follows the conversation that is running, or else the one used most recently. Pin one to keep it on screen.

Options for the command line:

| Option | What it does |
|---|---|
| `--once` | Print a table in the terminal and exit |
| `--debug` | The table, plus which files were read and how long each took |
| `--lang en` or `--lang fr` | Interface language for this run. The menu choice is what's remembered |
| `--data-dir PATH` | Read this Claude Desktop data folder instead of looking for it |
| `--warn N` | Alert at N % of the compaction threshold (default 80, or the last value you chose) |
| `--compact-at TOKENS` | Set the compaction threshold by hand |
| `--window TOKENS` | Force the window size |
| `--interval SECONDS`, `--days N`, `--limit N` | Refresh rate, how old a conversation can be, how many are listed |
| `--alpha`, `--zoom`, `--width` | Opacity, size and width at start |
| `--framed` | Normal window with a title bar |
| `--version` | Print the version |

## Privacy

I'd ask the same question, so here is the answer first.

Claude Desktop's local storage contains the text of your conversations. This program opens those files and decodes them in memory, so yes, it goes through that content. What it keeps is the token counts, the model, the context window size, the compaction events, the conversation titles and ids, some timestamps and the quota gauges. It doesn't keep the messages. Nothing from those files is written to disk, copied or sent anywhere.

There is no network code. You don't have to take my word for it: the program is a single file, and its imports are at the top. They are the Python standard library (`argparse`, `json`, `os`, `pathlib`, `re`, `struct`, `sys`, `threading`, `time`, `traceback`, `tkinter`) and, depending on the platform, `ctypes`, `winsound`, `msvcrt` or `fcntl`. No `socket`, no `urllib`, no `http`.

It only reads Claude Desktop's folder. Everything it writes is next to the script: `context_hud_state.json` (window position, settings, language, the compaction thresholds and window sizes it learned, the id of the pinned conversation), `context_hud.lock` (to prevent a second HUD), and `context_hud.log`, which only gets written when an error happens. All of these are in `.gitignore`.

When you post output somewhere, remember that `--once`, `--debug` and the log can show conversation titles and folder paths, which include your user name. Blank them before pasting anything into an issue.

One more detail: to read the quota, the program decodes every entry of Claude Desktop's Local Storage database and keeps only the quota entries. I don't know what else is in there, and the rest is dropped from memory right away.

## How it works

Claude Desktop keeps a local cache of the Cowork interface (the IndexedDB and Local Storage of its Electron app). When you open a conversation or when a turn ends, the app writes the conversation there. The HUD finds those files and decodes them with its own small decoders for Snappy, the V8 serialization format and LevelDB, all in the same file. For each conversation it takes the last turn of the main thread and adds up input, cache creation, cache read and output tokens. Turns from sub-agents are ignored.

That total is compared to the model's context window. The window comes from the `contextWindow` value that Cowork reports, and when it isn't there yet, from a small table in the code (200,000 for Haiku, 1,000,000 for the recent Sonnet and Opus models, 200,000 for anything unknown).

The red mark is where compaction starts. The cache records every compaction with the number of tokens it happened at. The HUD keeps the lowest automatic one for each model, saves it in the state file, and draws the mark there. In my own data it fired at about 382,000 tokens on Sonnet 5.5, with a window of 1,000,000, so around 38 %. Yours may differ, and it may change with Claude Desktop updates. If a conversation of the same model goes more than 2 % past the saved threshold without compacting, the HUD stops trusting it.

The alert is measured from that mark. At 80 % of it by default, the border flashes red for a few seconds and you hear a beep (the Windows exclamation sound on Windows, the Tk bell elsewhere). It fires once per conversation and re-arms when the conversation falls 10 points below the alert level. If a conversation is already past the level when you start the HUD, it fires right away.

The quota gauges (the 5 hour session and the week) use the most recent of three local sources, and the HUD shows how old each reading is.

## Limits

- The cache isn't documented by Anthropic as a data source. It works today on my machine, and a Claude Desktop update can break it without warning. If that happens, `--debug` shows what was read.
- Claude Desktop writes the cache when it loads a conversation, so the numbers can be a bit behind. The HUD shows the age of the data. A conversation you never opened has no data yet, and the HUD says so.
- There is no red mark until the HUD has seen one automatic compaction of that model on your machine. Until then the alert counts from the whole window. `--compact-at` sets it by hand.
- A model that isn't in the table gets a 200,000 token window until Cowork reports the real one, so the percentage can be wrong for a while. The table needs maintenance.
- It reads the standard Claude Desktop folder, including the Microsoft Store package on Windows. The separate folder of the third-party platform mode (`Claude-3p`) isn't read.
- Only Cowork conversations are covered.
- Tested by me on Windows, with Claude Desktop 2.19675.0 and Python 3.12. Nobody has tested macOS. I don't know yet if the cache has the same layout there.

## Alternatives

I'm not the first to want this. Here are other tools I found while checking. I don't claim the list is complete or up to date, and they read different sources than this one: [cowork-context-meter](https://github.com/a-data3/cowork-context-meter) by a-data3, [claude-context-meter](https://github.com/nowoandi/claude-context-meter) by nowoandi, [Context-Canary](https://github.com/amarisaster/Context-Canary) by amarisaster, and [usage-monitor-for-claude](https://github.com/jens-duttke/usage-monitor-for-claude) by jens-duttke, which only covers quotas. Try them and keep what fits.

## Disclaimer

This is a community project. It isn't official, and it isn't affiliated with, endorsed by or supported by Anthropic. Claude and Cowork are Anthropic's names. I only describe what the program does: it reads files on your own computer and talks to nobody. If Anthropic's terms matter to you, read them yourself.

## License

The code is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE). It isn't open source in the OSI sense. Noncommercial use is free: personal use, and use by charities, schools, public research bodies, public safety or health organizations, environmental organizations and government institutions, as the license text lists them.

If you want to use it commercially, you need a commercial license from me. Open an issue titled "Commercial license" and say you'd like to talk. Don't post personal contact details there, I'll tell you how to continue. If you're not sure that your use counts as noncommercial, ask before relying on my reading of it. I'm not a lawyer, and the license text is what counts.

## Contributing

Code contributions are welcome, under the terms of [CLA.md](CLA.md), summed up in [CONTRIBUTING.md](CONTRIBUTING.md). The most useful thing right now is a test report: the OS version, the Claude Desktop version, and what worked. For macOS, [TESTS_MACOS.md](TESTS_MACOS.md) is the list.

## About

I'm Kayhalan, a full-stack developer based in France, and I wrote this. The macOS port, the English texts and the files around the code were prepared with Claude's help, and I went through them before publishing.
