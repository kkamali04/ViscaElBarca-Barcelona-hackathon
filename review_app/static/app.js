"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const colors = { H: "#d9609e", A: "#6596dd", D: "#aeb9b8", X: "#e4c276" };
  const video = $("match-video");
  const seek = $("timeline-seek");
  const canvas = $("timeline-canvas");
  let state = null;
  let segments = [];
  let fps = 25;
  let frames = 0;
  let currentFrame = 0;
  let timelineKey = null;
  let timelineRequest = 0;
  let pollTimer = null;
  let stateRequest = null;
  let runRequest = false;
  let exportRequest = false;
  let demoPlaying = false;
  let demoPosition = 0;
  let demoLastTick = null;
  let animationId = null;
  let playbackSpeed = 1;
  let mediaSourceSet = false;
  let mediaFailed = false;
  let lastAnnouncedStatus = null;

  const number = (value, fallback = 0) => typeof value === "number" && Number.isFinite(value) ? value : fallback;
  const integer = (value, fallback = 0) => Math.max(0, Math.floor(number(value, fallback)));
  const formatNumber = (value) => integer(value).toLocaleString("en-US");
  const setText = (id, value) => { $(id).textContent = String(value); };
  const clock = (seconds, full = true) => {
    const whole = Math.max(0, Math.floor(number(seconds)));
    const hours = Math.floor(whole / 3600);
    const minutes = Math.floor((whole % 3600) / 60);
    const secondsPart = whole % 60;
    return full || hours > 0
      ? [hours, minutes, secondsPart].map((part) => String(part).padStart(2, "0")).join(":")
      : [minutes, secondsPart].map((part) => String(part).padStart(2, "0")).join(":");
  };
  const durationText = (count) => {
    const seconds = integer(count) / fps;
    return clock(seconds, seconds >= 3600);
  };
  const isRunning = () => state && state.run && state.run.status === "running";
  const hasOutput = () => Boolean(state && state.output && state.output.present && state.output.valid);
  const hasTimeline = () => segments.length > 0 && frames > 0;
  const labelDescription = (label) => {
    if (label === "H") return state.match.home || "Home possession";
    if (label === "A") return state.match.away || "Away possession";
    if (label === "D") return "Dead ball / play stopped";
    if (label === "X") return "No answer / outside play";
    return "No prediction available";
  };

  function enableLink(id, enabled) {
    const link = $(id);
    link.classList.toggle("disabled", !enabled);
    link.setAttribute("aria-disabled", String(!enabled));
    if (enabled) link.removeAttribute("tabindex");
    else link.setAttribute("tabindex", "-1");
  }

  function notice(message, error = false) {
    const box = $("connection-notice");
    box.textContent = message;
    box.hidden = !message;
    box.classList.toggle("is-error", error);
  }

  async function requestJSON(path, options = {}) {
    let response;
    try {
      response = await fetch(path, { cache: "no-store", credentials: "same-origin", ...options });
    } catch (_) {
      throw new Error("The local review service could not be reached. Keep the review server running and try again.");
    }
    let body;
    try { body = await response.json(); }
    catch (_) { throw new Error("The local review service returned an unreadable response."); }
    if (!response.ok) {
      const message = body && typeof body.error === "string" ? body.error : `Request failed (${response.status}).`;
      throw new Error(message);
    }
    return body;
  }

  function postOptions(body) {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Review-Token": state.request_token },
      body: JSON.stringify(body)
    };
  }

  function renderMedia() {
    const demo = state.mode === "demo";
    const ready = !demo && Boolean(state.inputs.video_ready) && !mediaFailed;
    $("synthetic-stage").hidden = !demo;
    video.hidden = !ready;
    $("stage-empty").hidden = demo || ready;
    $("stage-topline").hidden = !demo && !ready;
    setText("stage-source", demo ? "SYNTHETIC DEMO" : "LOCAL VIDEO");
    if (ready && !mediaSourceSet) {
      mediaSourceSet = true;
      video.src = "/media/tactical.mp4";
      video.load();
    }
    if (!ready && mediaSourceSet) {
      video.pause();
      video.removeAttribute("src");
      video.load();
      mediaSourceSet = false;
    }
    if (!demo && !ready) {
      setText("stage-empty-title", mediaFailed ? "The tactical video could not be played" : "Tactical video unavailable");
      setText("stage-empty-description", mediaFailed
        ? "The prediction timeline is still available. Check the local video file and browser playback support."
        : "The prediction timeline can be reviewed when ready. Add the tactical video locally to synchronize playback.");
    }
    $("play-toggle").disabled = !(demo ? hasTimeline() : ready);
    $("fullscreen-toggle").disabled = !(demo || ready);
    $("playback-speed").disabled = !(demo || ready);
  }

  function renderRatios() {
    const output = state.output || {};
    const counts = output.counts || {};
    const live = output.live_possession || {};
    const valid = Boolean(output.present && output.valid);
    const home = Math.min(100, Math.max(0, number(live.H)));
    const away = Math.min(100, Math.max(0, number(live.A)));
    const putRatio = (id, value) => {
      $(id).replaceChildren(document.createTextNode(valid ? value.toFixed(1) : "—"));
      const unit = document.createElement("small");
      unit.textContent = "%";
      $(id).append(unit);
    };
    putRatio("home-possession", home);
    putRatio("away-possession", away);
    $("home-share").style.width = valid ? `${home}%` : "0%";
    $("away-share").style.width = valid ? `${away}%` : "0%";
    $("home-share").parentElement.setAttribute("aria-label", valid
      ? `Live-play possession: ${state.match.home} ${home.toFixed(1)} percent, ${state.match.away} ${away.toFixed(1)} percent. Dead ball and no-answer frames excluded.`
      : "Live-play possession is not available.");
    setText("dead-time", valid ? durationText(counts.D) : "—");
    setText("unknown-time", valid ? durationText(counts.X) : "—");
    setText("frame-coverage", valid ? `${formatNumber(output.frames)} / ${formatNumber(frames)}` : "—");
    setText("output-status", valid ? (state.mode === "demo" ? "Sample data" : "CSV valid") : output.present ? "Needs review" : "No CSV yet");
    $("output-status").classList.toggle("is-warning", !valid || state.mode === "demo");
  }

  function renderRun() {
    const run = state.run || {};
    const status = run.status || "idle";
    const running = status === "running" || runRequest;
    const valid = hasOutput();
    const ready = Boolean(state.inputs.tracking_ready);
    const titles = {
      idle: valid ? "Candidate ready to review" : ready ? "Ready to generate predictions" : "Tracking input missing",
      running: "Generating predictions",
      complete: valid ? "Prediction CSV generated" : "Generation finished — review required",
      failed: "Generation did not complete"
    };
    $("run-state").className = `run-state is-${status}`;
    setText("run-title", runRequest && status !== "running" ? "Starting local generation" : titles[status] || "Checking generation status");
    const defaultMessage = ready ? "The candidate runs locally on the tracking input." : "Add the required tracking input to enable generation.";
    setText("run-message", status === "failed" && run.error ? run.error : run.message || defaultMessage);
    setText("run-elapsed", running || status === "complete" ? `${number(run.elapsed_seconds).toFixed(1)}s` : "");
    $("regenerate").disabled = running || !ready || !state.request_token;
    setText("regenerate-label", running ? "Generating…" : "Regenerate CSV");
    enableLink("download-csv", valid && !running);
    enableLink("download-code", Boolean(state.code_export_ready) && !running);
    $("prepare-pack").disabled = !valid || running || exportRequest || !state.request_token;
    $("prepare-pack").firstChild.textContent = exportRequest ? "Preparing pack… " : "Prepare review pack ";
    const output = state.output || {};
    if (valid) {
      const fingerprint = typeof output.sha256 === "string" ? output.sha256.slice(0, 16) : "unavailable";
      setText("artifact-note", `${state.mode === "demo" ? "Synthetic CSV" : "CSV"} · ${formatNumber(output.frames)} frames · SHA-256 ${fingerprint}${fingerprint !== "unavailable" ? "…" : ""}`);
    } else {
      setText("artifact-note", output.present ? "The available CSV has not passed the local frame and label contract." : "Prediction integrity and runtime appear after generation.");
    }
    if (status !== lastAnnouncedStatus) {
      lastAnnouncedStatus = status;
      setText("announcement", titles[status] || "Generation status updated.");
    }
  }

  function renderEvidence() {
    const model = state.model || {};
    setText("model-name", model.name || "Local possession candidate");
    setText("model-description", model.description || "Tracking data flows through a local model to produce one prediction per frame.");
    const validation = state.external_validation || {};
    setText("validation-notice", validation.notice || "External validation is separate from the challenge match and does not establish hidden-match performance.");
    const scores = [validation.clean_spell_f1, validation.occluded_spell_f1, validation.combined_spell_f1];
    $("validation-scores").hidden = !scores.some((value) => typeof value === "number" && Number.isFinite(value));
    ["clean-score", "occluded-score", "combined-score"].forEach((id, index) => {
      setText(id, typeof scores[index] === "number" && Number.isFinite(scores[index]) ? scores[index].toFixed(3) : "Not available");
    });
    setText("validation-match", validation.match ? `External match: ${validation.match}. Scores do not measure challenge-match accuracy.` : "Challenge-match accuracy remains unknown.");
    const runtime = state.runtime;
    setText("runtime-total", runtime && Number.isFinite(runtime.total_seconds) && runtime.total_seconds >= 0
      ? `${runtime.total_seconds.toFixed(2)} s` : "Not measured");
    setText("runtime-memory", runtime && Number.isFinite(runtime.peak_process_working_set_bytes) && runtime.peak_process_working_set_bytes >= 0
      ? `${(runtime.peak_process_working_set_bytes / 1048576).toFixed(1)} MiB` : "Not measured");
    setText("runtime-cache", state.mode === "demo" ? "Synthetic demo run"
      : runtime && typeof runtime.cache_hit === "boolean" ? runtime.cache_hit ? "Used existing tracking cache" : "Fresh tracking read" : "—");
  }

  function renderState() {
    fps = number(state.match.fps, 25);
    frames = integer(state.match.frames);
    currentFrame = Math.min(currentFrame, Math.max(0, frames - 1));
    const home = state.match.home || "Home";
    const away = state.match.away || "Away";
    setText("mode-label", state.mode === "demo" ? "Synthetic demo" : "Local workspace");
    $("environment").className = `environment is-${state.mode}`;
    $("demo-notice").hidden = state.mode !== "demo";
    setText("match-title", state.match.title || `${home} vs ${away}`);
    setText("match-frames", `${formatNumber(frames)} frames`);
    setText("match-fps", `${fps} fps`);
    for (const id of ["home-name", "legend-home"]) setText(id, home);
    for (const id of ["away-name", "legend-away"]) setText(id, away);
    renderRatios();
    renderRun();
    renderEvidence();
    renderMedia();
    renderFrame();
  }

  async function refreshTimeline(key) {
    const requestId = ++timelineRequest;
    try {
      const data = await requestJSON("/api/timeline");
      if (requestId !== timelineRequest) return;
      if (!Array.isArray(data.segments) || integer(data.frames) !== frames || number(data.fps) !== fps) {
        throw new Error("The timeline metadata does not match the current match. Regenerate the CSV before reviewing it.");
      }
      const next = [];
      let end = 0;
      for (const segment of data.segments) {
        if (!segment || !Object.hasOwn(colors, segment.label) || !Number.isInteger(segment.start) || !Number.isInteger(segment.end)
          || segment.start !== end || segment.end <= segment.start || segment.end > frames) {
          throw new Error("The timeline contains an invalid frame or label sequence. Regenerate the CSV before reviewing it.");
        }
        next.push({ start: segment.start, end: segment.end, label: segment.label });
        end = segment.end;
      }
      if (end !== frames) throw new Error("The prediction timeline does not cover every match frame.");
      segments = next;
      timelineKey = key;
      seek.disabled = false;
      seek.max = String(Math.max(0, frames - 1));
      $("timeline-placeholder").hidden = true;
      renderMedia();
      drawTimeline();
      renderFrame();
    } catch (error) {
      if (requestId !== timelineRequest) return;
      clearTimeline("The prediction timeline could not be loaded.");
      notice(error.message, true);
    }
  }

  function clearTimeline(message = "The timeline appears when predictions are ready.") {
    segments = [];
    timelineKey = null;
    seek.disabled = true;
    $("timeline-placeholder").hidden = false;
    setText("timeline-placeholder", message);
    if (demoPlaying) pauseDemo();
    drawTimeline();
    renderFrame();
    if (state) renderMedia();
  }

  async function loadState() {
    if (stateRequest) return stateRequest;
    stateRequest = (async () => {
      try {
        const data = await requestJSON("/api/state");
        if (!data || !["local", "demo"].includes(data.mode) || !data.match || !data.inputs || !data.output
          || !Number.isInteger(data.match.frames) || data.match.frames < 1 || !Number.isFinite(data.match.fps) || data.match.fps <= 0) {
          throw new Error("The review service returned incomplete match metadata.");
        }
        const oldMode = state && state.mode;
        state = data;
        if (oldMode && oldMode !== state.mode) {
          pauseDemo();
          currentFrame = 0;
          mediaFailed = false;
          clearTimeline();
        }
        notice("");
        renderState();
        const key = hasOutput() ? `${state.mode}:${data.output.sha256}:${frames}:${fps}` : null;
        if (key && key !== timelineKey) {
          clearTimeline("Loading the prediction timeline…");
          await refreshTimeline(key);
        }
        else if (!key && segments.length) clearTimeline();
      } catch (error) {
        notice(`${error.message}${state ? " The last loaded review remains visible." : ""}`, true);
        $("environment").className = "environment is-offline";
        setText("mode-label", "Service offline");
        if (!state) {
          setText("match-title", "The local service is unavailable");
          setText("stage-empty-title", "Waiting for the review service");
          setText("stage-empty-description", "Keep the local server running. This page will reconnect automatically.");
          setText("run-title", "Connection unavailable");
          setText("run-message", "Waiting to reconnect to the local review service.");
        }
      } finally {
        stateRequest = null;
        clearTimeout(pollTimer);
        pollTimer = setTimeout(loadState, isRunning() || runRequest ? 1500 : 8000);
      }
    })();
    return stateRequest;
  }

  function segmentIndex(frame) {
    let low = 0;
    let high = segments.length - 1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      const segment = segments[middle];
      if (frame < segment.start) high = middle - 1;
      else if (frame >= segment.end) low = middle + 1;
      else return middle;
    }
    return -1;
  }

  function renderFrame() {
    const frame = integer(currentFrame);
    const seconds = frame / fps;
    $("video-clock").replaceChildren(document.createTextNode(`${clock(seconds)} `));
    const total = document.createElement("span");
    total.textContent = `/ ${frames ? clock(frames / fps) : "—"}`;
    $("video-clock").append(total);
    seek.value = String(frame);
    const index = segmentIndex(frame);
    const segment = index >= 0 ? segments[index] : null;
    const label = segment ? segment.label : "";
    $("prediction-overlay").hidden = !segment;
    setText("current-team", labelDescription(label));
    setText("current-label", label || "—");
    $("prediction-indicator").style.backgroundColor = colors[label] || colors.X;
    setText("frame-counter", frames ? `FRAME ${formatNumber(frame)} / ${formatNumber(frames - 1)}` : "FRAME — / —");
    seek.setAttribute("aria-valuetext", segment ? `${clock(seconds)}, frame ${frame}, ${labelDescription(label)}` : "No timeline available");
    $("previous-state").disabled = index < 0 || index === 0;
    $("next-state").disabled = index < 0 || index >= segments.length - 1;
    if (state && state.mode === "demo") {
      const phase = seconds / 13;
      const x = Math.sin(phase) * 180;
      const y = Math.sin(phase * 1.7) * 110;
      $("demo-ball").setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
    }
  }

  function drawTimeline() {
    const rectangle = canvas.getBoundingClientRect();
    const ratio = Math.min(3, window.devicePixelRatio || 1);
    canvas.width = Math.max(1, Math.round(rectangle.width * ratio));
    canvas.height = Math.max(1, Math.round(rectangle.height * ratio));
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (hasTimeline()) {
      // Draw in chronological order. Subpixel spells retain their true frame boundaries.
      for (const segment of segments) {
        const left = segment.start / frames * canvas.width;
        const right = segment.end / frames * canvas.width;
        context.fillStyle = colors[segment.label];
        context.fillRect(left, 0, right - left, canvas.height);
      }
    }
    const ticks = $("timeline-ticks").children;
    for (let index = 0; index < ticks.length; index++) {
      ticks[index].textContent = frames ? clock((frames / fps) * index / (ticks.length - 1), false) : index === 0 ? "00:00" : "—";
    }
    canvas.setAttribute("aria-label", hasTimeline() ? `Full-match predicted possession timeline, ${formatNumber(segments.length)} state segments. Use the seek slider to review frames.` : "No predicted possession timeline available.");
  }

  function seekTo(frame) {
    currentFrame = Math.max(0, Math.min(integer(frame), Math.max(0, frames - 1)));
    demoPosition = currentFrame / fps;
    if (state && state.mode === "local" && mediaSourceSet && !mediaFailed) {
      try { video.currentTime = demoPosition; }
      catch (_) { /* Metadata can still be loading; the timeline remains usable. */ }
    }
    renderFrame();
  }

  function setPlaying(playing) {
    $("play-icon").hidden = playing;
    $("pause-icon").hidden = !playing;
    $("play-toggle").setAttribute("aria-label", playing ? "Pause video" : "Play video");
  }

  function pauseDemo() {
    demoPlaying = false;
    demoLastTick = null;
    if (animationId !== null) cancelAnimationFrame(animationId);
    animationId = null;
    setPlaying(false);
  }

  function animateDemo(timestamp) {
    if (!demoPlaying) return;
    if (demoLastTick !== null) demoPosition += Math.min(0.25, (timestamp - demoLastTick) / 1000) * playbackSpeed;
    demoLastTick = timestamp;
    currentFrame = Math.min(frames - 1, Math.floor(demoPosition * fps));
    renderFrame();
    if (currentFrame >= frames - 1) pauseDemo();
    else animationId = requestAnimationFrame(animateDemo);
  }

  $("play-toggle").addEventListener("click", async () => {
    if (!state) return;
    if (state.mode === "demo") {
      if (demoPlaying) pauseDemo();
      else {
        if (currentFrame >= frames - 1) seekTo(0);
        demoPlaying = true;
        demoLastTick = null;
        setPlaying(true);
        animationId = requestAnimationFrame(animateDemo);
      }
    } else if (video.paused) {
      try { await video.play(); }
      catch (_) { notice("The video could not start. Check local video availability and browser playback support.", true); }
    } else video.pause();
  });
  video.addEventListener("play", () => setPlaying(true));
  video.addEventListener("pause", () => setPlaying(false));
  video.addEventListener("ended", () => setPlaying(false));
  video.addEventListener("timeupdate", () => {
    if (!state || state.mode !== "local") return;
    currentFrame = Math.max(0, Math.min(frames - 1, Math.floor(video.currentTime * fps + 0.000001)));
    renderFrame();
  });
  video.addEventListener("loadedmetadata", () => {
    video.playbackRate = playbackSpeed;
    if (currentFrame > 0) {
      try { video.currentTime = currentFrame / fps; } catch (_) { /* Seeking remains available after metadata settles. */ }
    }
  });
  video.addEventListener("error", () => {
    if (!mediaSourceSet || !state || state.mode !== "local") return;
    mediaFailed = true;
    setPlaying(false);
    renderMedia();
  });
  seek.addEventListener("input", () => seekTo(Number(seek.value)));
  $("previous-state").addEventListener("click", () => {
    const index = segmentIndex(currentFrame);
    if (index > 0) seekTo(segments[index - 1].start);
  });
  $("next-state").addEventListener("click", () => {
    const index = segmentIndex(currentFrame);
    if (index >= 0 && index < segments.length - 1) seekTo(segments[index + 1].start);
  });
  $("playback-speed").addEventListener("change", (event) => {
    playbackSpeed = Number(event.target.value) || 1;
    video.playbackRate = playbackSpeed;
  });
  $("fullscreen-toggle").addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if ($("video-stage").requestFullscreen) await $("video-stage").requestFullscreen();
      else notice("Fullscreen is not supported by this browser. Playback is available in the review panel.");
    } catch (_) { notice("Fullscreen could not be opened in this browser."); }
  });
  document.addEventListener("fullscreenchange", () => {
    $("fullscreen-toggle").setAttribute("aria-label", document.fullscreenElement ? "Exit fullscreen video" : "Enter fullscreen video");
  });

  $("regenerate").addEventListener("click", async () => {
    if (!state || !state.request_token || runRequest || isRunning()) return;
    runRequest = true;
    renderRun();
    try {
      await requestJSON("/api/run", postOptions({}));
      notice("");
    } catch (error) {
      notice(error.message, true);
    } finally {
      await loadState();
      runRequest = false;
      renderRun();
      clearTimeout(pollTimer);
      pollTimer = setTimeout(loadState, 1500);
    }
  });

  $("export-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state || !hasOutput() || !state.request_token || exportRequest || isRunning()) return;
    if (!event.target.reportValidity()) return;
    exportRequest = true;
    $("export-feedback").classList.remove("is-error");
    setText("export-feedback", "Building the local review pack…");
    renderRun();
    try {
      const result = await requestJSON("/api/export", postOptions({
        team_name: $("team-name").value.trim(),
        repository_url: $("repository-url").value.trim()
      }));
      if (typeof result.download_url !== "string" || !result.download_url.startsWith("/download/") || result.download_url.startsWith("//") || result.download_url.includes("\\")) {
        throw new Error("The service did not return a safe local review-pack download.");
      }
      const downloadURL = new URL(result.download_url, window.location.origin);
      if (downloadURL.origin !== window.location.origin) throw new Error("The review pack must download from this local service.");
      const link = document.createElement("a");
      link.href = downloadURL.href;
      link.download = typeof result.filename === "string" ? result.filename : "touchline-review-pack.zip";
      document.body.append(link);
      link.click();
      link.remove();
      const pending = Array.isArray(result.pending) ? result.pending.filter((item) => typeof item === "string") : [];
      setText("export-feedback", pending.length
        ? `Review pack prepared. Not submission-ready. Still needed: ${pending.join("; ")}`
        : "Review pack prepared for local download. Review the files before any competition submission.");
    } catch (error) {
      $("export-feedback").classList.add("is-error");
      setText("export-feedback", error.message);
    } finally {
      exportRequest = false;
      renderRun();
    }
  });
  document.querySelectorAll("a[aria-disabled]").forEach((link) => {
    link.addEventListener("click", (event) => { if (link.getAttribute("aria-disabled") === "true") event.preventDefault(); });
  });
  if (typeof ResizeObserver === "function") new ResizeObserver(drawTimeline).observe($("timeline-track"));
  else window.addEventListener("resize", drawTimeline);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseDemo();
    else loadState();
  });
  window.addEventListener("beforeunload", () => { clearTimeout(pollTimer); pauseDemo(); });
  drawTimeline();
  loadState();
})();
