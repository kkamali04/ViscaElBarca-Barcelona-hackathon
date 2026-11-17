import { createPlaybackClock } from './clock.js';
import { getDisplayMotion, getGhosts } from './motion.js';
import { createVideoComparison } from './video.js';

const VIEW_PADDING_METRES = 8;
const MAX_WINDOWS = 3;
const REQUEST_TIMEOUT_MS = 15000;
const $ = id => document.getElementById(id);
const ui = Object.fromEntries(['pitch', 'pitch-stage', 'seek', 'play', 'previous', 'next',
  'speed', 'clock', 'duration', 'status', 'possession', 'possession-detail',
  'ball-status', 'bounds-status', 'visible-slots', 'missing-slots', 'outside-slots', 'fps',
  'frame-counter', 'mode-badge', 'source-caption', 'pitch-size', 'motion-note',
  'stage-message', 'stage-title', 'stage-detail', 'retry', 'motion-mode',
  'show-ghosts', 'ghost-slots', 'catalog-size', 'live-possession'].map(id => [id, $(id)]));
// Keep raw file:// opening and failed module loading readable instead of a broken app.
document.getElementById('app-shell').hidden = false;
document.getElementById('launch-help').hidden = true;
const context = ui.pitch.getContext('2d');
let metadata = null;
let clock = null;
let store = null;
let animationPending = false;
let bootEpoch = 0;
let failed = false;
let stateName = '';
let messageKey = '';
let lastPositions = null;
let lastGhosts = [];
let comparison = null;

function timelineState(timestamp) {
  return comparison?.snapshot() || clock?.snapshot(timestamp);
}

function pausePlayback() {
  comparison?.pause();
  clock?.pause();
}

