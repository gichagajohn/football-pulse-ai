# Football Pulse AI — Complete Deployment & API Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              FOOTBALL PULSE AI                          │
│                                                         │
│  ┌─────────────┐    ┌──────────────────┐               │
│  │ Data Agent  │───▶│ Decision Agent   │               │
│  │ (APIs/RSS)  │    │ (Score/Dedupe)   │               │
│  └─────────────┘    └────────┬─────────┘               │
│                              │                          │
│                    ┌─────────▼─────────┐               │
│                    │  Poster Agent     │               │
│                    │  (Pillow graphics)│               │
│                    └─────────┬─────────┘               │
│                              │                          │
│                    ┌─────────▼─────────┐               │
│                    │  Caption Agent    │               │
│                    │  (Templates/AI)   │               │
│                    └─────────┬─────────┘               │
│                              │                          │
│                    ┌─────────▼─────────┐               │
│                    │ Publisher Agent   │               │
│                    │ (Facebook/IG API) │               │
│                    └─────────┬─────────┘               │
│                              │                          │
│  ┌─────────────┐    ┌─────────▼─────────┐               │
│  │  Analytics  │◀───│ SQLite Database   │               │
│  │  Agent      │    │ (6 tables)        │               │
│  └─────────────┘    └───────────────────┘               │
│                                                         │
│  ┌─────────────────────────────────────────────┐       │
│  │         Scheduler Agent (APScheduler)        │       │
│  │  • 60s:  Live scores                         │       │
│  │  • 15m:  Standings                           │       │
│  │  • 07:00: Today's fixtures                   │       │
│  │  • 1h:   Football facts                      │       │
│  │  • 6h:   On This Day                         │       │
│  │  • 30m:  Analytics refresh                   │       │
│  └─────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

## Folder Structure

```
football_pulse_ai/
├── main.py                       # Entry point
├── settings.py                   # All config
├── requirements.txt
├── .env.example → .env           # Your API keys
├── deploy.sh                     # One-shot GCP deployment
├── football-pulse.service        # Systemd unit file
├── test_posters.py               # Test poster generation
│
├── agents/
│   ├── football_data_agent.py    # Data collection
│   ├── content_decision_agent.py # Scoring & dedup
│   ├── poster_design_agent.py    # Pillow graphics
│   ├── caption_agent.py          # Captions & hashtags
│   ├── publisher_agent.py        # Meta Graph API
│   ├── analytics_agent.py        # Engagement tracking
│   └── scheduler_agent.py        # Orchestration
│
├── database/
│   └── schema.py                 # SQLite DDL & helpers
│
├── utils/
│   ├── logger.py                 # Coloured logging
│   └── http.py                   # Resilient HTTP session
│
├── assets/
│   └── fonts/                    # Drop custom TTF fonts here
│
├── output/
│   ├── posters/                  # Generated JPEGs
│   └── captions/
│
└── logs/
    ├── football_pulse.log
    └── service.log
```

---

## Part 1: Google Cloud Free Tier VM Setup

### Step 1: Create a Google Cloud account
1. Go to https://cloud.google.com
2. Sign up (you get $300 free credit + always-free tier)

### Step 2: Create the VM
```bash
# In Google Cloud Console → Compute Engine → VM instances → Create

# Settings:
# Name: football-pulse-ai
# Region: us-central1 (or closest to you)
# Machine type: e2-micro (FREE TIER - always free)
# Boot disk: Ubuntu 22.04 LTS, 30 GB standard persistent disk
# Firewall: Allow HTTP, Allow HTTPS
```

Or via gcloud CLI:
```bash
gcloud compute instances create football-pulse-ai \
    --machine-type=e2-micro \
    --zone=us-central1-a \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB \
    --tags=http-server,https-server
```

### Step 3: Connect to your VM
```bash
gcloud compute ssh football-pulse-ai --zone=us-central1-a
# Or use the SSH button in the Console
```

---

## Part 2: Deploy the Application

### Option A: Upload files via gcloud scp
```bash
# From your local machine, in the project folder:
gcloud compute scp --recurse . football-pulse-ai:/home/ubuntu/football_pulse_ai \
    --zone=us-central1-a
```

### Option B: Git clone (if you push to GitHub)
```bash
# On the VM:
git clone https://github.com/YOUR_USERNAME/football_pulse_ai.git
cd football_pulse_ai
```

### Run the deploy script
```bash
chmod +x deploy.sh
./deploy.sh
```

This automatically:
- Updates Ubuntu packages
- Installs Python 3, pip, fonts
- Creates a virtualenv
- Installs all Python requirements
- Creates `.env` from template
- Installs and starts the systemd service

---

## Part 3: API Keys Setup

### Football-Data.org (FREE)
1. Go to https://www.football-data.org/client/register
2. Register for a free account
3. Copy your API key
4. Add to `.env`: `FOOTBALL_DATA_API_KEY=your_key`

**Free tier includes:** Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, World Cup

### TheSportsDB (FREE)
- No registration needed for basic use
- Free key is literally `"1"`
- Already pre-configured: `THESPORTSDB_API_KEY=1`

---

## Part 4: Meta API Setup (Facebook + Instagram)

