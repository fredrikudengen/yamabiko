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
