/* Pure display helpers. Source observations, model inputs and CSVs are untouched. */
const PLAYER_DISPLAY_METRES_PER_SECOND = 15;
const BALL_DISPLAY_METRES_PER_SECOND = 75;
const MAX_GHOST_SECONDS = 0.24;
const MAX_GHOST_LOOKBACK_FRAMES = 120;
const MAX_PLAYER_SLOTS = 128;

function playerCount(slots) {
  const count = Array.isArray(slots) ? slots.length : slots;
  return Number.isInteger(count) && count >= 0 && count <= MAX_PLAYER_SLOTS ? count : 0;
}

function pointAt(row, slot) {
  const x = row?.[slot * 2];
  const y = row?.[slot * 2 + 1];
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
}

function displacement(from, to) {
  return from && to ? { x: to.x - from.x, y: to.y - from.y } : null;
}

function plausible(delta, limit) {
  return Boolean(delta && Number.isFinite(limit) && limit > 0 &&
    Math.hypot(delta.x, delta.y) <= limit);
}

// Equal-interval monotone Hermite slopes: sign changes flatten the tangent;
// matching measured secants use their harmonic mean. Missing/unusable adjacent
// observations fall back to this segment's measured secant, never extrapolation.
function tangent(adjacent, segment) {
  if (segment === 0) return 0;
  if (adjacent === null) return segment;
  if (adjacent === 0 || Math.sign(adjacent) !== Math.sign(segment)) return 0;
  // This form avoids multiplying very large coordinates together.
  return 2 / (1 / adjacent + 1 / segment);
}

function boundedSlopes(delta, before, after) {
  if (delta === 0) return { left: 0, right: 0 };
  let left = tangent(before, delta) / delta;
  let right = tangent(after, delta) / delta;
  // The monotone-circle limiter bounds even extreme/roundoff-sensitive slopes.
  left = Number.isFinite(left) ? Math.max(0, left) : 0;
  right = Number.isFinite(right) ? Math.max(0, right) : 0;
  const norm = Math.hypot(left, right);
  if (norm > 3) {
    left *= 3 / norm;
    right *= 3 / norm;
  }
  return { left, right };
}

function speedBoundedSlopes(segment, prior, later, limit) {
  const x = boundedSlopes(segment.x, prior ? prior.x : null, later ? later.x : null);
  const y = boundedSlopes(segment.y, prior ? prior.y : null, later ? later.y : null);
  const left = { x: segment.x * x.left, y: segment.y * y.left };
  const right = { x: segment.x * x.right, y: segment.y * y.right };
  const middle = { x: 3 * segment.x - left.x - right.x,
    y: 3 * segment.y - left.y - right.y };
  // A cubic Bezier's derivative is a convex combination of these three vectors.
  // Bounding every control-vector norm bounds instantaneous display speed for
  // the entire interval. If this sufficient test fails, use the measured linear
  // segment, whose speed was already checked. Endpoints/bounds stay unchanged.
  if (![left, middle, right].every(delta => plausible(delta, limit))) {
    return { x: { left: 1, right: 1 }, y: { left: 1, right: 1 } };
  }
  return { x, y };
}

function boundedCubic(start, end, slopes, fraction) {
  const delta = end - start;
  if (delta === 0) return start;
  const { left, right } = slopes;
  const t = fraction;
  const t2 = t * t;
  const t3 = t2 * t;
  // Work in segment units instead of weighting absolute pitch coordinates.
  const progress = (-2 * t3 + 3 * t2) +
    (t3 - 2 * t2 + t) * left + (t3 - t2) * right;
  const boundedProgress = Math.max(0, Math.min(1, progress));
  return Math.max(Math.min(start, end), Math.min(Math.max(start, end),
    start + delta * boundedProgress));
}

/**
 * Rows contain x,y pairs in slot-array order, followed by the ball pair.
 * Return {positions, counters}; each position is null or
 * {x,y,jump,display,heading}. display is observed, interpolated, or held;
 * heading is null or radians of plausible measured displacement, not facing.
 * Counters include the ball. Current missing/partial pairs always remain null.
 * Natural mode preserves both finite endpoints. Exact mode holds the source
 * sample, snapping at fraction=1. The normal replay fraction is in [0,1).
 */