function formatTime(frames, fps) {
  const centiseconds = Math.floor(Math.max(0, frames) / fps * 100 + 1e-7);
  const minutes = Math.floor(centiseconds / 6000);
  const seconds = Math.floor(centiseconds / 100) % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(centiseconds % 100).padStart(2, '0')}`;
}

function setStatus(text, kind = 'ready') {
  const key = `${kind}:${text}`;
  if (stateName === key) return;
  stateName = key;
  ui.status.textContent = text;
  ui.status.dataset.state = kind;
}

function stageMessage(title = '', detail = '', retry = false) {
  const key = `${title}:${detail}:${retry}`;
  if (messageKey === key) return;
  messageKey = key;
  ui['stage-message'].hidden = !title;
  ui['stage-title'].textContent = title;
  ui['stage-detail'].textContent = detail;
  ui.retry.hidden = !retry;
  ui['stage-message'].querySelector('.loader').hidden = retry;
}

function disableControls(disabled) {
  for (const id of ['seek', 'play', 'previous', 'next', 'speed', 'motion-mode', 'show-ghosts']) ui[id].disabled = disabled;
}

function showFailure(message = 'The local coordinate stream could not be read. Check that the launcher is running, then choose Try again.') {
  failed = true;
  pausePlayback();
  comparison?.suspend();
  if (store) store.invalidate();
  lastPositions = null;
  lastGhosts = [];
  drawPitch(null);
  clearObservationReadout();
  disableControls(true);
  setStatus('Unavailable', 'error');
  stageMessage('Replay unavailable', message, true);
  ui['ball-status'].textContent = 'Unavailable';
  ui.possession.textContent = 'Unavailable';
  ui['live-possession'].textContent = 'Unavailable';
  ui['possession-detail'].textContent = 'No current prediction is shown while the replay is unavailable.';
  updatePlayButton();
}

async function boundedFetch(url, options = {}, consume = response => response) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal,
      credentials: 'same-origin', cache: 'no-store' });
    return await consume(response);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
}

async function readWindowBytes(response, expectedBytes) {
  const declaredLength = response.headers.get('content-length');
  if (declaredLength !== null && Number(declaredLength) !== expectedBytes) {
    throw new Error('Coordinate response had an invalid declared length.');
  }
  if (!response.body?.getReader) return response.arrayBuffer();
  const reader = response.body.getReader();
  const bytes = new Uint8Array(expectedBytes);
  let offset = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (offset + value.byteLength > expectedBytes) throw new Error('Coordinate window exceeded its bounded size.');
      bytes.set(value, offset);
      offset += value.byteLength;
    }
    if (offset !== expectedBytes) throw new Error('Coordinate window was truncated.');
    return bytes.buffer;
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally { reader.releaseLock(); }
}

class FrameStore {
  constructor(meta) {
    this.meta = meta;
    this.chunks = new Map();
    this.pending = new Map();
    this.epoch = 0;
  }
  invalidate() {
    this.epoch += 1;
    for (const pending of this.pending.values()) pending.controller.abort();
    this.pending.clear();
  }
  startFor(frame) { return Math.floor(frame / this.meta.chunk_frames) * this.meta.chunk_frames; }
  row(frame) {
    const start = this.startFor(frame);
    const chunk = this.chunks.get(start);
    if (!chunk) return null;
    // Map insertion order is the LRU order. Only three decoded windows survive.
    this.chunks.delete(start);
    this.chunks.set(start, chunk);
    const offset = (frame - start) * this.meta.row_floats;
    return chunk.subarray(offset, offset + this.meta.row_floats);
  }
  request(frame, essential = false) {
    if (frame < 0 || frame >= this.meta.frames) return Promise.resolve();
    const start = this.startFor(frame);
    if (this.chunks.has(start)) return Promise.resolve();
    if (this.pending.has(start)) {
      const pending = this.pending.get(start);
      pending.essential ||= essential;
      return pending.promise;
    }
    const epoch = this.epoch;
    const controller = new AbortController();
    const pending = { controller, promise: null, essential };
    pending.promise = (async () => {
      try {
        const count = Math.min(this.meta.chunk_frames, this.meta.frames - start);
        const bytes = await boundedFetch(`/api/frames?start=${start}&count=${count}`, { signal: controller.signal }, async response => {
          if (!response.ok) throw new Error('Coordinate request failed.');
          if (!response.headers.get('content-type')?.toLowerCase().startsWith('application/octet-stream') ||
              response.headers.get('X-Start-Frame') !== String(start) ||
              response.headers.get('X-Frame-Count') !== String(count) ||
              response.headers.get('X-Row-Floats') !== String(this.meta.row_floats)) {
            throw new Error('Coordinate response did not match its requested frame window.');
          }
          return readWindowBytes(response, count * this.meta.row_floats * 4);
        });
        if (epoch !== this.epoch) return;
        if (bytes.byteLength !== count * this.meta.row_floats * 4) {
          throw new Error('Coordinate response had an invalid length.');
        }
        const view = new DataView(bytes);
        const values = new Float32Array(bytes.byteLength / 4);
        for (let i = 0; i < values.length; i += 1) values[i] = view.getFloat32(i * 4, true);
        for (let offset = 0; offset < values.length; offset += this.meta.row_floats) {
          for (let pair = 0; pair < this.meta.row_floats - 1; pair += 2) {
            const x = values[offset + pair], y = values[offset + pair + 1];
            if (!((Number.isFinite(x) && Number.isFinite(y)) || (Number.isNaN(x) && Number.isNaN(y)))) {
              throw new Error('Coordinate response contained an invalid observation pair.');
            }
          }
          const label = values[offset + this.meta.row_floats - 1];
          if (this.meta.predictions_ready ? !(Number.isInteger(label) && label >= 0 && label <= 3) : !Number.isNaN(label)) {
            throw new Error('Coordinate response contained an invalid prediction code.');
          }
        }
        this.chunks.set(start, values);
        while (this.chunks.size > MAX_WINDOWS) this.chunks.delete(this.chunks.keys().next().value);
        scheduleRender();
      } catch (_) {
        if (epoch !== this.epoch || controller.signal.aborted) return;
        // Prefetch failure can be retried when the window becomes essential.
        if (pending.essential) showFailure('A frame window was unavailable or failed its byte and frame checks. No replacement motion is shown.');
      } finally {
        if (this.pending.get(start) === pending) this.pending.delete(start);
      }
    })();
    this.pending.set(start, pending);
    return pending.promise;
  }
  prefetch(frame) {
    const adjacent = this.startFor(frame) + this.meta.chunk_frames;
    if (adjacent < this.meta.frames) this.request(adjacent);
  }
}

function validateMetadata(meta) {
  if (!meta || !['demo', 'local'].includes(meta.mode) || meta.status !== 'ready' ||
      !Number.isInteger(meta.frames) || meta.frames < 1 ||
      !Number.isFinite(meta.fps) || meta.fps <= 0 ||
      !Array.isArray(meta.pitch) || meta.pitch.length !== 2 ||
      !meta.pitch.every(value => Number.isFinite(value) && value > 0) ||
      !Array.isArray(meta.slots) || meta.slots.length > 128 || meta.slots.some(slot =>
        !Number.isInteger(slot.slot) || slot.slot < 0 || !['H', 'A'].includes(slot.side)) ||
      new Set(meta.slots.map(slot => slot.slot)).size !== meta.slots.length ||
      meta.row_floats !== 2 * (meta.slots.length + 1) + 1 || meta.chunk_frames !== 250 ||
      !Number.isInteger(meta.initial_frame) || meta.initial_frame < 0 || meta.initial_frame >= meta.frames ||
      typeof meta.predictions_ready !== 'boolean' ||
      JSON.stringify(meta.label_codes) !== JSON.stringify(['X', 'H', 'A', 'D'])) {
    throw new Error('Replay metadata did not match the viewer contract.');
  }
  return meta;
}

function updatePlayButton() {
  const state = timelineState();
  const playing = state?.playing || false;
  const ended = state?.ended || false;
  ui.play.children[0].textContent = playing ? 'Ⅱ' : ended ? '↻' : '▶';
  ui.play.children[1].textContent = playing ? 'Pause' : ended ? 'Replay' : 'Play';
  ui.play.setAttribute('aria-label', playing ? 'Pause replay' : ended ? 'Replay from beginning' : 'Play replay');
  ui.play.setAttribute('aria-pressed', String(playing));
  if (state?.speed) {
    if (!Array.from(ui.speed.options).some(option => Number(option.value) === state.speed)) {
      for (const option of Array.from(ui.speed.querySelectorAll('[data-native-rate]'))) option.remove();
      const option = new Option(`${state.speed}×`, String(state.speed));
      option.dataset.nativeRate = 'true'; ui.speed.add(option);
    }
    ui.speed.value = String(state.speed);
  }
}

function fitCanvas() {
  const rect = ui.pitch.getBoundingClientRect();
  const ratio = Math.min(window.devicePixelRatio || 1, 3);
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (ui.pitch.width !== width || ui.pitch.height !== height) {
    ui.pitch.width = width;
    ui.pitch.height = height;
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { width: width / ratio, height: height / ratio };
}

function drawPitch(positions, ghosts = []) {
  const { width, height } = fitCanvas();
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#183c34';
  context.fillRect(0, 0, width, height);
  // Layout can briefly report a zero-sized canvas during viewport transitions.
  if (width < 32 || height < 48) return;
  const [length, breadth] = metadata?.pitch || [105.3, 68];
  const bounds = { left: -VIEW_PADDING_METRES, right: length + VIEW_PADDING_METRES,
    top: -VIEW_PADDING_METRES, bottom: breadth + VIEW_PADDING_METRES };
  const bottomAllowance = 22;
  const scale = Math.min((width - 22) / (bounds.right - bounds.left), (height - bottomAllowance - 14) / (bounds.bottom - bounds.top));
  const originX = (width - (bounds.right - bounds.left) * scale) / 2 - bounds.left * scale;
  const originY = (height - bottomAllowance - (bounds.bottom - bounds.top) * scale) / 2 - bounds.top * scale;
  const px = x => originX + x * scale;
  const py = y => originY + y * scale;
  context.fillStyle = '#205242';
  context.fillRect(px(0), py(0), length * scale, breadth * scale);
  for (let stripe = 0; stripe < 10; stripe += 2) {
    context.fillStyle = '#245746';
    context.fillRect(px(stripe * length / 10), py(0), length * scale / 10, breadth * scale);
  }
  context.lineWidth = Math.max(.6, Math.min(1.1, scale * .18));
  context.strokeStyle = '#a1c3a570';
  const line = (x1, y1, x2, y2) => { context.beginPath(); context.moveTo(px(x1), py(y1)); context.lineTo(px(x2), py(y2)); context.stroke(); };
  const rect = (x, y, w, h) => context.strokeRect(px(x), py(y), w * scale, h * scale);
  const circle = (x, y, r) => { context.beginPath(); context.arc(px(x), py(y), r * scale, 0, Math.PI * 2); context.stroke(); };
  rect(0, 0, length, breadth);
  line(length / 2, 0, length / 2, breadth);
  circle(length / 2, breadth / 2, 9.15);
  for (const side of [0, 1]) {
    rect(side ? length - 16.5 : 0, (breadth - 40.32) / 2, 16.5, 40.32);
    rect(side ? length - 5.5 : 0, (breadth - 18.32) / 2, 5.5, 18.32);
    rect(side ? length : -1.8, (breadth - 7.32) / 2, 1.8, 7.32);
    context.beginPath();
    const spotX = side ? length - 11 : 11;
    context.arc(px(spotX), py(breadth / 2), 9.15 * scale, side ? Math.PI - .92 : -.92, side ? Math.PI + .92 : .92);
    context.stroke();
    context.fillStyle = '#b9d4bc85';
    context.beginPath(); context.arc(px(spotX), py(breadth / 2), 1.4, 0, Math.PI * 2); context.fill();
  }
  context.fillStyle = '#b9d4bc85';
  context.beginPath(); context.arc(px(length / 2), py(breadth / 2), 1.5, 0, Math.PI * 2); context.fill();
  // A reconnected page can resize before its new metadata arrives.
  if (!metadata) return;
  for (const ghost of ghosts) {
    if (outsideViewport(ghost)) continue;
    context.save();
    context.globalAlpha = Math.max(0, Math.min(1, ghost.alpha)) * .65;
    context.setLineDash([2.5, 3]);
    context.strokeStyle = metadata.slots[ghost.slot].side === 'H' ? '#5ee1be' : '#f6ae7f';
    context.lineWidth = 1.5;
    context.beginPath(); context.arc(px(ghost.x), py(ghost.y), 7.2, 0, Math.PI * 2); context.stroke();
    context.restore();
  }
  for (let index = 0; index < (positions?.length || 0); index += 1) {
    const point = positions[index];
    if (!point || outsideViewport(point)) continue;
    const isBall = index === metadata.slots.length;
    const radius = isBall ? 3.8 : 5.4;
    const color = isBall ? '#fff9e6' : metadata.slots[index].side === 'H' ? '#5ee1be' : '#f6ae7f';
    context.save();
    context.shadowColor = '#081d1b55'; context.shadowBlur = 4; context.shadowOffsetY = 2;
    context.beginPath(); context.arc(px(point.x), py(point.y), radius, 0, Math.PI * 2);
    context.fillStyle = color; context.fill();
    context.shadowBlur = 0; context.shadowOffsetY = 0;
    context.lineWidth = isBall ? 1.1 : 1.5; context.strokeStyle = point.jump ? '#f9d26c' : isBall ? '#29483d' : '#143c33';
    if (point.display === 'held') context.setLineDash([2, 2]);
    context.stroke(); context.setLineDash([]);
    if (isBall) {
      context.beginPath(); context.arc(px(point.x), py(point.y), 1.2, 0, Math.PI * 2); context.fillStyle = '#65766c'; context.fill();
    }
    if (!isBall && Number.isFinite(point.heading)) {
      context.strokeStyle = '#0d3a31'; context.lineWidth = 1.6;
      context.beginPath(); context.moveTo(px(point.x), py(point.y));
      context.lineTo(px(point.x) + Math.cos(point.heading) * 8, py(point.y) + Math.sin(point.heading) * 8);
      context.stroke();
    }
    context.restore();
  }
}

function outsideViewport(point) {
  const [length, breadth] = metadata.pitch;
  return point.x < -VIEW_PADDING_METRES || point.x > length + VIEW_PADDING_METRES ||
    point.y < -VIEW_PADDING_METRES || point.y > breadth + VIEW_PADDING_METRES;
}

function updateObservations(positions, row, ghosts) {
  const players = positions.slice(0, metadata.slots.length);
  const observed = players.filter(Boolean).length;
  const visible = players.filter(point => point && !outsideViewport(point)).length;
  const outsideView = positions.filter(point => point && outsideViewport(point)).length;
  const ball = positions[metadata.slots.length];
  const [length, breadth] = metadata.pitch;
  const outside = positions.filter(point => point && (point.x < 0 || point.x > length || point.y < 0 || point.y > breadth)).length;
  const jumps = positions.filter(point => point?.jump).length;
  ui['visible-slots'].textContent = String(visible);
  ui['catalog-size'].textContent = `${metadata.slots.length} anonymous slots · not a player count`;
  ui['ghost-slots'].textContent = String(ghosts.length);
  ui['missing-slots'].textContent = String(metadata.slots.length - observed);
  ui['missing-slots'].dataset.warning = 'false';
  ui['outside-slots'].textContent = String(players.filter(point => point && outsideViewport(point)).length);
  ui['outside-slots'].dataset.warning = String(outsideView > 0);
  ui['ball-status'].textContent = ball ? outsideViewport(ball) ? 'Outside view' :
    ball.display === 'interpolated' ? 'Interpolated display' : ball.display === 'held' ? 'Held sample' : 'Observed sample' : 'Unobserved';
  ui['ball-status'].dataset.warning = String(!ball || outsideViewport(ball));
  ui['bounds-status'].textContent = outside ? `${outside} off-pitch` : 'Within pitch';
  ui['bounds-status'].dataset.warning = String(outside > 0);
  const interpolated = positions.filter(point => point?.display === 'interpolated').length;
  const held = positions.filter(point => point?.display === 'held').length;
  ui['motion-note'].textContent = `${ui['motion-mode'].value === 'exact' ? 'Exact source samples.' : 'Bounded natural display.'} ` +
    `${interpolated} interpolated · ${held} held · ${jumps} adjacent discontinuities. ` +
    (ghosts.length ? `${ghosts.length} dashed last-seen markers are unobserved.` : 'No travel is invented across missing samples.');
  const codeNumber = row[metadata.row_floats - 1];
  const code = Number.isInteger(codeNumber) && codeNumber >= 0 && codeNumber <= 3 ? metadata.label_codes[codeNumber] : null;
  const values = { H: ['Home', 'Home possession · existing CSV label'], A: ['Away', 'Away possession · existing CSV label'],
    D: ['Dead ball', 'Dead-ball state · existing CSV label'], X: ['No answer', 'CSV label X · play state unspecified'] };
  ui.possession.textContent = code ? values[code][0] : 'No CSV overlay';
  ui['live-possession'].textContent = ui.possession.textContent;
  ui['live-possession'].dataset.code = code || '';
  ui.possession.dataset.code = code || '';
  ui['possession-detail'].textContent = code ? values[code][1] : 'No prediction label is available at this frame.';
}

function clearObservationReadout() {
  for (const id of ['visible-slots', 'missing-slots', 'outside-slots', 'bounds-status', 'ghost-slots']) ui[id].textContent = '—';
  ui['ball-status'].textContent = 'Buffering';
  ui.possession.textContent = '—';
  ui['live-possession'].textContent = '—';
  ui['live-possession'].dataset.code = '';
  ui.possession.dataset.code = '';
  ui['possession-detail'].textContent = 'Waiting for this frame’s coordinate window.';
}

function render(timestamp) {
  animationPending = false;
  if (!clock || failed) return;
  const state = timelineState(timestamp);
  const frame = state.frame;
  const fraction = state.position - frame;
  const nextFrame = Math.min(frame + 1, metadata.frames - 1);
  const row = store.row(frame);
  const needsNext = fraction > 0 && ui['motion-mode'].value === 'natural';
  const next = needsNext ? store.row(nextFrame) : null;
  ui.seek.value = String(frame);
  ui.clock.textContent = formatTime(state.position, metadata.fps);
  ui['frame-counter'].textContent = `FRAME ${frame.toLocaleString('en-US')} / ${(metadata.frames - 1).toLocaleString('en-US')}`;
  ui.pitch.dataset.frame = String(frame);
  updatePlayButton();
  if (!row || (needsNext && !next)) {
    lastPositions = null;
    lastGhosts = [];
    drawPitch(null);
    clearObservationReadout();
    setStatus('Buffering', 'buffering');
    stageMessage('Buffering coordinates', 'Playback time is preserved while this frame window loads.');
    if (!row) store.request(frame, true);
    if (needsNext && !next) store.request(nextFrame, true);
  } else {
    stageMessage();
    setStatus(state.ended ? 'End of recording' : state.playing ? 'Playing' : 'Paused');
    const previous = frame > 0 ? store.row(frame - 1) : null;
    const following = frame + 2 < metadata.frames ? store.row(frame + 2) : null;
    const motion = getDisplayMotion({ row, next: next || store.row(nextFrame), previous, following,
      fraction, slots: metadata.slots, fps: metadata.fps, mode: ui['motion-mode'].value });
    lastPositions = motion.positions;
    lastGhosts = ui['show-ghosts'].checked ? getGhosts({ frame: state.position, slots: metadata.slots,
      fps: metadata.fps, lookup: index => store.row(index), maxAgeSeconds: .24 }) : [];
    drawPitch(lastPositions, lastGhosts);
    updateObservations(lastPositions, row, lastGhosts);
    if (frame > 0) store.request(frame - 1);
    if (frame + 2 < metadata.frames) store.request(frame + 2);
    store.prefetch(frame);
  }
  if (state.playing) scheduleRender();
}

function scheduleRender() {
  if (animationPending || failed) return;
  animationPending = true;
  requestAnimationFrame(render);
}

function seekTo(frame) {
  if (!clock || failed) return;
  store.invalidate();
  lastGhosts = [];
  if (!comparison?.seek(frame)) clock.seek(frame);
  scheduleRender();
}

async function togglePlayback() {
  if (!clock || failed) return;
  if (await comparison?.toggle()) {
    updatePlayButton(); scheduleRender(); return;
  }
  const state = clock.snapshot();
  if (state.playing) clock.pause();
  else {
    if (state.ended) { store.invalidate(); clock.seek(0); }
    clock.play();
  }
  updatePlayButton();
  scheduleRender();
}

async function boot() {
  const epoch = ++bootEpoch;
  failed = false;
  disableControls(true);
  if (store) store.invalidate();
  pausePlayback();
  comparison?.suspend();
  lastPositions = null;
  lastGhosts = [];
  metadata = null;
  clock = null;
  store = null;
  drawPitch(null);
  setStatus('Connecting', 'buffering');
  stageMessage('Opening the replay', 'Waiting for metadata from the local viewer.');
  try {
    const meta = await boundedFetch('/api/replay', {}, response => {
      if (!response.ok) throw new Error('Replay metadata was unavailable.');
      return response.json();
    });
    if (epoch !== bootEpoch) return;
    if (meta.status === 'building') {
      setStatus('Preparing', 'buffering');
      stageMessage('Preparing coordinate cache', 'The local parser is preparing bounded replay windows. The recording will open when ready.');
      setTimeout(() => { if (epoch === bootEpoch) boot(); }, 1000);
      return;
    }
    if (meta.status === 'failed') {
      const reason = typeof meta.message === 'string' ? meta.message.slice(0, 240) : 'Replay preparation failed.';
      ui['mode-badge'].textContent = meta.mode === 'demo' ? 'Invented tracking · unavailable' : 'Supplied tracking · unavailable';
      showFailure(`${reason} Correct the problem and restart the launcher; Try again reconnects afterward.`);
      return;
    }
    metadata = validateMetadata(meta);
    store = new FrameStore(metadata);
    clock = createPlaybackClock({ fps: metadata.fps, frames: metadata.frames });
    clock.seek(metadata.initial_frame);
    ui.seek.max = String(metadata.frames - 1);
    ui.seek.value = String(metadata.initial_frame);
    ui.speed.value = '1';
    ui.duration.textContent = formatTime(metadata.frames - 1, metadata.fps);
    ui.fps.textContent = `${metadata.fps} FPS`;
    ui['pitch-size'].textContent = `${metadata.pitch[0]} × ${metadata.pitch[1]} m`;
    const mode = metadata.mode === 'demo' ? 'Invented tracking' : 'Supplied tracking';
    ui['mode-badge'].textContent = mode;
    ui['mode-badge'].classList.toggle('invented', metadata.mode === 'demo');
    ui['source-caption'].textContent = mode;
    ui['possession-detail'].textContent = metadata.predictions_ready ? 'Existing CSV overlay · read-only' : 'No predictions CSV is attached.';
    comparison?.refresh?.();
    disableControls(false);
    scheduleRender();
  } catch (_) {
    if (epoch === bootEpoch) showFailure();
  }
}

ui.play.addEventListener('click', togglePlayback);
ui.seek.addEventListener('input', () => seekTo(Number(ui.seek.value)));
ui.previous.addEventListener('click', () => {
  if (!clock) return;
  pausePlayback(); seekTo(timelineState().frame - 1);
});
ui.next.addEventListener('click', () => {
  if (!clock) return;
  pausePlayback(); seekTo(timelineState().frame + 1);
});
ui.speed.addEventListener('change', () => {
  if (!clock || failed) return;
  if (!comparison?.setSpeed(Number(ui.speed.value))) clock.setSpeed(Number(ui.speed.value));
  scheduleRender();
});
ui.retry.addEventListener('click', boot);
ui['motion-mode'].addEventListener('change', scheduleRender);
ui['show-ghosts'].addEventListener('change', scheduleRender);
document.addEventListener('keydown', event => {
  // The native video handles Space itself; routing it twice cancels playback.
  if (event.code !== 'Space' || event.altKey || event.ctrlKey || event.metaKey || event.repeat ||
      ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'SUMMARY', 'A', 'VIDEO'].includes(event.target.tagName)) return;
  event.preventDefault(); togglePlayback();
});
window.addEventListener('resize', () => { if (!clock || failed) drawPitch(lastPositions, lastGhosts); else scheduleRender(); });
function initializeComparison() {
  comparison?.destroy();
  $('video-panel').replaceChildren();
  comparison = createVideoComparison({ container: $('video-panel'),
    getReplay: () => clock && metadata && !failed ? { ...clock.snapshot(), fps: metadata.fps, frames: metadata.frames } : null,
    onChange: () => { updatePlayButton(); scheduleRender(); },
    onRelease: state => {
      if (!clock || !state) return;
      clock.pause(); clock.seek(state.position); clock.setSpeed(state.speed);
      scheduleRender();
    } });
}
window.addEventListener('pagehide', () => { bootEpoch += 1; store?.invalidate(); pausePlayback(); comparison?.destroy(); });
window.addEventListener('pageshow', event => { if (event.persisted) { initializeComparison(); boot(); } });
initializeComparison();
boot();
