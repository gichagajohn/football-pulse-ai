# ⚽ Football Pulse AI

**A fully automated football media company — operated entirely by AI. Zero cost. Zero manual work.**

Runs 24/7 on Google Cloud Free Tier and automatically:
- Monitors live scores, goals, and match events
- Generates professional sports-media posters (inspired by 433, ESPN FC, OneFootball)
- Writes captions and hashtags
- Publishes to Facebook Page and Instagram Business
- Tracks engagement analytics

---

## 🏗️ Architecture

```
Data Agent → Decision Agent → Poster Agent → Caption Agent → Publisher Agent
                ↓                                                    ↓
         Duplicate Detection                              Analytics Agent
                ↑___________________SQLite DB________________________↑
                                        ↑
                              Scheduler Agent (APScheduler)
```

## 📁 Project Structure

```
football_pulse_ai/
├── main.py                        Entry point — starts the scheduler
├── cli.py                         Manual control & testing tool
├── settings.py                    All configuration (reads from .env)
├── requirements.txt
├── .env.example                   Copy to .env and fill in API keys
├── test_posters.py                Generate all poster types locally
├── deploy.sh                      One-shot Google Cloud deployment
├── football-pulse.service         Systemd unit file
│
├── agents/
│   ├── football_data_agent.py     Fetches data from free APIs + RSS
│   ├── content_decision_agent.py  Scores events, prevents spam
│   ├── duplicate_detection_agent.py  Dedup with 8-test self-test suite
│   ├── poster_design_agent.py     11 premium poster types via Pillow
│   ├── extra_posters.py           Starting XI, Record Broken, Half Time
│   ├── caption_agent.py           Templates + optional Grok AI (xAI)
│   ├── injury_transfer_agent.py   RSS-based news detector
│   ├── publisher_agent.py         Facebook + Instagram Graph API
│   ├── analytics_agent.py         Engagement tracking
│   └── scheduler_agent.py         Orchestrates all 7 recurring jobs
│
├── database/
│   └── schema.py                  SQLite DDL (6 tables) + helpers
│
├── utils/
│   ├── logger.py                  Coloured rotating logs
│   ├── http.py                    Resilient HTTP with retry/backoff
│   ├── image_utils.py             Cached image downloader
│   └── time_utils.py              Timezone-aware time helpers
│
├── assets/
│   └── fonts/                     Drop custom .ttf fonts here
│
├── output/
│   └── posters/                   Generated poster JPEGs land here
│
└── logs/
    └── football_pulse.log
```

---

## ⚡ Quick Start (Local)

```bash
# 1. Clone / unzip project
cd football_pulse_ai

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — add your Football-Data.org API key at minimum

# 5. Test poster generation (no API key needed)
python test_posters.py

# 6. Run the full system
python main.py
```

---

## 🖼️ Poster Types (11 total)

| Poster | File | Description |
|---|---|---|
| Goal Alert | `poster_design_agent.py` | Live goal with scorer, minute, score |
| Full Time | `poster_design_agent.py` | Final score with goals breakdown |
| Matchday | `poster_design_agent.py` | Pre-match preview with kickoff time |
| League Table | `poster_design_agent.py` | Top 16 standings with colour zones |
| Top Scorers | `poster_design_agent.py` | Top 10 scorers leaderboard |
| Transfer Alert | `poster_design_agent.py` | Player transfer with clubs and fee |
| Football Fact | `poster_design_agent.py` | Trivia / On This Day card |
| Today's Fixtures | `poster_design_agent.py` | Daily fixture list |
| Starting XI | `extra_posters.py` | Tactical pitch with formation |
| Record Broken | `extra_posters.py` | Record achievement with gold burst |
| Half Time | `extra_posters.py` | Half-time score card |

---

## 📅 Automation Schedule

| Interval | Job |
|---|---|
| Every 60 seconds | Live score monitoring + goal/FT detection |
| Every 15 minutes | League standings update (rotates through PL, La Liga, etc.) |
| Every 30 minutes | Transfer/injury RSS scan |
| Every 30 minutes | Analytics refresh from Meta API |
| 07:00 daily | Today's fixtures post |
| Every 1 hour | Football fact post |
| Every 6 hours | On This Day historical post |

---

## 🔑 API Keys Needed

| Service | Required | Cost | Link |
|---|---|---|---|
| Football-Data.org | ✅ Yes | Free | https://www.football-data.org |
| TheSportsDB | ✅ Built-in | Free (key = "1") | https://www.thesportsdb.com |
| Facebook Page Token | ✅ To publish | Free | https://developers.facebook.com |
| Instagram Business | Phase 2 | Free | Via Facebook App |
| Grok API (xAI) | ❌ Optional | Free tier | https://x.ai/api |

---

## 🖥️ CLI Commands

```bash
python cli.py test-posters      # Generate all 11 poster types
python cli.py test-captions     # Print sample captions to terminal
python cli.py test-dedup        # Run 8-test dedup self-test
python cli.py stats             # Analytics summary
python cli.py post-fact         # Manually trigger a fact post
python cli.py post-fixtures     # Manually trigger fixtures post
python cli.py clear-dedup       # Clear dedup history
python cli.py db-status         # Show DB row counts
```

---

## ☁️ Google Cloud Deployment

See **DEPLOYMENT_GUIDE.md** for the complete step-by-step.

**TL;DR:**
```bash
# On a fresh Ubuntu 22.04 e2-micro VM (always free):
chmod +x deploy.sh
./deploy.sh

# Edit .env with your API keys, then:
sudo systemctl restart football-pulse
sudo journalctl -u football-pulse -f
```

---

## 🛡️ Error Handling

- **API failures** → 3 retries with exponential backoff, then graceful skip
- **Duplicates** → 48-hour dedup window, per-event unique keys
- **Rate limiting** → Hard cap of 6 posts/hour (configurable)
- **Service crashes** → Systemd `Restart=always` recovers in 15 seconds
- **Meta API errors** → Post marked `failed` in DB, logged clearly

---

## 🚀 Future Scaling

1. Add player/team photo auto-download (TheSportsDB free images)
2. Multi-language captions (Swahili, French, Portuguese)
3. Multiple competition-specific pages (PL, UCL, La Liga)
4. TikTok API when available
5. PostgreSQL + Redis when traffic grows
6. Monetise at 10k followers via Facebook in-stream ads

---

## 📄 License

MIT — free to use, modify, and deploy.

Built with ❤️ using Python, Pillow, APScheduler, and the Meta Graph API.
