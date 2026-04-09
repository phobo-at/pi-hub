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
  const CLOCK_TZ_FMT = new Intl.DateTimeFormat(LOCALE, {
    timeZone: TIMEZONE,
    timeZoneName: "longGeneric",
  });
  let clockTimer = null;

  const nodes = {
    time: document.getElementById("clock-time"),
    date: document.getElementById("clock-date"),
    heroLocale: document.getElementById("hero-locale"),
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
    const timezoneName =
      CLOCK_TZ_FMT.formatToParts(now).find((part) => part.type === "timeZoneName")
        ?.value || TIMEZONE;
    nodes.heroLocale.textContent = timezoneName;
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
