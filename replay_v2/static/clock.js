/** Monotonic, anchor-based playback. Timestamps are milliseconds, positions frames.
 * No callback-time clamp: delayed animation callbacks retain all elapsed time.
 */
export class PlaybackClock {
  constructor({ fps, frames, now = () => performance.now() }) {
    if (!(Number.isFinite(fps) && fps > 0) || !Number.isInteger(frames) || frames < 1) {
      throw new RangeError('A positive frame rate and frame count are required.');
    }
    this.fps = fps;
    this.lastFrame = frames - 1;
    this.now = now;
    this.anchorFrame = 0;
    this.anchorTime = now();
    this.speed = 1;
    this.playing = false;
  }

  snapshot(timestamp = this.now()) {
    const elapsed = Math.max(0, timestamp - this.anchorTime) / 1000;
    const position = Math.min(this.lastFrame, Math.max(0,
      this.anchorFrame + (this.playing ? elapsed * this.fps * this.speed : 0)));
    if (this.playing && position >= this.lastFrame) {
      this.anchorFrame = this.lastFrame;
      this.anchorTime = timestamp;
      this.playing = false;
    }
    return { position, frame: Math.floor(position), playing: this.playing,
      speed: this.speed, ended: position >= this.lastFrame };
  }

  play(timestamp = this.now()) {
    const state = this.snapshot(timestamp);
    this.anchorFrame = state.position;
    this.anchorTime = timestamp;
    this.playing = this.anchorFrame < this.lastFrame;
    return this.snapshot(timestamp);
  }

  pause(timestamp = this.now()) {
    this.anchorFrame = this.snapshot(timestamp).position;
    this.anchorTime = timestamp;
    this.playing = false;
    return this.snapshot(timestamp);
  }

  seek(position, timestamp = this.now()) {
    if (!Number.isFinite(position)) throw new RangeError('A finite frame is required.');
    this.anchorFrame = Math.max(0, Math.min(this.lastFrame, position));
    this.anchorTime = timestamp;
    if (this.anchorFrame >= this.lastFrame) this.playing = false;
    return this.snapshot(timestamp);
  }

  setSpeed(speed, timestamp = this.now()) {
    if (!(Number.isFinite(speed) && speed > 0)) throw new RangeError('A positive speed is required.');
    this.anchorFrame = this.snapshot(timestamp).position;
    this.anchorTime = timestamp;
    this.speed = speed;
    return this.snapshot(timestamp);
  }
}

export function createPlaybackClock(options) { return new PlaybackClock(options); }
