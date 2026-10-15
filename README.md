# Yamabiko - Mythos
  
Yamabiko is a mountain god, spirit, and yōkai in Japanese folklore; the term "yamabiko" also refers to the echo that occurs in mountains, after which the yōkai is named. Literally translated, the term means "mountain boy". It is the yōkai responsible for the natural phenomenon in mountains or canyons. 

## The App

This is a self-hosted fitness tracking service designed to give users full control over their data and hosting environment. It's similar to Strava but focused on privacy and customization. Built with:

- **Frontend:** Vue.js 3 with TypeScript, Tailwind CSS and shadcn-vue components, with Pinia and TanStack Query for state management
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, Apprise, stravalib and python-garminconnect for Strava and Garmin Connect integration, gpxpy, tcxreader and fitdecode for .gpx, .tcx and .fit file import respectively
- **Database:** PostgreSQL for efficient data management
- **Observability:** Jaeger for basic tracing and monitoring
- **Integrations:** Supports Strava and Garmin Connect. Manual upload of activities using .gpx, .tcx and .fit files are also supported

To deploy Yamabiko, a Docker image is available, and a comprehensive example can be found in the "docker-compose.yml.example" file provided. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization.

## License

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.
