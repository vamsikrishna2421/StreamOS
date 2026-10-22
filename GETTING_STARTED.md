# Watch on your laptop — the simple version

You do not need to understand any of the code. You need two things: this
repository's URL, and the prompt below.

## Step 1 — open Claude Code on your laptop
On your MacBook or Windows laptop, start a Claude Code session in a new,
empty folder.

## Step 2 — paste this prompt
Copy it exactly. Replace the folder in the last line **only if** you want to
watch your own movie files; otherwise delete that line.

```
Clone the GitHub repo https://github.com/vamsikrishna2421/StreamOS
(branch claude/affectionate-babbage-foecr2) into this folder.
Then run:  python run.py
When it prints a web address, open that address in my default browser.
I want to watch videos there. Keep it running until I say stop.
To watch my own movies, run this instead:  python run.py --media "/path/to/my/Movies"
```

## Step 3 — watch
A browser tab opens at `http://127.0.0.1:8099`. You will see a **Welcome**
video already there — click it to confirm playback works. If you pointed it
at your movies folder, your films appear under **Movies** and on the **Home**
screen. Click one. Use the on-screen controls to play, pause, and seek.

Press **Ctrl+C** in the Claude Code terminal (or tell Claude "stop") to shut
it down.

---

## What you can watch
- **The bundled welcome clip** — always there, proves it works.
- **Your own video files** — point `--media` at a folder of movies you own.
  Files that play in a normal browser work directly: `.mp4`, `.m4v`, `.mov`,
  `.webm`. (`.mkv`/`.avi` are not shown yet — they need conversion first.)
- **Live TV / IPTV from your provider** — **not enabled.** That requires
  confirming what your provider permits first; see `PROVIDER_INTEGRATION.md`.
  Everything else works without it.

## Watch on more than one screen
Run `python run.py --lan`. It prints a second address like
`http://192.168.x.x:8099`. Open that on your phone or TV **on the same
Wi-Fi**. If two devices play the same thing, the hub fetches it once and
shares it. (Only use `--lan` on a network you trust — it has no password yet.)

## If something goes wrong
Tell Claude Code in the same session, in plain words:
- *"It says the port is in use"* → it will pick another automatically, or run
  `python run.py --port 9000`.
- *"The browser didn't open"* → copy the `http://127.0.0.1:...` address it
  printed into your browser yourself.
- *"My movie won't play"* → it is probably a `.mkv`/`.avi`. Ask Claude to
  convert a copy to `.mp4`.
- *"Install failed"* → you may be offline; reconnect and run `python run.py`
  again.

## What this is (one paragraph)
StreamOS is a small program that runs on your laptop and turns your own video
files into a clean, TV-style app you watch in a browser — and, when you tell
it what your IPTV provider allows, can share one stream to several devices in
your home. It never touches your provider on its own and plays only the files
and sources you give it.