### Step 1: Create a Facebook App
1. Go to https://developers.facebook.com
2. Click "My Apps" → "Create App"
3. Choose "Business" type
4. Fill in app name: "Football Pulse AI"

### Step 2: Add Facebook Login & Pages API
1. In your app dashboard, click "Add Product"
2. Add "Facebook Login"
3. Add "Pages API"

### Step 3: Get a Page Access Token
1. Go to https://developers.facebook.com/tools/explorer
2. Select your app
3. Select your Facebook Page
4. Request these permissions:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_content_publish`
5. Click "Generate Access Token"
6. Copy the token

**For a long-lived token (60 days):**
```bash
curl -i -X GET \
  "https://graph.facebook.com/oauth/access_token?
  grant_type=fb_exchange_token&
  client_id={APP_ID}&
  client_secret={APP_SECRET}&
  fb_exchange_token={SHORT_LIVED_TOKEN}"
```

### Step 4: Get your Page ID
```bash
curl "https://graph.facebook.com/me/accounts?access_token=YOUR_PAGE_TOKEN"
# Look for "id" in the response for your page
```

### Step 5: Connect Instagram Business Account
1. Your Instagram must be a **Business** or **Creator** account
2. Connect it to your Facebook Page:
   - Facebook Page Settings → Instagram → Connect Account
3. Get your Instagram User ID:
```bash
curl "https://graph.facebook.com/v19.0/me?fields=instagram_business_account&access_token=YOUR_PAGE_TOKEN"
```

### Step 6: Add to .env
```env
FB_PAGE_ACCESS_TOKEN=EAAxxxxxxxx...
FB_PAGE_ID=123456789012345
IG_USER_ID=17841400000000000
```

### Step 7: Restart the service
```bash
sudo systemctl restart football-pulse
```

---

## Part 5: Service Management

```bash
# Check status
sudo systemctl status football-pulse

# View live logs
sudo journalctl -u football-pulse -f

# View application logs
tail -f /home/ubuntu/football_pulse_ai/logs/football_pulse.log

# Restart
sudo systemctl restart football-pulse

# Stop
sudo systemctl stop football-pulse

# Disable autostart
sudo systemctl disable football-pulse
```

---

## Part 6: Testing Before Going Live

```bash
cd /home/ubuntu/football_pulse_ai
source venv/bin/activate

# Test poster generation (no API keys needed)
python test_posters.py

# Test that database initialises
python -c "from database.schema import init_db; init_db(); print('DB OK')"

# Test captions
python -c "
from agents.caption_agent import generate_goal_caption
print(generate_goal_caption('Salah','Liverpool','Liverpool','Arsenal',2,1,87,'Premier League'))
"
```

---

## Part 7: Error Handling Strategy

### API failures
- All HTTP calls use `tenacity`-style retries via `requests.adapters.Retry`
- 3 retries with 1.5x exponential backoff
- Failed API calls log a warning and return `None` — the system continues

### Duplicate prevention
- Every event gets a unique key: `{match_id}:{event_type}:{minute}:{player}`
- Checked in `post_history` table before every post
- 48-hour dedup window (configurable)

### Rate limiting
- Hard cap: `MAX_POSTS_PER_HOUR` (default 6)
- Checked before every publish call

### Service crashes
- `systemd` with `Restart=always` and `RestartSec=15`
- Recovers automatically from any crash
- Logs preserved in `/logs/`

### Meta API errors
- Token expiry: logged clearly; service continues without publishing
- Network errors: retried; logged if persistent
- Image upload failures: post marked `failed` in DB; no retry loop

---

## Part 8: Future Scaling Plan

### Phase 2 — Richer Content
- Add player photo fetching (TheSportsDB has free player images)
- Download and composite real team logos automatically
- Add Starting XI poster type using lineup data from football-data.org

### Phase 3 — Multi-language
- Swahili captions for East African audience
- French, Spanish, Portuguese caption variants

### Phase 4 — Multiple Pages
- Run separate instances for different league pages
- Pass `--competition PL` CLI argument to filter by league

### Phase 5 — Upgrade Infrastructure
- Move from SQLite to PostgreSQL when post volume exceeds 10k/month
- Add Redis for faster dedup lookups
- Use Cloud Run (still free tier eligible for low traffic)

### Phase 6 — Monetisation
- Facebook In-Stream Ads (requires 10k followers)
- Instagram Shopping tags on merchandise
- Affiliate links in bio

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `FOOTBALL_DATA_API_KEY` | Yes | football-data.org free key |
| `THESPORTSDB_API_KEY` | No | Default "1" (free) |
| `FB_PAGE_ACCESS_TOKEN` | Yes (to publish) | Long-lived page token |
| `FB_PAGE_ID` | Yes (to publish) | Numeric page ID |
| `IG_USER_ID` | Phase 2 | Instagram business user ID |
| `GROK_API_KEY` | No | Optional AI captions (free at x.ai/api) |
| `MIN_PRIORITY_TO_POST` | No | 0-100, default 50 |
| `MAX_POSTS_PER_HOUR` | No | Default 6 |
| `TIMEZONE` | No | Default UTC |
