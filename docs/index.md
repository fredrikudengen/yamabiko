<div align="center">
  <p>
    <img class="index-logo" src="assets/brand_logo_light_theme.png" width="150" height="150">
  </p>

  <h2>
      Yamabiko
  </h2>
  <p>
    A self-hosted fitness tracking service
  </p>
</div>

!!! note "A fork of Endurain"
    Yamabiko is a fork of [Endurain](https://github.com/endurain-project/endurain) by João Vitória Silva. It is not the official Endurain project and is not affiliated with it. Most of these pages are inherited from Endurain's documentation and may not match Yamabiko exactly. See the [README](https://github.com/fredrikudengen/yamabiko#readme) for what differs.

    Endurain® is a registered trademark of João Vitória Silva.

## What is Yamabiko?

Yamabiko is a self-hosted fitness tracking service designed to give users full control over their data and hosting environment. Built with:

- **Frontend:** Vue.js 3 with TypeScript, Tailwind CSS and shadcn-vue components, with Pinia and TanStack Query for state management
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, Apprise, stravalib and python-garminconnect for Strava and Garmin Connect integration, gpxpy, tcxreader and fitdecode for .gpx, .tcx and .fit file import respectively
- **Database:** PostgreSQL for efficient data management
- **Observability:** Jaeger for basic tracing and monitoring

Yamabiko has no published Docker image; build it from source with the "docker-compose.yamabiko.yml.example" file in the project repository. Configuration is done through environment variables.

## Features

Inherited from Endurain:

- Multi-user functionality with admin and user profiles adaptable interfaces
- Activity import via manual or bulk upload (.gpx, .tcx and .fit files. .fit files are preferred)
- Strava integration for syncing activities and gear
- Garmin Connect integration for syncing activities, gear and body composition
- Activity feeds and statistics (week/month)
- Basic activity privacy settings
- Gear tracking and default gear for activity types
- User pages with stats and activity histories
- Follower features (view activities)
- Multi-language support
- Imperial and metric units support
- Dark/light theme switcher
- Third-party app support
- Weight, steps and sleep logging
- Notification system
- Define and track goals
- MFA TOTP support
- Password reset through email link. Uses Apprise for email notifications
- Sign-up with configurable email verification and admin approval
- SSO support (OIDC/SAML)

Added in Yamabiko:

- Google Health import of Fitbit exercises
- Segments matched against every activity, with ranking among your own efforts
- Distance-based pace, heart-rate and elevation charts
- Heart-rate zones counted on moving time

## License

This project is licensed under the AGPL-3.0 or later License.
