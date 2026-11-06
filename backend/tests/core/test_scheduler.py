"""Tests for core.scheduler — APScheduler setup and lifecycle."""

from unittest.mock import patch


class TestSchedulerJobId:
    """Tests for _scheduler_job_id helper."""

    def test_generates_stable_id_from_description(self):
        from core.scheduler import _scheduler_job_id

        result = _scheduler_job_id("refresh Strava user tokens every 60 minutes")
        assert result == "endurain_refresh_strava_user_tokens_every_60_minutes"

    def test_handles_single_word_description(self):
        from core.scheduler import _scheduler_job_id

        result = _scheduler_job_id("test")
        assert result == "endurain_test"


class TestStartScheduler:
    """Tests for start_scheduler."""

    def test_starts_scheduler_when_not_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()
            mock_scheduler.start.assert_called_once_with()

    def test_skips_start_when_already_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = True
            from core.scheduler import start_scheduler

            start_scheduler()
            mock_scheduler.start.assert_not_called()

    def test_adds_all_recurring_jobs(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()
            # 14 before the Strava API and Garmin Connect jobs (Strava tokens,
            # Strava activities, Garmin activities, Garmin health) and the
            # sign-up token purge were removed.
            assert mock_add_job.call_count == 7

    def test_google_health_sync_job_registered(self):
        import google_health.activity_utils as google_health_activity_utils

        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()

        funcs = [call.args[0] for call in mock_add_job.call_args_list]
        assert google_health_activity_utils.sync_all_users in funcs

    def test_no_strava_api_or_garmin_job_is_registered(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()

        modules = {call.args[0].__module__ for call in mock_add_job.call_args_list}
        assert not {m for m in modules if m.startswith(("garmin", "strava"))}


class TestAddSchedulerJob:
    """Tests for add_scheduler_job."""

    def test_adds_job_successfully(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.core_logger.print_to_log") as mock_log,
        ):
            from core.scheduler import add_scheduler_job

            def dummy():
                pass

            add_scheduler_job(dummy, "interval", 60, [True], "test job every 60 minutes")
            mock_scheduler.add_job.assert_called_once_with(
                dummy,
                "interval",
                minutes=60,
                args=[True],
                id="endurain_test_job_every_60_minutes",
                replace_existing=True,
            )
            mock_log.assert_called_once()

    def test_logs_error_when_add_job_fails(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.core_logger.print_to_log") as mock_log,
        ):
            mock_scheduler.add_job.side_effect = ValueError("something went wrong")
            from core.scheduler import add_scheduler_job

            def dummy():
                pass

            add_scheduler_job(dummy, "interval", 60, [], "failing job")
            mock_log.assert_any_call(
                "Failed to add scheduler job to failing job: ValueError",
                "error",
                exc=mock_scheduler.add_job.side_effect,
            )


class TestStopScheduler:
    """Tests for stop_scheduler."""

    def test_shuts_down_when_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = True
            from core.scheduler import stop_scheduler

            stop_scheduler()
            mock_scheduler.shutdown.assert_called_once_with(wait=False)

    def test_skips_shutdown_when_not_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = False
            from core.scheduler import stop_scheduler

            stop_scheduler()
            mock_scheduler.shutdown.assert_not_called()
