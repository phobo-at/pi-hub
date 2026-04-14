(function bootstrap() {
  const boot = window.__SMART_DISPLAY__ || {};
  const config = boot.config || {};
  let state = boot.state || {};
  let screensaverActive = false;
  let idleTimer = null;
  let pollTimer = null;
  let slideshowTimer = null;
  let resizeTimer = null;
  let midnightTimer = null;
  // Plan B1 watchdog: while the screensaver is visible we re-POST
  // /api/screensaver/state periodically so the backend pause-TTL stays
  // fresh. If this loop stops firing (tab crash, JS exception), the TTL
  // expires and Spotify polling resumes on its own.
  let screensaverHeartbeatTimer = null;
  const SCREENSAVER_HEARTBEAT_MS = 5 * 60 * 1000;

  // Cached Intl formatters. Re-creating them per tick burns measurable CPU
  // on a Pi Zero 2 W; see plan B5. The weekday formatter drives the client-
  // side day label computation (mirrors smart_display/calendar_layout.py).
  const LOCALE = config.locale || "de-AT";
  const TIMEZONE = config.timezone || "Europe/Vienna";
  const WEEKDAY_FMT = new Intl.DateTimeFormat(LOCALE, {
    weekday: "long",
    timeZone: TIMEZONE,
  });
  const SECTION_DATE_FMT = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: TIMEZONE,
  });
  // Plan B5: the old updateClock allocated three Intl formatters per second
  // on a Pi Zero 2 W. Cache them once and drive the tick by a
  // setTimeout-to-next-minute so the idle CPU is closer to 0 %.
  const CLOCK_TIME_FMT = new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TIMEZONE,
  });
  const CLOCK_DATE_FMT = new Intl.DateTimeFormat(LOCALE, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: TIMEZONE,
  });
  let clockTimer = null;

  // QLOCKTWO word-clock face. The Python module smart_display/watch_faces.py
  // owns the canonical layout; this block is a 1:1 mirror so the minute tick
  // doesn't need to round-trip to the server. Keep the two sides in sync.
  const QLOCKTWO_WORDS = {
    ES: [0, 0, 2],
    IST: [0, 3, 3],
    FUENF_MIN: [0, 7, 4],
    ZEHN_MIN: [1, 0, 4],
    ZWANZIG_MIN: [1, 4, 7],
    VIERTEL: [2, 4, 7],
    NACH: [3, 2, 4],
    VOR: [3, 6, 3],
    HALB: [4, 0, 4],
    UHR: [9, 8, 3],
  };
  // Hour 1 has two forms — see smart_display/watch_faces.py for the rule.
  const QLOCKTWO_HOUR_EIN = [5, 2, 3];   // "EIN" — only paired with UHR at the full hour.
  const QLOCKTWO_HOUR_WORDS = {
    1: [5, 2, 4],  // EINS — default for every non-"ein Uhr" context.
    2: [5, 0, 4],
    3: [6, 1, 4],
    4: [7, 7, 4],
    5: [6, 7, 4],
    6: [9, 1, 5],
    7: [5, 5, 6],
    8: [8, 1, 4],
    9: [7, 3, 4],
    10: [8, 5, 4],
    11: [7, 0, 3],
    12: [4, 5, 5],
  };
  const VALID_WATCH_FACES = ["classic", "qlocktwo", "analog"];
  const WATCH_FACE_LABELS = {
    classic: "Klassisch",
    qlocktwo: "Wortuhr",
    analog: "Analog",
  };
  const WATCH_FACE_STORAGE_KEY = "sd.watch_face";
  let qlocktwoLetterIndex = null;
  let lastQlocktwoKey = "";

  function qlocktwoHour12(hour24) {
    const h = ((hour24 % 12) + 12) % 12;
    return h === 0 ? 12 : h;
  }

  function qlocktwoActiveKeys(hour, minute) {
    const block = Math.floor(minute / 5) * 5;
    const thisHour = qlocktwoHour12(hour);
    const nextHour = qlocktwoHour12(hour + 1);
    const words = [QLOCKTWO_WORDS.ES, QLOCKTWO_WORDS.IST];
    switch (block) {
      case 0:
        words.push(thisHour === 1 ? QLOCKTWO_HOUR_EIN : QLOCKTWO_HOUR_WORDS[thisHour], QLOCKTWO_WORDS.UHR);
        break;
      case 5:
        words.push(QLOCKTWO_WORDS.FUENF_MIN, QLOCKTWO_WORDS.NACH, QLOCKTWO_HOUR_WORDS[thisHour]);
        break;
      case 10:
        words.push(QLOCKTWO_WORDS.ZEHN_MIN, QLOCKTWO_WORDS.NACH, QLOCKTWO_HOUR_WORDS[thisHour]);
        break;
      case 15:
        words.push(QLOCKTWO_WORDS.VIERTEL, QLOCKTWO_WORDS.NACH, QLOCKTWO_HOUR_WORDS[thisHour]);
        break;
      case 20:
        words.push(QLOCKTWO_WORDS.ZWANZIG_MIN, QLOCKTWO_WORDS.NACH, QLOCKTWO_HOUR_WORDS[thisHour]);
        break;
      case 25:
        words.push(
          QLOCKTWO_WORDS.FUENF_MIN,
          QLOCKTWO_WORDS.VOR,
          QLOCKTWO_WORDS.HALB,
          QLOCKTWO_HOUR_WORDS[nextHour],
        );
        break;
      case 30:
        words.push(QLOCKTWO_WORDS.HALB, QLOCKTWO_HOUR_WORDS[nextHour]);
        break;
      case 35:
        words.push(
          QLOCKTWO_WORDS.FUENF_MIN,
          QLOCKTWO_WORDS.NACH,
          QLOCKTWO_WORDS.HALB,
          QLOCKTWO_HOUR_WORDS[nextHour],
        );
        break;
      case 40:
        words.push(QLOCKTWO_WORDS.ZWANZIG_MIN, QLOCKTWO_WORDS.VOR, QLOCKTWO_HOUR_WORDS[nextHour]);
        break;
      case 45:
        words.push(QLOCKTWO_WORDS.VIERTEL, QLOCKTWO_WORDS.VOR, QLOCKTWO_HOUR_WORDS[nextHour]);
        break;
      case 50:
        words.push(QLOCKTWO_WORDS.ZEHN_MIN, QLOCKTWO_WORDS.VOR, QLOCKTWO_HOUR_WORDS[nextHour]);
        break;
      case 55:
        words.push(QLOCKTWO_WORDS.FUENF_MIN, QLOCKTWO_WORDS.VOR, QLOCKTWO_HOUR_WORDS[nextHour]);
        break;
      default:
        break;
    }
    const keys = new Set();
    for (const word of words) {
      const [row, col, length] = word;
      for (let i = 0; i < length; i += 1) {
        keys.add(`${row},${col + i}`);
      }
    }
    return keys;
  }

  function buildQlocktwoLetterIndex() {
    if (!nodes.qlocktwo) {
      return null;
    }
    const map = new Map();
    const letters = nodes.qlocktwo.querySelectorAll(".qlocktwo-letter");
    letters.forEach((letter) => {
      const row = letter.dataset.row;
      const col = letter.dataset.col;
      if (row !== undefined && col !== undefined) {
        map.set(`${row},${col}`, letter);
      }
    });
    return map;
  }

  function updateQlocktwo(force) {
    if (!nodes.qlocktwo) {
      return;
    }
    const now = new Date();
    // Resolve the timezone via the cached time formatter so the word clock
    // follows the same zone as the classic clock.
    const parts = CLOCK_TIME_FMT.formatToParts(now);
    let hour = now.getHours();
    let minute = now.getMinutes();
    for (const part of parts) {
      if (part.type === "hour") {
        hour = Number(part.value);
      } else if (part.type === "minute") {
        minute = Number(part.value);
      }
    }
    const block = Math.floor(minute / 5) * 5;
    const key = `${hour}:${block}`;
    if (!force && key === lastQlocktwoKey) {
      return;
    }
    lastQlocktwoKey = key;
    if (!qlocktwoLetterIndex) {
      qlocktwoLetterIndex = buildQlocktwoLetterIndex();
    }
    if (!qlocktwoLetterIndex) {
      return;
    }
    const activeKeys = qlocktwoActiveKeys(hour, minute);
    qlocktwoLetterIndex.forEach((letter, cellKey) => {
      const active = activeKeys.has(cellKey);
      if (active !== letter.classList.contains("is-active")) {
        letter.classList.toggle("is-active", active);
      }
    });
  }

  let lastAnalogKey = "";
  let analogSecondTimer = null;

  function updateAnalog(force) {
    if (!nodes.analogHour || !nodes.analogMinute || !nodes.analogSecond) {
      return;
    }
    const now = new Date();
    const parts = CLOCK_TIME_FMT.formatToParts(now);
    let hour = now.getHours();
    let minute = now.getMinutes();
    for (const part of parts) {
      if (part.type === "hour") {
        hour = Number(part.value);
      } else if (part.type === "minute") {
        minute = Number(part.value);
      }
    }
    // Seconds are the same across all timezones, so the native getter is
    // safe here (unlike hour/minute which must follow config.timezone).
    const secondDeg = ((now.getSeconds() * 6) % 360).toFixed(2);
    nodes.analogSecond.setAttribute("transform", `rotate(${secondDeg} 100 100)`);

    // Hour + minute only change on minute boundaries — cache to skip the
    // two setAttribute calls on the 1 Hz seconds tick.
    const key = `${hour}:${minute}`;
    if (!force && key === lastAnalogKey) {
      return;
    }
    lastAnalogKey = key;
    const hourDeg = (((hour % 12) * 30 + minute * 0.5) % 360).toFixed(2);
    const minuteDeg = ((minute * 6) % 360).toFixed(2);
    nodes.analogHour.setAttribute("transform", `rotate(${hourDeg} 100 100)`);
    nodes.analogMinute.setAttribute("transform", `rotate(${minuteDeg} 100 100)`);
  }

  function startAnalogSecondTick() {
    if (analogSecondTimer !== null) {
      return;
    }
    // Align the first tick to the next second boundary so the hand steps
    // in sync with real-world seconds rather than drifting off by up to 1 s.
    const msUntilNextSecond = 1000 - (Date.now() % 1000);
    analogSecondTimer = window.setTimeout(function tick() {
      updateAnalog(false);
      analogSecondTimer = window.setTimeout(tick, 1000);
    }, msUntilNextSecond + 10);
  }

  function stopAnalogSecondTick() {
    if (analogSecondTimer !== null) {
      window.clearTimeout(analogSecondTimer);
      analogSecondTimer = null;
    }
  }

  function currentWatchFace() {
    const stored = (() => {
      try {
        return window.localStorage && window.localStorage.getItem(WATCH_FACE_STORAGE_KEY);
      } catch (error) {
        return null;
      }
    })();
    if (stored && VALID_WATCH_FACES.includes(stored)) {
      return stored;
    }
    const configured = config.watch_face;
    if (configured && VALID_WATCH_FACES.includes(configured)) {
      return configured;
    }
    return "classic";
  }

  function applyWatchFace(face) {
    const next = VALID_WATCH_FACES.includes(face) ? face : "classic";
    document.body.setAttribute("data-watch-face", next);
    if (nodes.watchFace) {
      nodes.watchFace.setAttribute("aria-pressed", next === "qlocktwo" ? "true" : "false");
    }
    if (nodes.qlocktwo) {
      nodes.qlocktwo.setAttribute("aria-hidden", next === "qlocktwo" ? "false" : "true");
    }
    const analogWrap = document.getElementById("watch-face-analog");
    if (analogWrap) {
      analogWrap.setAttribute("aria-hidden", next === "analog" ? "false" : "true");
    }
    if (next === "qlocktwo") {
      updateQlocktwo(true);
      stopAnalogSecondTick();
    } else if (next === "analog") {
      updateAnalog(true);
      startAnalogSecondTick();
    } else {
      stopAnalogSecondTick();
    }
    return next;
  }

  function cycleWatchFace() {
    const current = document.body.getAttribute("data-watch-face") || "classic";
    const idx = VALID_WATCH_FACES.indexOf(current);
    const next = VALID_WATCH_FACES[(idx + 1) % VALID_WATCH_FACES.length];
    try {
      if (window.localStorage) {
        window.localStorage.setItem(WATCH_FACE_STORAGE_KEY, next);
      }
    } catch (error) {
      /* storage disabled — fall back to session-only switch */
    }
    applyWatchFace(next);
    showToast(`Uhrzeit-Stil: ${WATCH_FACE_LABELS[next] || next}`, "info", 1600);
  }

  const nodes = {
    time: document.getElementById("clock-time"),
    date: document.getElementById("clock-date"),
    watchFace: document.getElementById("watch-face"),
    qlocktwo: document.getElementById("watch-face-qlocktwo"),
    analogHour: document.getElementById("analog-hand-hour"),
    analogMinute: document.getElementById("analog-hand-minute"),
    analogSecond: document.getElementById("analog-hand-second"),
    weatherLocation: document.getElementById("weather-location"),
    weatherStatus: document.getElementById("weather-status"),
    weatherTemperature: document.getElementById("weather-temperature"),
    weatherIcon: document.getElementById("weather-icon"),
    weatherCondition: document.getElementById("weather-condition"),
    weatherSecondary: document.getElementById("weather-secondary"),
    weatherForecast: document.getElementById("weather-forecast"),
    calendarStatus: document.getElementById("calendar-status"),
    calendarList: document.getElementById("calendar-list"),
    spotifyStatus: document.getElementById("spotify-status"),
    spotifyCard: document.getElementById("spotify-card"),
    spotifyTrack: document.getElementById("spotify-track"),
    spotifyArtist: document.getElementById("spotify-artist"),
    spotifyDevice: document.getElementById("spotify-device"),
    spotifyDeviceBadge: document.getElementById("spotify-device-badge"),
    spotifyVolumeReadout: document.getElementById("spotify-volume-readout"),
    spotifyArtwork: document.getElementById("spotify-artwork"),
    spotifyPrevious: document.getElementById("spotify-previous"),
    spotifyPreviousIcon: document.getElementById("spotify-previous-icon"),
    spotifyToggle: document.getElementById("spotify-toggle"),
    spotifyToggleIcon: document.getElementById("spotify-toggle-icon"),
    spotifyNext: document.getElementById("spotify-next"),
    spotifyNextIcon: document.getElementById("spotify-next-icon"),
    spotifyVolume: document.getElementById("spotify-volume"),
    screensaver: document.getElementById("screensaver"),
    // Plan C1: two stacked image slots for crossfade. The active one is
    // visible; the inactive one holds the next image preloaded at opacity 0.
    screensaverImageA: document.getElementById("screensaver-image-a"),
    screensaverImageB: document.getElementById("screensaver-image-b"),
    screensaverFallback: document.getElementById("screensaver-fallback"),
    screensaverClock: document.getElementById("screensaver-clock"),
    toast: document.getElementById("toast"),
  };
  let volumeCommitTimer = null;
  // Volume-Slider Race-Guard (Plan A2). Snapshots arriving while the user is
  // mid-drag or within 1.5 s of the last touch must not snap the slider back.
  let volumeBusyUntil = 0;
  let volumeLastSent = null;
  const VOLUME_BUSY_MS = 1500;
  const VOLUME_TOLERANCE = 2;

  function markVolumeBusy() {
    volumeBusyUntil = performance.now() + VOLUME_BUSY_MS;
    if (nodes.spotifyVolume) {
      nodes.spotifyVolume.dataset.dirty = "1";
    }
  }

  let toastTimer = null;
  function showToast(message, kind = "error", ms = 4000) {
    const node = nodes.toast;
    if (!node || !message) {
      return;
    }
    window.clearTimeout(toastTimer);
    node.textContent = message;
    node.dataset.kind = kind;
    node.hidden = false;
    // Force reflow so the transition re-plays when replacing an existing toast.
    // eslint-disable-next-line no-unused-expressions
    node.offsetHeight;
    node.classList.add("is-visible");
    toastTimer = window.setTimeout(() => hideToast(), ms);
  }

  function hideToast() {
    const node = nodes.toast;
    if (!node) {
      return;
    }
    window.clearTimeout(toastTimer);
    node.classList.remove("is-visible");
    // Wait for the fade-out before hiding so the screen reader doesn't announce empty.
    window.setTimeout(() => {
      if (!node.classList.contains("is-visible")) {
        node.hidden = true;
      }
    }, 220);
  }

  const icons = {
    clear:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="16" cy="16" r="5"></circle><path d="M16 3v4M16 25v4M3 16h4M25 16h4M6.8 6.8l2.8 2.8M22.4 22.4l2.8 2.8M25.2 6.8l-2.8 2.8M9.6 22.4l-2.8 2.8"></path></svg>',
    "partly-cloudy":
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 12a6 6 0 1 1 11.3-3"></path><path d="M24 17a5 5 0 0 0-1-9.9"></path><path d="M9 25h13a5 5 0 0 0 0-10 7 7 0 0 0-13-1A5 5 0 0 0 9 25Z"></path></svg>',
    cloudy:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 25h14a5 5 0 1 0-.9-9.9A7 7 0 0 0 9 14a5 5 0 0 0 0 11Z"></path></svg>',
    fog:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 12h16"></path><path d="M5 17h22"></path><path d="M8 22h16"></path></svg>',
    rain:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 20h14a5 5 0 1 0-.9-9.9A7 7 0 0 0 9 9a5 5 0 0 0 0 11Z"></path><path d="M12 23l-1.5 3M17 23l-1.5 3M22 23l-1.5 3"></path></svg>',
    snow:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19h14a5 5 0 1 0-.9-9.9A7 7 0 0 0 9 8a5 5 0 0 0 0 11Z"></path><path d="M13 24h0M19 24h0"></path><path d="M13 21v6M10 24h6M11 22l4 4M15 22l-4 4"></path><path d="M19 21v6M16 24h6M17 22l4 4M21 22l-4 4"></path></svg>',
    storm:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19h14a5 5 0 1 0-.9-9.9A7 7 0 0 0 9 8a5 5 0 0 0 0 11Z"></path><path d="M16 20l-3 5h3l-2 4 5-7h-3l2-2"></path></svg>',
    previous:
      '<svg viewBox="0 0 32 32" fill="currentColor"><rect x="7" y="7" width="3" height="18" rx="1.2"></rect><path d="M23.5 8.5v15L11 16z"></path></svg>',
    next:
      '<svg viewBox="0 0 32 32" fill="currentColor"><rect x="22" y="7" width="3" height="18" rx="1.2"></rect><path d="M8.5 8.5v15L21 16z"></path></svg>',
    play:
      '<svg viewBox="0 0 32 32" fill="currentColor"><path d="M11 8.5v15l12-7.5z"></path></svg>',
    pause:
      '<svg viewBox="0 0 32 32" fill="currentColor"><rect x="10" y="8" width="4.5" height="16" rx="1.5"></rect><rect x="17.5" y="8" width="4.5" height="16" rx="1.5"></rect></svg>',
    device:
      '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="9" width="18" height="12" rx="2"></rect><path d="M12 25h8"></path></svg>',
  };

  function weatherIconName(conditionCode) {
    if (conditionCode === 0 || conditionCode === 1) {
      return "clear";
    }
    if (conditionCode === 2) {
      return "partly-cloudy";
    }
    if (conditionCode === 3) {
      return "cloudy";
    }
    if (conditionCode === 45 || conditionCode === 48) {
      return "fog";
    }
    if ([71, 73, 75, 77, 85, 86].includes(conditionCode)) {
      return "snow";
    }
    if ([95, 96, 99].includes(conditionCode)) {
      return "storm";
    }
    if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(conditionCode)) {
      return "rain";
    }
    return "cloudy";
  }

  function setIcon(node, iconName) {
    if (!node) {
      return;
    }
    node.innerHTML = icons[iconName] || "";
  }

  function updateClock() {
    const now = new Date();
    const timeValue = CLOCK_TIME_FMT.format(now);
    nodes.time.textContent = timeValue;
    nodes.date.textContent = CLOCK_DATE_FMT.format(now);
    nodes.screensaverClock.textContent = timeValue;
    updateQlocktwo(false);
    updateAnalog(false);
  }

  function scheduleClockTick() {
    // Re-arm for the next minute boundary + 500 ms safety margin so a slow
    // tick never lands in the previous minute. Clamp to at least 1 s to
    // avoid a runaway loop if the host clock misbehaves.
    const now = Date.now();
    const msUntilNextMinute = 60_000 - (now % 60_000);
    const delay = Math.max(1_000, msUntilNextMinute + 500);
    window.clearTimeout(clockTimer);
    clockTimer = window.setTimeout(() => {
      updateClock();
      scheduleClockTick();
    }, delay);
  }

  function setStatus(node, snapshot) {
    const status = snapshot && snapshot.status ? snapshot.status : "empty";
    const labels = {
      ok: "Live",
      stale: "Cache",
      error: "Fehler",
      empty: "Leer",
    };
    node.dataset.status = status;
    node.textContent = labels[status] || "Leer";
    node.classList.toggle("is-hidden", status === "ok");
    node.setAttribute("aria-hidden", status === "ok" ? "true" : "false");
  }

  function renderWeather(weather) {
    const snapshot = weather.snapshot || {};
    setStatus(nodes.weatherStatus, snapshot);
    nodes.weatherLocation.textContent = `Wetter ${weather.location_label || "Zuhause"}`;
    if (typeof weather.temperature_c === "number") {
      nodes.weatherTemperature.textContent = `${Math.round(weather.temperature_c)}°`;
    } else {
      nodes.weatherTemperature.textContent = "--";
    }
    setIcon(nodes.weatherIcon, weatherIconName(weather.condition_code));
    nodes.weatherCondition.textContent =
      weather.condition || snapshot.error_message || "Wetterdaten werden geladen.";

    if (typeof weather.apparent_temperature_c === "number") {
      nodes.weatherSecondary.textContent =
        `Gefühlt ${Math.round(weather.apparent_temperature_c)}°`;
    } else if (snapshot.error_message) {
      nodes.weatherSecondary.textContent = snapshot.error_message;
    } else {
      nodes.weatherSecondary.textContent = "";
    }

    nodes.weatherForecast.innerHTML = "";
    const forecastItems = Array.isArray(weather.forecast) ? weather.forecast.slice(0, 3) : [];
    nodes.weatherForecast.classList.toggle("is-empty", forecastItems.length === 0);

    forecastItems.forEach((item) => {
      const card = document.createElement("div");
      card.className = "forecast-chip";

      const top = document.createElement("div");
      top.className = "forecast-chip__top";

      const day = document.createElement("div");
      day.className = "forecast-chip__day";
      day.textContent = item.day_label || "Tag";

      const icon = document.createElement("div");
      icon.className = "forecast-chip__icon";
      setIcon(icon, weatherIconName(item.condition_code));

      const temp = document.createElement("div");
      temp.className = "forecast-chip__temp";
      const max = typeof item.temperature_max_c === "number" ? `${Math.round(item.temperature_max_c)}°` : "--";
      temp.textContent = max;

      if (typeof item.temperature_min_c === "number") {
        const min = document.createElement("span");
        min.className = "forecast-chip__temp-min";
        min.textContent = `${Math.round(item.temperature_min_c)}°`;
        temp.appendChild(min);
      }

      top.append(day, icon);
      card.append(top, temp);
      nodes.weatherForecast.appendChild(card);
    });
  }

  function createCalendarRow(item) {
    const row = document.createElement("li");
    row.className = "calendar-item";

    const time = document.createElement("div");
    time.className = "calendar-item__time";
    time.textContent = item.time_label;

    const title = document.createElement("div");
    title.className = "calendar-item__title";
    title.textContent = item.title;

    row.append(time, title);
    return row;
  }

  function createCalendarSectionLabel(label) {
    const sectionLabel = document.createElement("li");
    sectionLabel.className = "calendar-section-label";
    sectionLabel.textContent = label;
    return sectionLabel;
  }

  function todayIsoInZone() {
    // en-CA locale gives us YYYY-MM-DD directly, honoring the configured timezone.
    return SECTION_DATE_FMT.format(new Date());
  }

  function computeDayLabel(sectionDateIso, todayIso) {
    if (!sectionDateIso) {
      return "";
    }
    const sectionParts = sectionDateIso.split("-").map((part) => Number(part));
    const todayParts = todayIso.split("-").map((part) => Number(part));
    if (sectionParts.length !== 3 || todayParts.length !== 3) {
      return "";
    }
    const sectionDate = Date.UTC(sectionParts[0], sectionParts[1] - 1, sectionParts[2]);
    const today = Date.UTC(todayParts[0], todayParts[1] - 1, todayParts[2]);
    const diffDays = Math.round((sectionDate - today) / 86_400_000);
    if (diffDays === 0) {
      return "Heute";
    }
    if (diffDays === 1) {
      return "Morgen";
    }
    if (diffDays === 2) {
      return "Übermorgen";
    }
    // Fall through to weekday name — covers future days > 2 and stale/offline past dates.
    // Use UTC noon so the Intl formatter lands on the right weekday regardless of TZ.
    const display = new Date(sectionDate + 12 * 3_600_000);
    const label = WEEKDAY_FMT.format(display);
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  // Plan B8: after the A3 backend rewrite the server always emits
  // ``sections`` with a ``section_date``. The old flat-items fallback is
  // gone — a malformed payload yields an empty calendar + a one-shot
  // warning instead of silently labelling everything as "Heute".
  let calendarMissingSectionsWarned = false;

  function normalizeCalendarSections(calendar) {
    if (!calendar || !Array.isArray(calendar.sections)) {
      if (!calendarMissingSectionsWarned) {
        calendarMissingSectionsWarned = true;
        window.console.warn(
          "calendar payload missing 'sections' array — ignoring",
        );
      }
      return [];
    }
    return calendar.sections
      .filter(
        (section) =>
          section &&
          Array.isArray(section.items) &&
          section.items.length > 0 &&
          typeof section.section_date === "string" &&
          section.section_date.length > 0,
      )
      .map((section) => ({
        day_key: section.day_key || "",
        section_date: section.section_date,
        items: section.items,
      }));
  }

  // Plan B7: port of smart_display/calendar_layout.compute_row_budget.
  // Keep in sync — Python is the source of truth, JS is a 1:1 mirror.
  function computeRowBudget(sectionItemCounts, maxRows, sectionHasLabel) {
    const n = sectionItemCounts.length;
    if (n === 0 || maxRows <= 0) {
      return new Array(n).fill(0);
    }
    const allocated = sectionItemCounts.map((c) => Math.max(0, c | 0));
    const totalRows = () => {
      let total = 0;
      for (let i = 0; i < n; i += 1) {
        if (allocated[i] > 0) {
          total += allocated[i];
          if (sectionHasLabel[i]) {
            total += 1;
          }
        }
      }
      return total;
    };
    let guard = allocated.reduce((a, b) => a + b, 0) + 1;
    while (totalRows() > maxRows && guard > 0) {
      guard -= 1;
      let largestIdx = -1;
      let largestValue = 0;
      for (let i = 0; i < n; i += 1) {
        if (allocated[i] > largestValue) {
          largestValue = allocated[i];
          largestIdx = i;
        }
      }
      if (largestIdx < 0) {
        break;
      }
      allocated[largestIdx] -= 1;
    }
    return allocated;
  }

  let calendarZeroHeightWarned = false;

  function renderCalendar(calendar) {
    const snapshot = calendar.snapshot || {};
    const sections = normalizeCalendarSections(calendar);
    const todayIso = todayIsoInZone();
    setStatus(nodes.calendarStatus, snapshot);
    nodes.calendarList.innerHTML = "";

    if (sections.length === 0) {
      const empty = document.createElement("li");
      empty.className = "calendar-empty";
      empty.textContent =
        snapshot.error_message ||
        calendar.empty_message ||
        "Keine Termine in den nächsten Tagen.";
      nodes.calendarList.appendChild(empty);
      return;
    }

    // Pre-compute per-section metadata in render order.
    const labels = sections.map((section) =>
      computeDayLabel(section.section_date, todayIso),
    );
    const sectionHasLabel = labels.map(
      (label) => label.length > 0 && label !== "Heute",
    );
    const sectionItemCounts = sections.map((section) => section.items.length);

    const availableHeight = nodes.calendarList.clientHeight;
    let allocated;
    if (availableHeight <= 0) {
      // Plan B7: if the list hasn't been laid out yet we can't measure,
      // so render everything instead of silently trimming. Warn once so
      // the issue shows up in diagnostic logs on the Pi without spamming.
      if (!calendarZeroHeightWarned) {
        calendarZeroHeightWarned = true;
        window.console.warn(
          "calendar list has clientHeight=0; rendering without row budget",
        );
      }
      allocated = sectionItemCounts.slice();
    } else {
      // Measure one representative row + one label against the live DOM
      // so we pick up the actual CSS dimensions instead of hard-coding
      // magic numbers that drift when the theme changes.
      const measureRow = createCalendarRow({
        title: "Messung",
        time_label: "",
      });
      const measureLabel = createCalendarSectionLabel("Messung");
      nodes.calendarList.appendChild(measureRow);
      nodes.calendarList.appendChild(measureLabel);
      const rowHeight = measureRow.offsetHeight || 1;
      const labelHeight = measureLabel.offsetHeight || rowHeight;
      nodes.calendarList.removeChild(measureRow);
      nodes.calendarList.removeChild(measureLabel);

      // Use the taller of the two as the uniform row unit so we never
      // overshoot. With typical CSS the label is slightly larger.
      const rowUnit = Math.max(rowHeight, labelHeight);
      const maxRows = Math.max(1, Math.floor(availableHeight / rowUnit));
      allocated = computeRowBudget(sectionItemCounts, maxRows, sectionHasLabel);
    }

    // Build everything into a fragment, append once — a single layout
    // pass instead of one per appended row.
    const fragment = document.createDocumentFragment();
    let visibleRows = 0;
    for (let i = 0; i < sections.length; i += 1) {
      const count = allocated[i];
      if (count <= 0) {
        continue;
      }
      if (sectionHasLabel[i]) {
        fragment.appendChild(createCalendarSectionLabel(labels[i]));
      }
      const items = sections[i].items.slice(0, count);
      for (const item of items) {
        fragment.appendChild(createCalendarRow(item));
        visibleRows += 1;
      }
    }
    nodes.calendarList.appendChild(fragment);

    if (visibleRows === 0) {
      const empty = document.createElement("li");
      empty.className = "calendar-empty";
      empty.textContent =
        snapshot.error_message ||
        calendar.empty_message ||
        "Keine Termine in den nächsten Tagen.";
      nodes.calendarList.innerHTML = "";
      nodes.calendarList.appendChild(empty);
    }
  }

  function renderSpotify(spotify) {
    const snapshot = spotify.snapshot || {};
    const showControls = Boolean(spotify.can_control || spotify.supports_volume);
    setStatus(nodes.spotifyStatus, snapshot);
    nodes.spotifyCard.classList.toggle("is-inactive", !showControls);
    setIcon(nodes.spotifyPreviousIcon, "previous");
    setIcon(nodes.spotifyNextIcon, "next");
    setIcon(nodes.spotifyToggleIcon, spotify.is_playing ? "pause" : "play");
    nodes.spotifyToggle.setAttribute(
      "aria-label",
      spotify.is_playing ? "Wiedergabe pausieren" : "Wiedergabe starten",
    );
    nodes.spotifyTrack.textContent =
      spotify.track_title || spotify.empty_message || "Keine aktive Wiedergabe";
    nodes.spotifyArtist.textContent =
      spotify.artist_name || snapshot.error_message || "Spotify nicht verbunden.";
    setIcon(nodes.spotifyDeviceBadge.querySelector(".spotify-device-badge__icon"), "device");
    const deviceLabel = [spotify.device_name, spotify.device_type]
      .filter(Boolean)
      .join(" · ");
    nodes.spotifyDevice.textContent = deviceLabel || "Kein aktives Gerät";
    nodes.spotifyVolumeReadout.textContent =
      typeof spotify.volume_percent === "number" ? `${spotify.volume_percent}%` : "";

    if (spotify.album_art_url) {
      nodes.spotifyArtwork.style.backgroundImage = `url("${spotify.album_art_url}")`;
    } else {
      nodes.spotifyArtwork.style.backgroundImage = "";
    }

    const disabled = !spotify.can_control;
    nodes.spotifyPrevious.disabled = disabled;
    nodes.spotifyToggle.disabled = disabled;
    nodes.spotifyNext.disabled = disabled;
    nodes.spotifyVolume.disabled = !spotify.supports_volume;

    // Plan A2: don't snap the slider back while the user is mid-drag or while
    // the last user-sent value is still in flight. Spotify rounds volumes to
    // the nearest step, so we accept a ±VOLUME_TOLERANCE reconciliation.
    const slider = nodes.spotifyVolume;
    const now = performance.now();
    const incoming = typeof spotify.volume_percent === "number" ? spotify.volume_percent : null;
    const busy = volumeBusyUntil > now;
    const dirty = slider.dataset.dirty === "1";

    if (incoming === null) {
      if (!dirty && !busy && !slider.matches(":active")) {
        slider.value = "0";
        nodes.spotifyVolumeReadout.textContent = "";
      }
      return;
    }

    if (busy) {
      return;
    }

    if (dirty) {
      if (volumeLastSent !== null && Math.abs(incoming - volumeLastSent) <= VOLUME_TOLERANCE) {
        delete slider.dataset.dirty;
        volumeLastSent = null;
        slider.value = String(incoming);
        nodes.spotifyVolumeReadout.textContent = `${incoming}%`;
      }
      return;
    }

    slider.value = String(incoming);
    nodes.spotifyVolumeReadout.textContent = `${incoming}%`;
  }

  function render(nextState) {
    state = nextState || state;
    renderWeather(state.weather || {});
    renderSpotify(state.spotify || {});
    renderCalendar(state.calendar || {});
  }

  function scheduleMidnightRerender() {
    window.clearTimeout(midnightTimer);
    const now = new Date();
    const nextMidnight = new Date(now);
    nextMidnight.setHours(24, 0, 2, 0); // 2s slack so we land safely past the boundary
    const delayMs = Math.max(nextMidnight.getTime() - now.getTime(), 1000);
    midnightTimer = window.setTimeout(() => {
      render(state);
      scheduleMidnightRerender();
    }, delayMs);
  }

  async function fetchState() {
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      render(payload);
    } catch (error) {
      window.console.debug("state refresh failed", error);
    }
  }

  function schedulePolling() {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(async function poll() {
      if (!screensaverActive) {
        await fetchState();
      }
      schedulePolling();
    }, Math.max((config.poll_interval_seconds || 15) * 1000, 5000));
  }

  async function postAction(endpoint) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body || body.ok === false) {
        return { ok: false, message: (body && body.message) || "Netzwerkfehler.", state: null };
      }
      return { ok: true, message: body.message || "ok", state: body.state || null };
    } catch (error) {
      return { ok: false, message: "Netzwerkfehler.", state: null };
    }
  }

  async function postJson(endpoint, payload) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body || body.ok === false) {
        return { ok: false, message: (body && body.message) || "Netzwerkfehler.", state: null };
      }
      return { ok: true, message: body.message || "ok", state: body.state || null };
    } catch (error) {
      return { ok: false, message: "Netzwerkfehler.", state: null };
    }
  }

  function applySpotifyState(spotifyState) {
    if (!spotifyState) {
      return;
    }
    state = { ...state, spotify: spotifyState };
    renderSpotify(spotifyState);
  }

  // Plan C1: crossfade state. ``activeSlot`` is the <img> currently visible;
  // the next fetch writes into the hidden slot, waits for its ``load`` event,
  // then toggles the ``is-active`` class to trigger the CSS opacity swap.
  // We intentionally do NOT preload "the next next image" because
  // /api/screensaver/next returns a *random* manifest entry on every call,
  // so a speculative pre-fetch rarely matches what the next advance picks.
  let activeScreensaverSlot = null;

  async function fetchNextScreensaverImage() {
    try {
      const response = await fetch("/api/screensaver/next", { cache: "no-store" });
      if (!response.ok) {
        return null;
      }
      const payload = await response.json();
      return payload && payload.image ? payload.image : null;
    } catch (error) {
      window.console.debug("screensaver image fetch failed", error);
      return null;
    }
  }

  function loadImageInSlot(slot, src) {
    return new Promise((resolve) => {
      const onLoad = () => {
        slot.removeEventListener("load", onLoad);
        slot.removeEventListener("error", onError);
        resolve(true);
      };
      const onError = () => {
        slot.removeEventListener("load", onLoad);
        slot.removeEventListener("error", onError);
        resolve(false);
      };
      slot.addEventListener("load", onLoad);
      slot.addEventListener("error", onError);
      slot.src = src;
    });
  }

  async function loadScreensaverImage() {
    const image = await fetchNextScreensaverImage();
    if (!image) {
      showScreensaverFallback();
      return;
    }
    if (!activeScreensaverSlot) {
      activeScreensaverSlot = nodes.screensaverImageA;
    }
    const nextSlot =
      activeScreensaverSlot === nodes.screensaverImageA
        ? nodes.screensaverImageB
        : nodes.screensaverImageA;

    const loaded = await loadImageInSlot(nextSlot, image.public_path);
    if (!loaded) {
      // Leave the current slot visible; a failure must not blank the panel.
      return;
    }

    // Swap visibility: activate the freshly loaded slot and retire the old
    // one. CSS handles the 1.2 s crossfade.
    nextSlot.classList.add("is-active");
    activeScreensaverSlot.classList.remove("is-active");
    activeScreensaverSlot = nextSlot;
    nodes.screensaverFallback.style.display = "none";
  }

  function showScreensaverFallback() {
    [nodes.screensaverImageA, nodes.screensaverImageB].forEach((slot) => {
      slot.removeAttribute("src");
      slot.classList.remove("is-active");
    });
    activeScreensaverSlot = null;
    nodes.screensaverFallback.style.display = "flex";
  }

  function notifyScreensaverState(active) {
    // Plan B1: tell the backend so it can pause/resume the Spotify poll
    // group. Fire-and-forget — a failure here must not keep the screensaver
    // from showing.
    try {
      fetch("/api/screensaver/state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: Boolean(active) }),
        keepalive: true,
      }).catch(() => {});
    } catch (error) {
      /* ignore */
    }
  }

  function enterScreensaver() {
    if (screensaverActive) {
      return;
    }
    screensaverActive = true;
    nodes.screensaver.classList.add("is-active");
    loadScreensaverImage();
    window.clearInterval(slideshowTimer);
    slideshowTimer = window.setInterval(
      loadScreensaverImage,
      Math.max((config.image_duration_seconds || 15) * 1000, 5000),
    );
    notifyScreensaverState(true);
    window.clearInterval(screensaverHeartbeatTimer);
    screensaverHeartbeatTimer = window.setInterval(
      () => notifyScreensaverState(true),
      SCREENSAVER_HEARTBEAT_MS,
    );
  }

  function exitScreensaver() {
    if (!screensaverActive) {
      return;
    }
    screensaverActive = false;
    nodes.screensaver.classList.remove("is-active");
    window.clearInterval(slideshowTimer);
    window.clearInterval(screensaverHeartbeatTimer);
    screensaverHeartbeatTimer = null;
    resetIdleTimer();
    notifyScreensaverState(false);
    fetchState();
  }

  function resetIdleTimer() {
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(
      enterScreensaver,
      Math.max((config.idle_timeout_seconds || 120) * 1000, 5000),
    );
  }

  function handleActivity() {
    if (screensaverActive) {
      exitScreensaver();
      return;
    }
    resetIdleTimer();
  }

  function bindEvents() {
    // Plan B6: pointermove fired on every pixel of cursor motion during
    // debug sessions and on the kiosk itself whenever a touch was dragged,
    // which was pure CPU noise — pointerdown/touchstart already cover real
    // interaction.
    ["pointerdown", "touchstart", "keydown"].forEach((eventName) => {
      window.addEventListener(eventName, handleActivity, { passive: true });
    });

    nodes.screensaver.addEventListener("pointerdown", exitScreensaver, { passive: true });

    if (nodes.watchFace) {
      nodes.watchFace.addEventListener("click", (event) => {
        // If the tap was consumed by the screensaver-exit path, the
        // screensaver is still marked active briefly — skip cycling then.
        if (screensaverActive) {
          return;
        }
        event.preventDefault();
        cycleWatchFace();
      });
    }

    if (nodes.toast) {
      nodes.toast.addEventListener("pointerdown", hideToast, { passive: true });
    }

    nodes.spotifyToggle.addEventListener("click", async () => {
      const currentSpotify = state.spotify || {};
      const previousIsPlaying = Boolean(currentSpotify.is_playing);
      // Optimistic flip so the button feels alive on touch.
      applySpotifyState({ ...currentSpotify, is_playing: !previousIsPlaying });
      const result = await postAction("/api/spotify/toggle");
      if (result.ok && result.state) {
        applySpotifyState(result.state);
      } else if (result.ok === false) {
        applySpotifyState({ ...currentSpotify, is_playing: previousIsPlaying });
        showToast(result.message || "Spotify nicht erreichbar.");
      }
    });

    nodes.spotifyNext.addEventListener("click", async () => {
      const result = await postAction("/api/spotify/next");
      if (result.ok && result.state) {
        applySpotifyState(result.state);
      } else if (result.ok === false) {
        showToast(result.message || "Spotify nicht erreichbar.");
      }
    });

    nodes.spotifyPrevious.addEventListener("click", async () => {
      const result = await postAction("/api/spotify/previous");
      if (result.ok && result.state) {
        applySpotifyState(result.state);
      } else if (result.ok === false) {
        showToast(result.message || "Spotify nicht erreichbar.");
      }
    });

    nodes.spotifyVolume.addEventListener("pointerdown", markVolumeBusy, { passive: true });
    nodes.spotifyVolume.addEventListener("touchstart", markVolumeBusy, { passive: true });
    nodes.spotifyVolume.addEventListener("input", () => {
      markVolumeBusy();
      nodes.spotifyVolumeReadout.textContent = `${nodes.spotifyVolume.value}%`;
    });
    nodes.spotifyVolume.addEventListener("change", () => {
      window.clearTimeout(volumeCommitTimer);
      const targetValue = Number(nodes.spotifyVolume.value);
      volumeLastSent = targetValue;
      markVolumeBusy();
      volumeCommitTimer = window.setTimeout(async () => {
        const result = await postJson("/api/spotify/volume", {
          volume_percent: targetValue,
        });
        if (result.ok && result.state) {
          applySpotifyState(result.state);
        } else if (result.ok === false) {
          // Command failed — release the dirty lock so future snapshots render.
          delete nodes.spotifyVolume.dataset.dirty;
          volumeLastSent = null;
          showToast(result.message || "Spotify nicht erreichbar.");
        }
      }, 120);
    });
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => render(state), 80);
    });
  }

  applyWatchFace(currentWatchFace());
  bindEvents();
  updateClock();
  render(state);
  schedulePolling();
  scheduleMidnightRerender();
  resetIdleTimer();
  scheduleClockTick();
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => render(state));
  }
})();
