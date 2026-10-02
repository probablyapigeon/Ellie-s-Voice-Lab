# Bird Voice Lab

Published as **Ellie's Voice Lab** on GitHub.

[Download the runnable Windows package](https://github.com/probablyapigeon/Ellie-s-Voice-Lab/releases/download/v0.1.0/BirdVoiceLab-0.1.0-Windows.zip) · [Release and source download](https://github.com/probablyapigeon/Ellie-s-Voice-Lab/releases/tag/v0.1.0) · [Welcome guide for Jen](docs/FOR_JEN.md)

A local research notebook for bird communication studies, with transparent comparison controls and a separate learning-agent sandbox. Built to share with Jen, inspired by the computational controls described in the Parrot Kindergarten documentary. This is an independent tool, not a reconstruction of Pigeon42.

## Run

Windows: extract the entire Windows ZIP, then double-click `BirdVoiceLab.exe` inside its folder. A local browser window opens. Use **Quit** in the sidebar when finished. No Python installation, account, internet connection, or cloud service is needed.

Source (Python 3.11 or later): run `python app.py`. The application uses only the Python standard library. On Windows you can also double-click `start.cmd` if Python is installed.

## Research workflow

1. Write the question, available choices, corroboration criterion and trial limit. The saved protocol is immutable.
2. Before presenting a trial, record the actual display order, brightness estimates, prompt and context weights. Commit the trial to store all six predictions before observing a response.
3. Record selection, latency, initiative, corroboration and notes. Record withdrawal, distress and no response explicitly. Withdrawal/distress ends a study; two consecutive no-response trials also end it.
4. Export JSON for full records, CSV for a spreadsheet, and a separate integrity receipt. Keep the receipt independently of the JSON.

Controls compare uniform chance, first-position bias, brightness, prior choice frequency, literal prompt echo and researcher-rated context. Scores are descriptive Brier scores and log loss, not significance tests or certificates of intention. Pending predictions are hidden in the observation screen; completed trials and exports reveal them. This is not a double-blind study system. Context ratings and corroboration are supplied by people and can carry observer bias.

Records cannot be edited in this version. Check entries before saving; explain errors in an external annotation alongside the exported evidence. An unanswered or uncertain corroboration judgment stays unknown rather than being counted as failure.

## Agent sandbox

Compare a learning policy, the same policy with learning disabled, and uniform chance under a seeded reward reversal and fatigue/rest rule. Inspect every state transition and export the simulation. Synthetic results remain separate from bird observations. These simple policies explore mechanisms; they do not establish animal cognition.

## Data and privacy

The server binds only to `127.0.0.1`, requires a per-launch browser session, and does not upload records. Windows records live in `%LOCALAPPDATA%\BirdVoiceLab\lab.sqlite`; macOS uses `~/Library/Application Support/BirdVoiceLab`; Linux uses the XDG data directory. The field guide displays the actual location. Back up this folder while the app is closed. Media references are text only: audio/video files are not copied or transcribed by this app.

Use `python app.py --data-dir YOUR_FOLDER` to keep a separate notebook. Verify an evidence export with `python app.py --verify evidence.json` (or the executable with the same arguments). Hash chaining detects modification/truncation relative to a preserved receipt; it cannot authenticate the observer or prevent rewriting both export and receipt.

## Development

Run `python -m unittest discover -s tests -v`. Browser checks additionally require Playwright and Chromium: `python tests/browser_check.py`. Build Windows on Windows with `python -m pip install pyinstaller`, then `python -m PyInstaller --noconfirm --onedir --name BirdVoiceLab --add-data "web;web" app.py`. Preserve the complete output folder when distributing it.

Version 0.1.0. MIT license. No original bird observations or documentary media are distributed.

## Research context

The [Open University report on the 2024 research](https://www.open.ac.uk/blogs/news/science-mct/new-study-provides-evidence-that-parrots-can-communicate-needs-and-emotions-with-humans/) and the [ACI Lab project](https://www.animalcomputerinteractionlab.org/parrot-human-communication-project) describe published evidence of functional and intentional parrot communication. This notebook supports further documented observations and comparisons; those findings should be assessed through their original research methods and publications.
