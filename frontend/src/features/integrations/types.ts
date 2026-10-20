import type { Schemas } from '@/types'

/** Strava client-credentials body (snake_case wire shape). */
export type StravaClientDto = Schemas['StravaClient']

/** Garmin Connect login body. */
export type GarminLoginDto = Schemas['GarminLogin']

/** Garmin Connect MFA-code body. */
export type GarminMfaDto = Schemas['garmin__schema__MFARequest']

/** The clean credentials the Strava connect dialog collects. */
export interface StravaClientInput {
  clientId: number
  clientSecret: string
}

/** The clean credentials the Garmin Connect login dialog collects. */
export interface GarminLoginInput {
  username: string
  password: string
  /** Whether to authenticate against Garmin's China region (connect.garmin.cn). */
  isCn: boolean
}

/** An inclusive start/end date window, each formatted `YYYY-MM-DD`. */
export interface DateRange {
  startDate: string
  endDate: string
}

/** Wire shape of `GET /googlehealth/status` (never carries tokens). */
export interface GoogleHealthStatusDto {
  configured: boolean
  linked: boolean
  access_token_expires_at: string | null
  redirect_uri: string
}

/** Whether the server has a Google OAuth client and whether this user is linked. */
export interface GoogleHealthStatus {
  /** The server has `GOOGLE_HEALTH_CLIENT_ID` and `_SECRET` set. */
  configured: boolean
  linked: boolean
  /** The redirect URI the server sends to Google; must be registered in Google Cloud. */
  redirectUri: string
}
