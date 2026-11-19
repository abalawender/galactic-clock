"""The RTC maintenance service: re-syncs NTP while the clock runs. The
boot-time sync (and the `ntp_synced` latch) stay in main.py's
connect_wifi(); this module only owns the running cadence — six hours.
Pure logic: the time module comes in via the call (same contract as the
co2 ring), so the cadence runs against the host harness unchanged."""

import ntptime

NTP_INTERVAL_S = 6 * 3600  # a synced RTC holds well; re-sync this often
NTP_RETRY_S = 300          # one failed attempt retries this much later


class NtpSync:
    """The re-sync cadence: `sync_if_due()` is cheap to call every loop
    pass and only attempts the real NTP round-trip on its schedule. The
    caller passes its own `time` module (sim: the mocked clock), so the
    service ticks whatever clock the app itself ticks."""

    def __init__(self, first_attempt_in=NTP_INTERVAL_S):
        # the caller sets when the FIRST in-loop attempt is due: six
        # hours after a successful boot sync, but NTP_RETRY_S after a
        # failed one — a one-off NTP failure at boot must not leave the
        # clock unsynced until the next full interval
        self._first_in = first_attempt_in
        self._next_due = None  # epoch when the next attempt is allowed

    def sync_if_due(self, t):
        """Attempt an NTP sync when due. `t` is the caller's time
        module. Returns True only when a sync succeeded this call. The
        first call anchors the schedule instead of attempting (the boot
        sync just ran; see `first_attempt_in` for the failed-boot case).
        The post-sync epoch is re-read after `settime()` — the call
        itself corrects the clock, and the schedule must hang off the
        corrected time, not the drifted one."""
        now = t.time()
        if self._next_due is None:
            self._next_due = now + self._first_in
        if now < self._next_due:
            return False
        try:
            ntptime.settime()
        except Exception as e:
            print("ntp re-sync failed:", e)
            self._next_due = t.time() + NTP_RETRY_S
            return False
        self._next_due = t.time() + NTP_INTERVAL_S
        print("rtc re-synced")
        return True
