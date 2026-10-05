# Contributing

Contributions are welcome, code or not.

## The terms, in one sentence

If you send code, you accept [CLA.md](CLA.md): you keep your copyright, and you let me use your contribution under any license, including a paid commercial one, without payment to you. You're credited in `CONTRIBUTORS.md` and in the release notes. The pull request template has a box to tick for this, and it's required.

## What helps most

A test report. Tell me the OS and its version, the Claude Desktop version, the Python version, and what worked or didn't. Use the "Test report" issue template. For macOS, [TESTS_MACOS.md](TESTS_MACOS.md) lists what to check.

Next come bug reports, with the output of `--debug` after you've blanked the conversation titles and your user name, and small pull requests that fix one thing.

For a bigger change, open an issue first so we agree before you spend time on it.

## Rules for the code

- It stays a single file, `context_hud.py`, using only the Python standard library, and it works on Python 3.8.
- No network code. A pull request that adds network access will be declined, because "this program talks to nobody" is something the README says.
- Windows behavior doesn't change by accident. Code that depends on the platform goes behind `IS_WIN` or `IS_MAC`.
- Text shown to the user goes in `STRINGS`, in English and in French.
- No personal data in the repository: no conversation titles, no paths containing a user name, no `context_hud_state.json`, no log.

## Before you send

Check that `python -m py_compile context_hud.py` passes, and run `python context_hud.py --once` on your machine. Say in the pull request what you tested and on which system.
