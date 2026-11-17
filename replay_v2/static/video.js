/** Optional local comparison media. Native video is the linked clock; Drive is
 * deliberately an independent, sandboxed preview. No file bytes leave the picker.
 */
export function createVideoComparison({ container, getReplay, onChange = () => {}, onRelease = () => {} }) {
  const make = (tag, props = {}, text = '') => {
    const element = document.createElement(tag);
    Object.assign(element, props);
    if (text) element.textContent = text;
    return element;
  };
  const panel = make('section', { className: 'video-comparison' });
  panel.setAttribute('aria-labelledby', 'video-heading');
  const heading = make('h2', { id: 'video-heading' }, 'Compare with match video');
  const intro = make('p', { className: 'video-intro' }, 'Choose a local MP4 to link playback, or open an independent Google Drive preview. Local files stay in this browser and are never uploaded.');
  const controls = make('div', { className: 'video-controls' });
  const localGroup = make('div', { className: 'video-local' });
  const fileLabel = make('label', { htmlFor: 'video-file' }, 'Local match video (MP4)');
  const fileInput = make('input', { id: 'video-file', type: 'file', accept: 'video/mp4,.mp4' });
  const localHelp = make('p', { id: 'video-local-help', className: 'video-help' }, 'Use an MP4 your browser can decode, such as H.264. Selecting a file pauses playback first. Use the tactical recording. Broadcast edits/replays cannot be aligned with one offset.');
  fileInput.setAttribute('aria-describedby', localHelp.id);
  localGroup.append(fileLabel, fileInput, localHelp);
  const driveGroup = make('div', { className: 'video-drive' });
  const urlLabel = make('label', { htmlFor: 'video-url' }, 'Google Drive file share link');
  const urlInput = make('input', { id: 'video-url', type: 'url', placeholder: 'https://drive.google.com/file/d/…/view', maxLength: 2048, autocomplete: 'off' });
  const driveButton = make('button', { id: 'video-link', type: 'button' }, 'Open Drive preview');
  const driveHelp = make('p', { id: 'video-drive-help', className: 'video-help' }, 'Drive playback is independent and manual: its iframe cannot be synchronized. Access, processing or cookies may block it; choose a local MP4 instead.');
  urlInput.setAttribute('aria-describedby', driveHelp.id);
  driveGroup.append(urlLabel, urlInput, driveButton, driveHelp);
  const clockControls = make('div', { className: 'video-clock-controls' });
  const syncLabel = make('label', { className: 'video-sync-label' });
  const syncInput = make('input', { id: 'video-sync', type: 'checkbox', disabled: true });
  syncLabel.append(syncInput, document.createTextNode(' Link controls — same tactical timeline'));
  const offsetLabel = make('label', { htmlFor: 'video-offset' }, 'Video offset (seconds)');
  const offsetInput = make('input', { id: 'video-offset', type: 'number', value: '0', step: 'any', disabled: true });
  const offsetHelp = make('p', { id: 'video-offset-help', className: 'video-help' }, 'Video seconds = recording seconds + offset. Full tactical video: 0. Clips may cover only part of the recording.');
  offsetInput.setAttribute('aria-describedby', offsetHelp.id);
  const unlinkButton = make('button', { id: 'video-unlink', type: 'button', disabled: true }, 'Remove video');
  clockControls.append(syncLabel, offsetLabel, offsetInput, unlinkButton, offsetHelp);
  controls.append(localGroup, clockControls, driveGroup);
  const status = make('p', { id: 'video-status', className: 'video-status' }, 'No video selected. Tracking playback works on its own.');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const createNativeElement = () => {
    const element = make('video', { id: 'comparison-video', controls: true, preload: 'metadata', playsInline: true, hidden: true });
    element.setAttribute('aria-label', 'Local match video');
    return element;
  };
  let video = createNativeElement();
  const drive = make('iframe', { id: 'drive-preview', title: 'Google Drive video preview — independent manual playback', hidden: true, referrerPolicy: 'no-referrer' });
  drive.setAttribute('sandbox', 'allow-scripts allow-same-origin');
  drive.setAttribute('allow', 'fullscreen');
  drive.setAttribute('allowfullscreen', '');
  const timingHelp = make('p', { className: 'video-help' }, 'Linked tracking follows the native video’s presented media time when available. Browser scheduling can differ by a display frame; this is a visual comparison, not guaranteed compositor synchronization.');
  panel.append(heading, intro, status, video, drive, controls, timingHelp);
  container.append(panel);

  let destroyed = false;
  let sourceKind = null;
  let objectURL = null;
  let linked = false;
  let ready = false;
  let offset = 0;
  let presentedTime = null;
  let callbackID = null;
  let callbackKind = null;
  let sourceEpoch = 0;
  let lastState = null;
  let lastStatus = '';
  const listeners = [];
  const nativeListeners = [];
  const listen = (target, name, fn, bucket = listeners) => {
    target.addEventListener(name, fn);
    bucket.push([target, name, fn]);
  };
  const removeNativeListeners = () => {
    for (const [target, name, fn] of nativeListeners) target.removeEventListener(name, fn);
    nativeListeners.length = 0;
  };
  const notify = () => { if (!destroyed) onChange(); };
  const say = (message, error = false) => {
    if (lastStatus !== message) { status.textContent = message; lastStatus = message; }
    status.dataset.state = error ? 'error' : 'ready';
  };
  const replay = () => {
    const state = getReplay();
    return state && Number.isFinite(state.fps) && state.fps > 0 &&
      Number.isInteger(state.frames) && state.frames > 0 && Number.isFinite(state.position) ? state : null;
  };
  const range = state => {
    if (!state || !ready || !Number.isFinite(video.duration) || video.duration <= 0) return null;
    const start = Math.max(0, offset);
    // duration is exclusive: no presented frame exists at that exact time.
    // Stop on the last tracking sample strictly before the video's end.
    const last = Math.min(state.frames - 1, Math.ceil((video.duration - offset) * state.fps) - 1);
    const end = last / state.fps + offset;
    return end >= start && start >= 0 && end <= video.duration ? { start, end } : null;
  };
  const inRange = (seconds, bounds) => !!bounds && seconds >= bounds.start - 1e-7 && seconds <= bounds.end + 1e-7;
  const stopCallback = () => {
    if (callbackID !== null) {
      if (callbackKind === 'video') video.cancelVideoFrameCallback?.(callbackID);
      else cancelAnimationFrame(callbackID);
    }
    callbackID = null;
    callbackKind = null;
  };
  const stateAt = (state, seconds) => {
    const position = Math.min(state.frames - 1, Math.max(0, (seconds - offset) * state.fps));
    // Seek arithmetic can put an exact sample a few ulps below its frame.
    const snapped = Math.abs(position - Math.round(position)) < 1e-7 ? Math.round(position) : position;
    const bounds = range(state);
    return { position: snapped, frame: Math.floor(snapped), speed: video.playbackRate,
      playing: !video.paused && !video.ended && !video.seeking && !!bounds && seconds < bounds.end,
      ended: !!bounds && (video.ended || seconds >= bounds.end - 1e-7) };
  };
  const snapshot = () => {
    if (destroyed || !linked || !ready) return null;
    const state = replay();
    if (!state) return null;
    const seconds = !video.paused && !video.seeking && presentedTime !== null ? presentedTime : video.currentTime;
    lastState = stateAt(state, seconds);
    return { ...lastState };
  };
  const release = (preservedState = null) => {
    if (!linked) return false;
    const state = preservedState || snapshot() || lastState || replay();
    linked = false;
    syncInput.checked = false;
    stopCallback();
    presentedTime = null;
    video.pause();
    if (state) onRelease({ position: state.position, speed: state.speed });
    return true;
  };
  const noCorrespondingTime = (preservedState = null) => {
    release(preservedState);
    video.pause();
    say('No corresponding video time; choose the full tactical video or adjust the offset. Tracking playback is independent.', true);
    notify();
  };
  const ensureBoundary = (fromSeek = false) => {
    if (!linked) return;
    const state = replay();
    const bounds = range(state);
    if (!bounds || video.currentTime < bounds.start - 1e-6 || (fromSeek && video.currentTime > bounds.end + 1e-6)) {
      noCorrespondingTime();
      return;
    }
    if (video.currentTime >= bounds.end) {
      presentedTime = bounds.end;
      video.pause();
      // End the common recording even if the selected video continues longer.
      if (video.currentTime !== bounds.end) video.currentTime = bounds.end;
      say('End of the shared video / tracking range. Replay restarts at its first corresponding frame.');
    }
  };
  const startCallback = () => {
    if (destroyed || !linked || video.paused || callbackID !== null) return;
    const epoch = sourceEpoch;
    if (typeof video.requestVideoFrameCallback === 'function') {
      callbackKind = 'video';
      callbackID = video.requestVideoFrameCallback((_now, metadata) => {
        callbackID = null;
        if (epoch !== sourceEpoch || destroyed || !linked) return;
        presentedTime = Number.isFinite(metadata.mediaTime) ? metadata.mediaTime : null;
        ensureBoundary();
        notify();
        startCallback();
      });
    } else {
      callbackKind = 'animation';
      callbackID = requestAnimationFrame(() => {
        callbackID = null;
        if (epoch !== sourceEpoch || destroyed || !linked) return;
        ensureBoundary();
        notify();
        startCallback();
      });
    }
  };
  const positionNative = seconds => {
    presentedTime = null;
    if (Math.abs(video.currentTime - seconds) > 1e-7) video.currentTime = seconds;
  };
  const linkNative = () => {
    if (!ready || sourceKind !== 'local') {
      syncInput.checked = false;
      say('Choose a decodable local MP4 and wait for its metadata before linking playback.', true);
      return false;
    }
    const state = replay();
    if (!state) {
      syncInput.checked = false;
      say('Tracking is not ready. Leave the local video open, then enable linked playback when tracking is available.', true);
      return false;
    }
    const seconds = state.position / state.fps + offset;
    if (!inRange(seconds, range(state))) { noCorrespondingTime(); syncInput.checked = false; return false; }
    video.pause();
    positionNative(seconds);
    if (Number.isFinite(state.speed) && state.speed > 0) video.playbackRate = state.speed;
    linked = true;
    syncInput.checked = true;
    lastState = stateAt(state, seconds);
    say('Linked controls · assumed same tactical timeline, offset ' + offset + ' s. Shared play, pause, seek and speed; video content is not verified.');
    notify();
    return true;
  };
  const clearSource = () => {
    release();
    sourceEpoch += 1;
    stopCallback();
    removeNativeListeners();
    video.pause();
    ready = false;
    presentedTime = null;
    sourceKind = null;
    video.removeAttribute('src');
    video.load();
    // A fresh element makes queued metadata/error/seek events from an old
    // resource unambiguous: they target an element with no remaining listeners.
    const replacement = createNativeElement();
    video.replaceWith(replacement);
    video = replacement;
    bindNativeListeners();
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = null;
    drive.removeAttribute('src');
    video.hidden = true;
    drive.hidden = true;
    syncInput.checked = false;
    syncInput.disabled = true;
    offsetInput.disabled = true;
    unlinkButton.disabled = true;
  };
  const pauseStandalone = () => {
    const state = replay();
    if (state) onRelease({ position: state.position, speed: state.speed });
  };

  listen(fileInput, 'change', () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!/\.mp4$/i.test(file.name) && file.type !== 'video/mp4') {
      say('Choose an MP4 video. If necessary, convert a local copy to H.264 MP4 without changing the original.', true);
      fileInput.value = '';
      return;
    }
    clearSource();
    pauseStandalone();
    try { objectURL = URL.createObjectURL(file); }
    catch (_) { say('The browser could not open this local file. Choose the MP4 again.', true); return; }
    sourceKind = 'local';
    video.hidden = false;
    unlinkButton.disabled = false;
    offsetInput.disabled = false;
    video.src = objectURL;
    video.load();
    say('Opening local video metadata. Playback is paused.');
    // Clear the picker so selecting the same file again is a real replacement.
    fileInput.value = '';
    notify();
  });
  const bindNativeListeners = () => {
  const mediaListen = (name, fn) => listen(video, name, fn, nativeListeners);
  mediaListen('loadedmetadata', () => {
    if (sourceKind !== 'local') return;
    if (!Number.isFinite(video.duration) || video.duration <= 0) {
      clearSource(); say('This video has no usable finite duration. Choose a complete local MP4.', true); notify(); return;
    }
    ready = true;
    syncInput.disabled = !replay();
    say('Local video ready · independent playback. For the same tactical recording, enable “Link controls” and set its offset. Broadcast edits/replays cannot be aligned with one offset.');
    notify();
  });
  mediaListen('error', () => {
    if (sourceKind !== 'local') return;
    clearSource();
    say('This video could not be decoded. Choose a local H.264 MP4, or try an independent Drive preview. Tracking remains available.', true);
    notify();
  });
  mediaListen('play', () => {
    if (!linked) return;
    presentedTime = null;
    ensureBoundary();
    startCallback();
    notify();
  });
  mediaListen('pause', () => { presentedTime = null; stopCallback(); notify(); });
  mediaListen('ended', () => { presentedTime = null; stopCallback(); ensureBoundary(); notify(); });
  mediaListen('ratechange', notify);
  mediaListen('seeking', () => { presentedTime = null; stopCallback(); notify(); });
  mediaListen('seeked', () => {
    presentedTime = null;
    ensureBoundary(true);
    startCallback();
    notify();
  });
  mediaListen('timeupdate', () => {
    if (linked) ensureBoundary();
    notify();
  });
  };
  bindNativeListeners();
  listen(syncInput, 'change', () => {
    if (syncInput.checked) linkNative();
    else { release(); say('Local video playback is independent. Enable linked playback to share the tracking clock.'); notify(); }
  });
  listen(offsetInput, 'change', () => {
    const value = offsetInput.value.trim();
    const next = Number(value);
    if (!value || !Number.isFinite(next)) {
      offsetInput.setAttribute('aria-invalid', 'true');
      say('Enter a finite video offset in seconds; use 0 for the full tactical video. The previous offset remains active.', true);
      return;
    }
    offsetInput.removeAttribute('aria-invalid');
    // Preserve the requested tracking frame when changing the offset.
    const tracking = replay();
    const state = snapshot() || tracking;
    video.pause();
    offset = next;
    if (linked && state && tracking) {
      const seconds = state.position / tracking.fps + offset;
      if (!inRange(seconds, range(tracking))) noCorrespondingTime(state);
      else { positionNative(seconds); say('Linked controls · assumed same tactical timeline, offset ' + offset + ' s. Playback is paused; video content is not verified.'); }
    } else say('Offset set to ' + offset + ' s. Enable linked playback to apply it at the tracking position.');
    notify();
  });

  // Only two documented file-share URL shapes are accepted. All navigation is
  // rebuilt from validated identifiers; supplied paths/query strings are not used.
  const drivePreviewURL = value => {
    if (value.length > 2048) return null;
    let url;
    try { url = new URL(value); } catch (_) { return null; }
    if (url.protocol !== 'https:' || url.hostname !== 'drive.google.com' || url.port || url.username || url.password) return null;
    let id;
    const path = url.pathname.match(/^\/file\/d\/([A-Za-z0-9_-]{10,200})(?:\/(?:view|preview|edit))?\/?$/);
    if (path) id = path[1];
    else if (/^\/(?:open|uc)\/?$/.test(url.pathname) && url.searchParams.getAll('id').length === 1) id = url.searchParams.get('id');
    if (!id || !/^[A-Za-z0-9_-]{10,200}$/.test(id)) return null;
    const output = new URL('https://drive.google.com/file/d/' + id + '/preview');
    const keys = url.searchParams.getAll('resourcekey');
    if (keys.length > 1 || (keys.length && !/^[A-Za-z0-9_-]{1,200}$/.test(keys[0]))) return null;
    if (keys.length) output.searchParams.set('resourcekey', keys[0]);
    return output.href;
  };
  listen(driveButton, 'click', () => {
    const previewURL = drivePreviewURL(urlInput.value.trim());
    if (!previewURL) {
      urlInput.setAttribute('aria-invalid', 'true');
      say('Use an HTTPS drive.google.com file share link (/file/d/FILE_ID/view or /open?id=FILE_ID), not a folder or another website. A local MP4 is always available.', true);
      return;
    }
    urlInput.removeAttribute('aria-invalid');
    clearSource();
    pauseStandalone();
    sourceKind = 'drive';
    drive.hidden = false;
    unlinkButton.disabled = false;
    drive.src = previewURL;
    say('Drive preview · independent manual playback. Its controls cannot be linked to tracking. If it is unavailable, choose a local MP4.');
    notify();
  });
  listen(unlinkButton, 'click', () => {
    clearSource();
    pauseStandalone();
    say('Video removed. Tracking playback is independent and paused.');
    notify();
  });

  return {
    snapshot,
    refresh() {
      if (destroyed) return;
      syncInput.disabled = sourceKind !== 'local' || !ready || !replay();
      if (linked && syncInput.disabled) release();
      notify();
    },
    seek(frame) {
      if (!linked || destroyed) return false;
      const state = replay();
      const boundedFrame = state && Number.isFinite(frame) ? Math.max(0, Math.min(state.frames - 1, frame)) : NaN;
      const seconds = state ? boundedFrame / state.fps + offset : NaN;
      if (!inRange(seconds, range(state))) { noCorrespondingTime(); return false; }
      positionNative(seconds);
      notify();
      return true;
    },
    async toggle() {
      if (!linked || destroyed) return false;
      if (!video.paused) { video.pause(); notify(); return true; }
      const state = snapshot();
      const bounds = range(replay());
      if (!bounds) { noCorrespondingTime(); return false; }
      if (state?.ended) positionNative(bounds.start);
      const epoch = sourceEpoch;
      try { await video.play(); }
      catch (_) {
        if (!destroyed && epoch === sourceEpoch) {
          video.pause();
          say('Playback was blocked or this codec is unavailable. Press Play in the video controls, or choose a local H.264 MP4.', true);
          notify();
        }
      }
      return true;
    },
    pause() { if (!destroyed) { video.pause(); presentedTime = null; stopCallback(); notify(); } },
    setSpeed(value) {
      if (!linked || destroyed) return false;
      if (!Number.isFinite(value) || value <= 0 || value > 16) { say('Choose a playback speed above 0 and at most 16×.', true); return true; }
      try { video.playbackRate = value; }
      catch (_) { say('This browser cannot use that playback speed. Choose a supported speed in the video controls.', true); }
      notify();
      return true;
    },
    suspend() {
      if (destroyed) return;
      release();
      video.pause();
      presentedTime = null;
      stopCallback();
      if (sourceKind === 'local') say('Linked playback is paused. Enable linked playback when tracking is ready.');
      notify();
    },
    destroy() {
      if (destroyed) return;
      clearSource();
      destroyed = true;
      removeNativeListeners();
      for (const [target, name, fn] of listeners) target.removeEventListener(name, fn);
      panel.remove();
    },
  };
}
