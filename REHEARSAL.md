# A test run, and back to zero

Everything here runs from this folder on your Mac. A full pass takes about 20 minutes, the
preparation five, the clean-up two.

## Without a terminal: the deck's first slide

The deck is served from the cluster. Open its address and type the password on slide 1 (the key
**L** jumps to the field from any slide). There's no user name. The password is `DECK_PASSWORD` in
`.env`; `make up-shop` puts it on the cluster. Slide 1 then is the whole guide: the logins, every
address, and three buttons. The browser remembers you until you press **lock** on that slide. The
old link that ends in `#key=…` still works (`make links SECRETS=1` prints it).

| Button | What it does | Time |
|---|---|---|
| Prepare | checks the platform, the oracles, the stored campaign and the night; restarts the OpenClaw gateways; plays a trial run; empties everything | about 2 minutes |
| Prepare with the night | the same, with the blond boy's 40 visits first | about 4 minutes |
| Reset | empties the desk, the conversations and every counter | 5 seconds |

The buttons do from inside the cluster what `make prepare` does from this laptop. Three things
stay with the laptop: the cluster login, `make dashboard` (the digital apprentice's own console)
and `make shell-ui`. After a change to the deck's files, `make up-deck` publishes it again.
Without the password the same address shows the scripted deck, which you can hand to anyone.

## From this laptop: one command

```bash
make prepare
```

It logs in, checks the platform and every oracle, checks the stored campaign (and runs it if it is
missing), runs the night, restarts the OpenClaw gateways, plays a trial run (first-year, blond
boy, the three guardrails, one phone), empties everything, forwards the digital apprentice's
console to this laptop (http://127.0.0.1:18789, opened in your browser) and writes the deck's
live config. It
ends with a table of what is ok, what to look at and what failed, and the few steps that are
yours. About 12 minutes; 8 of them are the night run.

| Command | When | Time |
|---|---|---|
| `make prepare` | the morning of the talk, or after anything was rolled out | about 12 minutes |
| `make prepare QUICK=1` | between a rehearsal and the real run: everything except the night | about 3 minutes |
| `make prepare CAMPAIGN=1` | if you want fresh campaign results too | about 18 minutes |
| `make prepare CHECK=1` | only look, change nothing | 10 seconds |

The tables below are the same steps by hand, for when you want to do only one of them.

## Before you start

| Step | Command | Why |
|---|---|---|
| 1 | `make cluster-login` | Only if authentication has expired; uses your current kubeconfig and interactive cluster login. |
| 2 | `make deck-live` | Writes the live addresses, the desk key and the console's address into the deck. |
| 3 | `python3 scripts/shop-say.py --reset` | "New day": empties requests and fittings, and every customer starts a fresh conversation. |
| 4 | `python3 scripts/rush-sim.py --reset` | Rush counters and the oracles' call counters back to zero. |
| 5 | `python3 -m http.server 8765 --directory deck` | Serves the deck. Leave it running in its own terminal. |
| 6 | Open http://127.0.0.1:8765 and press F | Start on slide 2, so the live frames load in the background. |
| 7 | Log in to the OpenShift console in the same browser | The links on slides 6, 17 and 20 open console pages in a tab. `make links` prints the address; the password is in `local/cluster-admin-password`. |
| 8 | Optional: open MLflow in a second tab | Slide 14 shows the day's scroll and the visit in MLflow as a capture. If you want the real page too: workspace `ollivanders`, experiment `apprentice`. `make links` prints the address. |

Optional, only if you want them in the run:

- `make dashboard` for the digital apprentice's console live (slide 10, "open it live").
- `make shell-ui` for OpenShell's terminal UI (slide 12).

You don't need `make campaign` or `make captures` for a test run. Both were done on 16 November
at 12:49 and 13:53, and slide 20 replays the stored campaign.

## During the run

- Slide 1 is backstage: the guide, Prepare and Reset. The talk starts on slide 2.
- Keys: right arrow or space for next, left for back, N for notes, R restarts the slide, M
  switches a demo slide between live and scripted.
- Slide 9 (demo 1): four clicks. Each one sends a line to the real digital apprentice, and he
  needs 5 to 15 seconds. Keep talking.
- Slide 14 (demo 2, the day's scroll): six clicks. It reads the visits you just made on slide 9,
  so play slide 9 first. Click 3 shows the first-year's visit in MLflow. If you open MLflow itself,
  don't open the blond boy's trace: MLflow shows the name unredacted.
- Slide 17 (demo 3): three clicks, then the chat field is yours.
- Slide 22: scan the QR code with your own phone. You get a wizard's name and a plain chat.
  Slide 23 shows the counters; `python3 scripts/rush-sim.py 12` adds twelve simulated phones if
  you want to see the queue move.
- If a live slide sticks: M puts the scripted version on. M again brings live back.

## Clean-up: back to zero

| Step | Command | What it clears |
|---|---|---|
| 1 | `python3 scripts/shop-say.py --reset` | Requests, fittings and all conversations (same as "New day" on the desk). |
| 2 | `python3 scripts/rush-sim.py --reset` | Wizards in the shop, answers, tricks, the name counter, the oracles' call counters. |
| 3 | Reload the deck (cmd + shift + R), go to slide 2 | The chats on screen. The rail counters reset themselves when you enter slide 17. |
| 4 | If you pressed M anywhere: press M again on that slide | The switch is remembered per browser tab. A new tab also starts live. |
| 5 | `make dashboard-stop` | Only if you ran `make dashboard`. |

After that the shop is where it was before the run. Two things are not reset, on purpose:

- MLflow keeps the traces of the run. That's fine: on stage you open the newest one.
- The stored campaign results stay, so slide 20 keeps working.

## Tomorrow morning, before the talk

1. `make cluster-login`
2. `make deck-live`
3. `make campaign` (about five minutes per release; optional if you're happy with the stored run)
4. `make night` (about eight minutes; fills "while the shop was shut" on slide 14 with fresh visits; optional if the last night run is the one you want to show)
5. `make up-tune` (required: it restarts OpenClaw's gateway inside each sandbox, which frees its
   256 MCP connections; sessions and the audit log stay)
6. The "Before you start" table above, from step 3

Don't run `make up-apprentice`, `make up-pool` or `make up-platform`. They recreate the sandboxes
and empty the audit log.

## If something looks wrong

| What you see | What to do |
|---|---|
| "The digital apprentice is lost for words" after 2 seconds | `make up-tune`, then try again |
| A link opens the console's login page | Log in there once, then click the link again |
| A live frame stays empty | Reload the deck; if it stays empty, M for the scripted version |
| Answers take longer than 30 seconds | `make oracle` shows which oracle answers and whether one is resting |
| "Not logged in to the cluster" | `make cluster-login` |
