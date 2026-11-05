/**
 * Centralised TanStack Query key factories — the single source of truth for
 * every server-state cache key in the app.
 *
 * Why this exists: query keys are how TanStack Query identifies, caches, and
 * invalidates server data. When keys are hand-written as ad-hoc string arrays
 * (`['notifications']`) scattered across composables and realtime handlers,
 * they silently drift — a typo or a shape change in one place stops matching
 * the other, and invalidations quietly stop working. Routing every key through
 * this factory keeps reads, writes, and invalidations referring to the exact
 * same key.
 *
 * The canonical server-state pattern every feature should follow:
 *   1. service fn   — `apiFetch` + a mapper, in `@/services/<domain>.ts`
 *      (DTO → clean model boundary, e.g. {@link mapUserProfile}).
 *   2. key factory  — a domain entry in {@link queryKeys} below.
 *   3. composable    — `useXxxQuery()` in `@/composables/` calling `useQuery`
 *      with `queryFn` (the service fn) and `queryKey` (the factory).
 *   4. view          — consumes the composable; never calls `fetch`/`apiFetch`
 *      directly and never holds server data in Pinia.
 *
 * For writes, follow the mutation reference in `@/composables/useNotifications`
 * (`useMarkNotificationReadMutation`): optimistic `onMutate` + snapshot,
 * `onError` rollback, and `onSettled` invalidation of the domain's `all()` key.
 *
 * Adding a domain: follow the `notifications` shape — `all()` is the broad
 * prefix used for "invalidate everything in this domain"; `list(filters)` and
 * `detail(id)` narrow from it so partial invalidation (`all()`) cascades to
 * every list and detail query for that domain.
 */
