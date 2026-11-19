"""The CO2 history store: one SCD41 sample stream in, one rolling history
out. Pure logic — no board imports (the sensor handle and the time module
come in via `sample()`), so the whole ring runs against the host harness
in sim/ regardless of import order (a host-side import of this module
binds the real `time`; the clock must not be trusted from that binding)."""

from array import array

# SCD41 sample cadence: the board reads the sensor at most this often
CO2_INTERVAL_S = 15
CO2_BUCKET_S = 180  # one strip column = one averaged ring entry (3 min)
CO2_LOG_N = 64      # ring slots: ~3.2 h of bucket means, 384 bytes total


class Co2Ring:
    """The CO2 store: raw readings land here (via `sample()`), bucket
    means come out (via `history()`), and the big readout's number is
    `current()`. The ring owns its own cadence: `sample()` is cheap to
    call often and no-ops unless CO2_INTERVAL_S has passed. The caller
    passes its own `time` module: under sim/ main.py runs on the mocked
    clock, and the ring must tick the same one it does."""

    def __init__(self):
        # 'i': epoch seconds; 'H': ppm — the SCD41's spec range is
        # 400..5000 (note (0,)*N pre-fills a tuple BEFORE array())
        self._ts = array("i", (0,) * CO2_LOG_N)
        self._ppm = array("H", (0,) * CO2_LOG_N)
        self._head = 0    # the next write slot
        self._count = 0   # filled slots
        self._open = None  # the open bucket [slot, ppm sum, reads]
        self._last_t = None  # epoch of the last logged reading
        self._reading = None  # the latest raw reading (see current())

    def sample(self, sensor, t):
        """Read the sensor once (skip when the cadence doesn't allow it)
        and add the reading to the rolling bucket. `t` is the time
        module — main.py's own import, so sim and board tick alike.
        Returns the fresh reading, or None if no reading was taken this
        call."""
        now = int(t.time())
        if self._last_t is not None and now - self._last_t < CO2_INTERVAL_S:
            return None
        if sensor is None or not sensor.ready():
            return None
        try:
            co2, _temp, _rh = sensor.measure()
        except Exception as e:
            print("scd41 read failed:", e)
            return None
        if co2 < 400:  # below the SCD41's spec floor = a hiccup, not air
            return None
        # measure() returns floats on this build (the sim mocks them too;
        # this cast is the reason the ring stores ints safely)
        co2 = int(co2)
        self._reading = co2
        slot = now // CO2_BUCKET_S  # this reading's wall-clock bucket
        if self._open is None:
            self._open = [slot, 0, 0]
        elif slot != self._open[0]:
            # the reading crossed into a new slot: commit the passed-over
            # one and open fresh for this reading (empty slots in between
            # store nothing — unsampled time is unknown, not zero)
            self._commit()
            self._open = [slot, 0, 0]
        self._open[1] += co2
        self._open[2] += 1
        self._last_t = now
        return co2

    def _commit(self):
        """The open bucket's mean lands in the ring (the entry's ts is the
        slot's start epoch); the next reading opens a fresh bucket."""
        self._ts[self._head] = self._open[0] * CO2_BUCKET_S
        self._ppm[self._head] = (self._open[1] + self._open[2] // 2) \
            // self._open[2]
        self._head = (self._head + 1) % CO2_LOG_N
        self._count = min(self._count + 1, CO2_LOG_N)

    def history(self):
        """The bucket means, oldest -> newest, as [(epoch_s, ppm)]."""
        entries = []
        for k in range(self._count):
            i = (self._head - self._count + k) % CO2_LOG_N
            entries.append((self._ts[i], self._ppm[i]))
        return entries

    def current(self):
        """The latest raw reading's ppm (the big readout's number), or
        None before the first reading lands."""
        return self._reading

    def restore(self, readings):
        """Replace the ring's contents with a known history [(epoch_s,
        ppm)] — the test seed and any future state-reload path; the live
        sample() flow never calls this."""
        self._ts = array("i", (0,) * CO2_LOG_N)
        self._ppm = array("H", (0,) * CO2_LOG_N)
        for k, (t, ppm) in enumerate(readings):
            self._ts[k] = t
            self._ppm[k] = ppm
        self._head = len(readings) % CO2_LOG_N
        self._count = min(len(readings), CO2_LOG_N)
        self._open = None
        # no _last_t seeding: the next live reading starts a fresh open
        # bucket; its cadence clock starts from that first sample
        self._last_t = None
