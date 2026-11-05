import stravaMark from '@/assets/strava/stravaLogo.jpeg'
import garminConnectApp from '@/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png'

/**
 * Brand logos for third-party fitness integrations, resolved to hashed asset
 * URLs by Vite. Lucide ships no brand icons, so these are bundled as images.
 *
 * @property stravaMark - The Strava "S" mark (square icon use).
 * @property garminApp - The Garmin Connect app icon (square icon use).
 */
export const INTEGRATION_LOGOS = {
  stravaMark,
  garminApp: garminConnectApp,
} as const