export const queryKeys = {
  /** The authenticated user's profile (seeded by the auth store on login). */
  currentUser: () => ['current-user'] as const,

  /** Unauthenticated settings consumed by the login / sign-up screens. */
  public: {
    serverSettings: () => ['public-server-settings'] as const,
    identityProviders: () => ['public-identity-providers'] as const,
  },

  /**
   * Activities domain. New activities are created via the file-upload reference
   * (`@/features/upload`); its mutation invalidates `all()` on settle so every
   * activities list refetches.
   */
  activities: {
    /** Broad prefix; invalidating this cascades to every activities query. */
    all: () => ['activities'] as const,
    lists: () => ['activities', 'list'] as const,
    /**
     * @param filters - Serializable list filters (paging, type, etc.).
     * @returns A list query key scoped to the given filters.
     */
    list: (filters: Record<string, unknown> = {}) => ['activities', 'list', filters] as const,
    details: () => ['activities', 'detail'] as const,
    /**
     * @param id - Activity identifier.
     * @returns A detail query key for a single activity.
     */
    detail: (id: number) => ['activities', 'detail', id] as const,
    /**
     * @param id - Activity identifier.
     * @returns A query key for an activity's metric streams.
     */
    streams: (id: number) => ['activities', 'detail', id, 'streams'] as const,
    /** Planned workout steps for one activity. */
    workoutSteps: (id: number) => ['activities', 'detail', id, 'workout-steps'] as const,
    /** Performed workout sets for one activity. */
    sets: (id: number) => ['activities', 'detail', id, 'sets'] as const,
    /** The exercise-name catalogue (shared across activities). */
    exerciseTitles: () => ['activities', 'exercise-titles'] as const,
    /** Media (photos) attached to one activity. */
    media: (id: number) => ['activities', 'detail', id, 'media'] as const,
    /** The activity's owner user (public or authenticated), keyed by user id. */
    owner: (userId: number) => ['activities', 'owner', userId] as const,
    /** The distinct activity-type codes the user owns (type-filter options). */
    types: () => ['activities', 'types'] as const,
    /** The user's activity-type code→name map (summary type filter). */
    typeNames: () => ['activities', 'type-names'] as const,
    /**
     * An aggregated activity summary for a view type + period + optional type
     * filter (the `/summary` view). Under the `activities` prefix so an `all()`
     * invalidation after an upload/delete refetches it.
     *
     * @param params - Serializable summary params (view type, date/year, type).
     * @returns A summary query key scoped to those params.
     */
    summary: (params: Record<string, unknown> = {}) => ['activities', 'summary', params] as const,
    /**
     * The home dashboard's infinite feed of a user's own activities. Under the
     * `list` prefix so an `all()` invalidation (e.g. after upload/delete)
     * refetches it.
     *
     * @param userId - The feed owner's user id.
     * @param pageSize - Records per page (the only paging filter; the infinite
     *   query keys on size, not page number, so all pages share one entry).
     * @returns A list query key for the user's home feed.
     */
    userFeed: (userId: number, pageSize: number) =>
      ['activities', 'list', { scope: 'user-feed', userId, pageSize }] as const,
    /**
     * The home dashboard's feed of activities from people the user follows.
     *
     * @param userId - The viewer's user id.
     * @param pageSize - Records per page.
     * @returns A list query key for the followed-users feed.
     */
    followersFeed: (userId: number, pageSize: number) =>
      ['activities', 'list', { scope: 'followers-feed', userId, pageSize }] as const,
    /**
     * A user's per-sport aggregated stats for a timeframe (home dashboard).
     *
     * @param userId - The user whose stats to key.
     * @param timeframe - `week` or `month`.
     * @returns A stats query key.
     */
    stats: (userId: number, timeframe: 'week' | 'month') =>
      ['activities', 'stats', userId, timeframe] as const,
    /**
     * A user's activity count for the current month (public-profile header).
     *
     * @param userId - The user whose monthly count to key.
     * @returns A query key for the user's this-month activity count.
     */
    monthCount: (userId: number) => ['activities', 'month-count', userId] as const,
    /**
     * A user's activities for a configured week (public-profile week browser).
     * Under the `list` prefix so an `all()` invalidation refetches it.
     *
     * @param userId - The profile owner's user id.
     * @param week - Week offset (0 = this week).
     * @returns A list query key for that week's activities.
     */
    weekActivities: (userId: number, week: number) =>
      ['activities', 'list', { scope: 'user-week', userId, week }] as const,
  },

  /**
   * Server settings domain (admin). The singleton settings object and the
   * static tile-map presets each get a key; the edit mutation invalidates
   * `all()` on settle so the form refetches the server-authoritative state.
   */
  serverSettings: {
    /** Broad prefix; invalidating this cascades to every server-settings query. */
    all: () => ['server-settings'] as const,
    /** The singleton server-settings object. */
    detail: () => ['server-settings', 'detail'] as const,
    /** The static catalogue of selectable tile-server presets. */
    tileTemplates: () => ['server-settings', 'tile-templates'] as const,
  },

  /**
   * Identity providers domain (admin SSO config). `all()` is the broad prefix
   * the create/update/delete mutations invalidate on settle so the list (and
   * any derived view) refetches the server-authoritative state.
   */
  identityProviders: {
    /** Broad prefix; invalidating this cascades to every IdP query. */
    all: () => ['identity-providers'] as const,
    /** The admin list of all configured providers. */
    list: () => ['identity-providers', 'list'] as const,
    /** The static catalogue of provider presets. */
    templates: () => ['identity-providers', 'templates'] as const,
  },

  /**
   * The authenticated user's own settings profile (identity + privacy). Kept
   * separate from {@link queryKeys.currentUser} (the narrow shell model): the
   * profile zone needs the full field set, and its edits invalidate both keys.
   */
  /** Google Health link status (settings → integrations). */
  googleHealth: {
    status: () => ['google-health', 'status'] as const,
  },

  profile: {
    /** Broad prefix; invalidating this cascades to every profile query. */
    all: () => ['profile'] as const,
    /** The full self-profile (identity + privacy). */
    detail: () => ['profile', 'detail'] as const,
    /** The user's per-activity default-gear assignments. */
    defaultGear: () => ['profile', 'default-gear'] as const,
  },

  /**
   * Core application metadata fetched from the backend and external sources.
   */
  core: {
    /** The running backend's version (`/about`). */
    aboutVersion: () => ['core', 'about-version'] as const,
    /** The latest published stable release tag from the upstream repository. */
    latestRelease: () => ['core', 'latest-release'] as const,
    /** The latest published pre-release tag from the upstream repository. */
    latestPreRelease: () => ['core', 'latest-pre-release'] as const,
  },

  /**
   * Segments (a start and an end node) and the efforts of activities on them.
   * `all()` is the broad prefix: a segment write also changes effort counts and
   * the efforts shown on activities, so it invalidates everything here.
   */
  segments: {
    /** Broad prefix; invalidating this cascades to every segment query. */
    all: () => ['segments'] as const,
    /** The user's segments. */
    list: () => ['segments', 'list'] as const,
    /** @param id - Segment identifier. */
    detail: (id: number) => ['segments', 'detail', id] as const,
    /** @param id - Segment identifier. */
    efforts: (id: number) => ['segments', 'efforts', id] as const,
    /** @param activityId - Activity identifier. */
    activityEfforts: (activityId: number) => ['segments', 'activity-efforts', activityId] as const,
    /** @param activityId - Activity identifier. */
    track: (activityId: number) => ['segments', 'track', activityId] as const,
  },

  /**
   * The coverage map: which cells the user's tours have passed through. One
   * entry per cell size; `all()` is the broad prefix the rebuild invalidates,
   * since it changes every cell size at once.
   */
  coverage: {
    /** Broad prefix; invalidating this cascades to every cell size. */
    all: () => ['coverage'] as const,
    /** @param zoom - Zoom of the grid the cells are counted at. */
    grid: (zoom: number) => ['coverage', 'grid', zoom] as const,
    /** The tours in one cell; under `all()` so a rebuild refetches it too. */
    cell: (zoom: number, x: number, y: number) => ['coverage', 'cell', zoom, x, y] as const,
  },

  /**
   * The authenticated user's account security state (MFA, backup codes, active
   * sessions). `all()` is the broad prefix the security mutations invalidate so
   * the affected cards refetch the server-authoritative state.
   */
  security: {
    /** Broad prefix; invalidating this cascades to every security query. */
    all: () => ['security'] as const,
    /** Whether MFA (TOTP) is enabled. */
    mfaStatus: () => ['security', 'mfa-status'] as const,
    /** The remaining-backup-codes summary. */
    backupCodeStatus: () => ['security', 'backup-code-status'] as const,
    /** The user's active sessions. */
    sessions: () => ['security', 'sessions'] as const,
    /** The user's linked identity providers. */
    linkedProviders: () => ['security', 'linked-providers'] as const,
    /** The user's API keys. */
    apiKeys: () => ['security', 'api-keys'] as const,
  },
} as const
