# Yamabiko

Yamabiko is a mountain god, spirit, and yōkai in Japanese folklore; the term "yamabiko" also refers to the echo that occurs in mountains, after which the yōkai is named. Literally translated, the term means "mountain boy". It is the yōkai responsible for the natural phenomenon in mountains or canyons.

Yamabiko is a self-hosted log of hikes and other activities, run by one person for personal use.

## A fork of Endurain

Yamabiko is a fork of [Endurain](https://github.com/endurain-project/endurain) by João Vitória Silva, and most of the code is his work. It is **not** the official Endurain project and is not affiliated with or endorsed by it. Yamabiko no longer follows Endurain's updates.

Endurain® is a registered trademark of João Vitória Silva. It is named here only to credit the original project.

What Yamabiko adds compared to Endurain:

- **Google Health import** of Fitbit exercises
- **Segments:** your own segments, matched against every activity, with ranking among your efforts, climb rate and heart beats per 100 m climbed
- **Coverage map:** every map cell your activities have passed through, with the activities behind each cell
- **Distance-based charts** for pace, heart rate and elevation, with long stops left out
- **Heart-rate zones** counted on moving time, with editable limits
- **Separate map and photo cards** on the activity page, with photo upload

What Yamabiko has removed: gear, laps, health pages, goals, search, followers and user pages, notifications, sign-up and user administration, Garmin Connect, the Strava API link and single sign-on. Activities come in through file upload (.gpx, .tcx, .fit), a Strava export or Google Health.

Built with Vue 3 and TypeScript, FastAPI and SQLAlchemy, and PostgreSQL.

## Running it

Yamabiko has no published image; Docker builds it from this repository.

1. Copy the examples and fill in `.env` (passwords, `SECRET_KEY`, `FERNET_KEY`, `ENDURAIN_HOST`):

   ```bash
   cp .env.example .env
   cp docker-compose.yml.example docker-compose.yml
   ```

2. Create the data folders. The container runs as UID 1000:

   ```bash
   sudo mkdir -p /var/opt/endurain/backend/{data,logs}
   sudo chown -R 1000:1000 /var/opt/endurain/backend
   ```

3. Build and start:

   ```bash
   docker compose up -d --build
   ```

4. Open the app and sign in with `admin` / `admin`. Change the password under Settings → Security right away.

Database migrations run when the container starts. To update, pull the code and run `docker compose up -d --build` again.

### Reaching it from other devices with Tailscale

The compose example binds the app to `127.0.0.1:8080`, so only the machine itself can reach it. [Tailscale](https://tailscale.com) makes it available to your own devices over HTTPS:

```bash
sudo tailscale serve --bg 8080
```

Then set `ENDURAIN_HOST` in `.env` to the address it prints (for example `https://wallace.your-tailnet.ts.net`) and restart. Use that address on every device, including this one. If the host runs ufw, allow traffic from the tailnet:

```bash
sudo ufw allow in on tailscale0
```

On an iPhone, open the address in Safari and choose Share → Add to Home Screen to get it as an app. On Linux Mint, the Web Apps tool does the same for the desktop.

### Google Health

Create an OAuth client in the Google Cloud Console, put its ID and secret in `GOOGLE_HEALTH_CLIENT_ID` and `GOOGLE_HEALTH_CLIENT_SECRET`, and register `<ENDURAIN_HOST>/api/v1/googlehealth/callback` as an authorized redirect URI. Then link your account under Settings → Integrations.

## Development

Backend, from `backend/` (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv run pytest
uv run ruff check app tests
PYTHONPATH=app uv run lint-imports
```

Frontend, from `frontend/`:

```bash
npm ci
npm run dev
npm test
npm run type-check
npm run lint:check
```

After changing the API, regenerate the frontend types:

```bash
cd backend && uv run --frozen --no-config python scripts/export_openapi.py ../frontend/openapi.json
cd ../frontend && npm run gen:api
```

The frontend's design tokens are described in `docs/developer-guide/brand-and-ux-guidelines.md`, and the rules for using auth from other modules in `docs/developer-guide/auth-boundary.md`.

## License

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details. As a fork of Endurain it keeps the same license.
