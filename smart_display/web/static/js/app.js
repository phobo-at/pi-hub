(function bootstrap() {
  const boot = window.__SMART_DISPLAY__ || {};
  const config = boot.config || {};
  let state = boot.state || {};
  let screensaverActive = false;
  let idleTimer = null;
  let pollTimer = null;
  let slideshowTimer = null;
  let resizeTimer = null;

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
    screensaverImage: document.getElementById("screensaver-image"),
    screensaverFallback: document.getElementById("screensaver-fallback"),
    screensaverClock: document.getElementById("screensaver-clock"),
  };
  let volumeCommitTimer = null;

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
    const timezone = config.timezone || "Europe/Vienna";
    const locale = config.locale || "de-AT";
    const timeFormatter = new Intl.DateTimeFormat(config.locale || "de-AT", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timezone,
    });
    const dateFormatter = new Intl.DateTimeFormat(config.locale || "de-AT", {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone: timezone,
    });
    const timezoneFormatter = new Intl.DateTimeFormat(locale, {
      timeZone: timezone,
      timeZoneName: "longGeneric",
    });
    const timeValue = timeFormatter.format(now);
    nodes.time.textContent = timeValue;
    nodes.date.textContent = dateFormatter.format(now);
    nodes.screensaverClock.textContent = timeValue;
    const timezoneName =
      timezoneFormatter.formatToParts(now).find((part) => part.type === "timeZoneName")
        ?.value || timezone;
    nodes.heroLocale.textContent = timezoneName;
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

  function normalizeCalendarSections(calendar) {
    const sections = Array.isArray(calendar.sections) ? calendar.sections : [];
    const normalized = sections
      .filter((section) => Array.isArray(section.items) && section.items.length > 0)
      .map((section) => ({
        day_key: section.day_key || "",
        day_label: section.day_label || "",
        items: section.items,
      }));

    if (normalized.length > 0) {
      return normalized;
    }

    if (Array.isArray(calendar.items) && calendar.items.length > 0) {
      return [{ day_key: "today", day_label: "Heute", items: calendar.items }];
    }

    return [];
  }

  function renderCalendar(calendar) {
    const snapshot = calendar.snapshot || {};
    const sections = normalizeCalendarSections(calendar);
    const availableHeight = nodes.calendarList.clientHeight;
    const canMeasure = availableHeight > 0;
    let visibleRows = 0;
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

    outer: for (const section of sections) {
      const needsLabel = section.day_key !== "today";
      let labelNode = null;
      let sectionHasVisibleItems = false;

      if (needsLabel) {
        labelNode = createCalendarSectionLabel(section.day_label);
        nodes.calendarList.appendChild(labelNode);
      }

      for (const item of section.items) {
        const row = createCalendarRow(item);
        nodes.calendarList.appendChild(row);

        if (canMeasure && nodes.calendarList.scrollHeight > availableHeight + 2) {
          row.remove();
          if (!sectionHasVisibleItems && labelNode) {
            labelNode.remove();
          }
          break outer;
        }

        sectionHasVisibleItems = true;
        visibleRows += 1;
      }

      if (labelNode && !sectionHasVisibleItems) {
        labelNode.remove();
      }
    }

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
    if (typeof spotify.volume_percent === "number") {
      nodes.spotifyVolume.value = String(spotify.volume_percent);
    } else if (!nodes.spotifyVolume.matches(":active")) {
      nodes.spotifyVolume.value = "0";
    }
  }

  function render(nextState) {
    state = nextState || state;
    renderWeather(state.weather || {});
    renderSpotify(state.spotify || {});
    renderCalendar(state.calendar || {});
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
      await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      await fetchState();
    } catch (error) {
      window.console.debug("spotify action failed", error);
    }
  }

  async function postJson(endpoint, payload) {
    try {
      await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await fetchState();
    } catch (error) {
      window.console.debug("spotify json action failed", error);
    }
  }

  async function loadScreensaverImage() {
    try {
      const response = await fetch("/api/screensaver/next", { cache: "no-store" });
      if (!response.ok) {
        showScreensaverFallback();
        return;
      }
      const payload = await response.json();
      if (!payload.image) {
        showScreensaverFallback();
        return;
      }
      nodes.screensaverImage.src = payload.image.public_path;
      nodes.screensaverImage.style.display = "block";
      nodes.screensaverFallback.style.display = "none";
    } catch (error) {
      window.console.debug("screensaver image failed", error);
      showScreensaverFallback();
    }
  }

  function showScreensaverFallback() {
    nodes.screensaverImage.removeAttribute("src");
    nodes.screensaverImage.style.display = "none";
    nodes.screensaverFallback.style.display = "flex";
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
  }

  function exitScreensaver() {
    if (!screensaverActive) {
      return;
    }
    screensaverActive = false;
    nodes.screensaver.classList.remove("is-active");
    window.clearInterval(slideshowTimer);
    resetIdleTimer();
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
    ["pointerdown", "pointermove", "touchstart", "keydown"].forEach((eventName) => {
      window.addEventListener(eventName, handleActivity, { passive: true });
    });

    nodes.screensaver.addEventListener("pointerdown", exitScreensaver, { passive: true });
    nodes.spotifyPrevious.addEventListener("click", () => postAction("/api/spotify/previous"));
    nodes.spotifyToggle.addEventListener("click", () => postAction("/api/spotify/toggle"));
    nodes.spotifyNext.addEventListener("click", () => postAction("/api/spotify/next"));
    nodes.spotifyVolume.addEventListener("input", () => {
      nodes.spotifyVolumeReadout.textContent = `${nodes.spotifyVolume.value}%`;
    });
    nodes.spotifyVolume.addEventListener("change", () => {
      window.clearTimeout(volumeCommitTimer);
      volumeCommitTimer = window.setTimeout(() => {
        postJson("/api/spotify/volume", {
          volume_percent: Number(nodes.spotifyVolume.value),
        });
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
  resetIdleTimer();
  window.setInterval(updateClock, 1000);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => render(state));
  }
})();
