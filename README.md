# Auto Shorts

Every N hours (4 by default) this picks Korean Google Trends keywords that are still rising and turns each one into a news Short in the channel's format. That format is a header, a footage panel, info cards, subtitles, ElevenLabs narration and BGM.

## How a short is made
1. **Trends** (`trends.py`): reads the Google Trends KR RSS feed. Each keyword gets a rising score from three signals: search volume and recency, the pytrends curve for the last 40 minutes vs the 40 minutes before, and the change since the previous poll.
2. **Topic choice** (`planner.select_topics`): Claude drops ads, in-progress matches, private-individual tragedies and topics already made in the last 48h. It ranks the rest.
3. **Research** (`research.py`): pulls article bodies from the trend feed's links and Naver News search, plus Google News headlines.
4. **Plan** (`planner.write_plan`): Claude writes the script, subtitle chunks, highlighted keywords, info cards, header, thumbnail text, title, description and tags. Channel rules apply: allegation wording, no hanja or emoji, and so on.
5. **Narration and BGM** (`voice.py`): ElevenLabs TTS with character timestamps, and ElevenLabs Music.
6. **Footage** (`footage.py`): YouTube search (newest first, broadcasters preferred, uploaded within the last 4 days), downloads the first 4 minutes, detects scene cuts and builds contact sheets.
7. **Shot choice** (`planner.pick_shots`): Claude looks at the contact sheets and picks one scene per narration segment. It also picks the crop that removes broadcaster tickers, the on-screen credit and the thumbnail frames.
8. **Render** (`render/`): panel clips, frame compositor, loudness-normalised mix (-14 LUFS) and thumbnail.
9. **QA** (`planner.qa`): Claude checks preview frames for text overflow, wrong footage, identifiable private faces and broken frames.
   - Passing shorts go to `output/ready/`.
   - Failing shorts go to `output/needs_review/`.
   - Approved shorts are moved to `output/approved/` from the admin page. That folder is the step-2 auto-upload queue.

## Run locally
```bash
.venv/bin/python -m autoshorts trends           # ranked candidates
.venv/bin/python -m autoshorts make "키워드"     # one short
.venv/bin/python -m autoshorts run -n 2         # one full cycle
ADMIN_PASSWORD=... .venv/bin/python -m autoshorts.web   # admin page at :8080
```

Keys can be supplied in either of two places:
- In the admin page's settings. They are stored in `state/settings.json` with chmod 600.
- As environment variables (`.env`): `ELEVENLABS_API_KEY`, `ANTHROPIC_API_KEY`.

## Claude: API key vs Claude Code on the server
- `api` (recommended on the server): uses the Anthropic API key and is billed per call.
- `cli`: runs `claude -p` with the server's Claude Code login. Install it with `INSTALL_CLAUDE_CLI=1` during setup, then run `claude` once on the server to log in. This uses subscription limits, so 12 shorts a day may hit the cap.

## Deploy (AWS Lightsail, Ubuntu 24.04, 4 GB+ RAM)
```bash
scp -r autoshorts ubuntu@<ip>:~/       # or git clone
ssh ubuntu@<ip> 'cd autoshorts && sudo bash deploy/setup_ubuntu.sh'
```
Then open `http://<ip>/`, log in with the password the script printed, enter the keys in settings, and press **시작**.

Note: YouTube often rate-limits downloads from cloud IPs. If downloads fail, export `cookies.txt` from a logged-in browser and upload it on the settings page.

## Credits
- Font: [Pretendard](https://github.com/orioncactus/pretendard) (SIL Open Font License 1.1)
- Narration/BGM: ElevenLabs API, script/footage selection: Claude (Anthropic)