export function getDisplayMotion({ row, next, previous, following, fraction = 0,
  slots, fps, mode = 'natural' } = {}) {
  const count = playerCount(slots);
  const t = Number.isFinite(fraction) ? Math.max(0, Math.min(1, fraction)) : 0;
  const validFps = Number.isFinite(fps) && fps > 0;
  const counters = { observed: 0, missing: 0, interpolated: 0, held: 0, jumps: 0 };
  const positions = Array.from({ length: count + 1 }, (_, slot) => {
    const current = pointAt(row, slot);
    if (!current) {
      counters.missing += 1;
      return null;
    }
    counters.observed += 1;
    const future = pointAt(next, slot);
    const past = pointAt(previous, slot);
    const after = pointAt(following, slot);
    const limit = validFps ? (slot === count ? BALL_DISPLAY_METRES_PER_SECOND :
      PLAYER_DISPLAY_METRES_PER_SECOND) / fps : NaN;
    const segment = displacement(current, future);
    const prior = displacement(past, current);
    const later = displacement(future, after);
    const usableSegment = plausible(segment, limit);
    const usablePrior = plausible(prior, limit);
    const usableLater = plausible(later, limit);
    // Inspect source adjacency even when paused exactly on a sample. Neither
    // current nulls nor missing neighbors are fabricated into discontinuities.
    const isJump = delta => Boolean(delta && validFps && !plausible(delta, limit));
    const jump = t === 1 && future ? isJump(segment) || isJump(later) :
      isJump(prior) || isJump(segment);
    if (jump) counters.jumps += 1;

    const measured = t === 1 && future ?
      (usableLater ? later : usableSegment ? segment : null) :
      (usableSegment ? segment : usablePrior ? prior : null);
    const heading = measured && Math.hypot(measured.x, measured.y) > 0 ?
      Math.atan2(measured.y, measured.x) : null;
    let x = current.x;
    let y = current.y;
    let display = t === 0 ? 'observed' : 'held';
    if (t === 1 && future) {
      x = future.x;
      y = future.y;
      display = 'observed';
    } else if (t > 0 && mode === 'natural' && usableSegment) {
      const slopes = speedBoundedSlopes(segment, usablePrior ? prior : null,
        usableLater ? later : null, limit);
      x = boundedCubic(current.x, future.x, slopes.x, t);
      y = boundedCubic(current.y, future.y, slopes.y, t);
      display = 'interpolated';
    }
    if (display === 'interpolated') counters.interpolated += 1;
    if (display === 'held') counters.held += 1;
    return { x, y, jump, display, heading };
  });
  return { positions, counters };
}

/**
 * Stationary, display-only missing-player ghosts; never the ball. `slot` is the
 * zero-based index into the supplied slots array, not its catalog identifier.
 * lookup(integerFrame) returns a source row or null. An unavailable row stops
 * history lookup. This function keeps no state, so seeking/source replacement
 * cannot retain ghosts from a previous call. Do not count ghosts as observations.
 */
export function getGhosts({ frame, slots, fps, lookup,
  maxAgeSeconds = MAX_GHOST_SECONDS } = {}) {
  const count = playerCount(slots);
  if (!Number.isFinite(frame) || frame < 0 || !Number.isSafeInteger(Math.floor(frame)) ||
      !Number.isFinite(fps) || fps <= 0 || typeof lookup !== 'function' ||
      !Number.isFinite(maxAgeSeconds) || maxAgeSeconds <= 0 || count === 0) return [];
  const currentFrame = Math.floor(frame);
  const ageLimit = Math.min(MAX_GHOST_SECONDS, maxAgeSeconds);
  // An absolute frame bound also protects against malicious/extreme FPS values.
  const lookback = Math.min(MAX_GHOST_LOOKBACK_FRAMES, currentFrame,
    Math.floor(ageLimit * fps));
  if (lookback < 1) return [];
  const current = lookup(currentFrame);
  if (!current) return [];
  const pending = new Set();
  for (let slot = 0; slot < count; slot += 1) {
    if (!pointAt(current, slot)) pending.add(slot);
  }
  const ghosts = [];
  for (let distance = 1; distance <= lookback && pending.size; distance += 1) {
    const ageSeconds = (frame - (currentFrame - distance)) / fps;
    if (ageSeconds > ageLimit) break;
    const past = lookup(currentFrame - distance);
    if (!past) break;
    for (const slot of pending) {
      const point = pointAt(past, slot);
      if (!point) continue;
      ghosts.push({ slot, x: point.x, y: point.y, ageSeconds,
        alpha: 0.18 + 0.32 * (1 - ageSeconds / ageLimit) });
      pending.delete(slot);
    }
  }
  return ghosts;
}
