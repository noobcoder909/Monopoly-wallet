# 🎩 Monopoly Wallet

A simple, mobile-friendly digital bank for Monopoly. One player is the **Banker** (host) and controls all money. Everyone else joins with a game code and can only view balances.

## Features

- Join a game by sharing a 4-character game code (up to 8 players)
- Banker sets the starting money and adds or deducts money for any player, or for everyone at once (e.g. passing GO)
- Players cannot change any amount
- Each player picks a name and a unique colour; the screen takes on that colour
- Live balances (refresh every 3 seconds) and a recent-activity log
- Rejoins automatically if the page is refreshed
- Clean, large-touch layout designed for Android phones

## How to play

1. **Banker:** open the site, tap **Host game**, enter the starting money, name and colour, then tap **Create game**.
2. Share the 4-character code shown at the top of the screen.
3. **Players:** tap **Join game**, enter the code, choose a name and a free colour.
4. **Banker:** tap a player, enter an amount (or use the 50 / 100 / 200 / 500 chips), add an optional note, then tap **Add** or **Deduct**. Use **Pay / charge everyone** for GO salary or taxes.

Deductions are blocked if a player does not have enough money.

## Project structure

```
api/index.py      Flask backend (create, join, taken, state, adjust)
public/index.html Frontend (HTML, CSS and JavaScript in one file)
vercel.json       Routes /api/* to the backend
requirements.txt  Python dependencies (Flask)
```

## Deploy on Vercel

Vercel runs the backend as short-lived functions, so game data is stored in a free Upstash Redis database.

1. Push this folder to a GitHub repository.
2. On [vercel.com](https://vercel.com), choose **Add New → Project**, import the repo and click **Deploy**.
3. In the project, open **Storage** (or **Marketplace**), add **Upstash Redis** and connect it to the project. This sets the environment variables automatically:
   - `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`, or
   - `KV_REST_API_URL` and `KV_REST_API_TOKEN`
4. Redeploy once so the variables take effect (**Deployments → ⋯ → Redeploy**).
5. Open your `.vercel.app` link and share it with the players.

## Run locally

The easiest way to run the full site (pages and API together) is the Vercel CLI:

```bash
npm i -g vercel
vercel dev
```

To run only the API with Flask for testing:

```bash
pip install flask
flask --app api/index run
```

Without Redis environment variables the backend falls back to temporary in-memory storage (data is lost on restart and is not shared between processes), which is fine for testing only.

## API (for reference)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/create` | POST | Create a game (`name`, `color`, `start`) |
| `/api/taken` | GET | Colours already used in a game (`code`) |
| `/api/join` | POST | Join a game (`code`, `name`, `color`) |
| `/api/state` | GET | Current players, balances and log (`code`, `token`) |
| `/api/adjust` | POST | Banker only: add or deduct (`code`, `token`, `target`, `op`, `amount`, `note`) |

Each player gets a secret token on joining; the server uses it to check who is the Banker.

## Notes and limits

- Games are deleted automatically after 3 days without activity.
- The free Upstash plan has a monthly command limit. Casual games are fine, but many players polling for a long time can use it up.
- There is no player-to-player transfer; all changes go through the Banker by design.
