/* waveform.js - WaveSurfer playback with synchronized playhead */

const Waveform = (() => {
  let _ws = null;
  let _onTimeUpdate = null;
  let _duration = 0;

  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  }

  function init(onTimeUpdate) {
    _onTimeUpdate = onTimeUpdate;

    _ws = WaveSurfer.create({
      container: '#waveform',
      waveColor: '#2E86AB',
      progressColor: '#e94560',
      cursorColor: '#e94560',
      cursorWidth: 2,
      height: 60,
      normalize: true,
      interact: true,
      fillParent: true,
      backend: 'WebAudio',
      autoCenter: false,
    });

    _ws.on('ready', () => {
      _duration = _ws.getDuration();
      document.getElementById('totalTime').textContent = formatTime(_duration);
      document.getElementById('playTime').textContent = '0:00';
    });

    _ws.on('audioprocess', (t) => {
      document.getElementById('playTime').textContent = formatTime(t);
      if (_onTimeUpdate) _onTimeUpdate(t);
    });

    _ws.on('seek', (progress) => {
      const t = progress * _duration;
      document.getElementById('playTime').textContent = formatTime(t);
      if (_onTimeUpdate) _onTimeUpdate(t);
    });

    _ws.on('finish', () => {
      document.getElementById('btnPlay').textContent = '▶';
    });

    // Note: btnPlay and spacebar are handled by main.js to process dirty clusters first
    document.getElementById('btnStop').addEventListener('click', stop);
  }

  function togglePlay() {
    if (!_ws) return;
    if (_ws.isPlaying()) {
      _ws.pause();
      document.getElementById('btnPlay').textContent = '▶';
    } else {
      _ws.play();
      document.getElementById('btnPlay').textContent = '⏸';
    }
  }

  function stop() {
    if (!_ws) return;
    _ws.stop();
    document.getElementById('btnPlay').textContent = '▶';
    document.getElementById('playTime').textContent = '0:00';
    if (_onTimeUpdate) _onTimeUpdate(0);
  }

  function load(url) {
    if (!_ws) return;
    const wasPlaying = _ws.isPlaying();
    if (wasPlaying) _ws.pause();
    _ws.load(url);
  }

  function getCurrentTime() {
    return _ws ? _ws.getCurrentTime() : 0;
  }

  /**
   * Sync waveform view to match pitch plot x range.
   * xRange: [startSeconds, endSeconds]
   * totalDuration: full audio duration in seconds
   */
  function syncToRange(xRange, totalDuration) {
    if (!_ws || !totalDuration) return;
    const dur = totalDuration || _duration;
    if (!dur) return;

    const visibleDuration = xRange[1] - xRange[0];
    const containerWidth = document.getElementById('waveform').clientWidth;

    // Calculate required zoom (pixels per second) to show the visible range
    const pxPerSec = containerWidth / visibleDuration;

    // Apply zoom - WaveSurfer redraws at new scale
    _ws.zoom(pxPerSec);

    // After zoom, the total waveform width is pxPerSec * totalDuration
    // Scroll to show the correct portion
    const wrapper = _ws.getWrapper ? _ws.getWrapper() : null;
    if (wrapper && wrapper.parentElement) {
      // Calculate scroll position: start time * pixels per second
      const scrollLeft = xRange[0] * pxPerSec;
      wrapper.parentElement.scrollLeft = scrollLeft;
    }
  }

  function isPlaying() {
    return _ws ? _ws.isPlaying() : false;
  }

  return { init, load, togglePlay, stop, getCurrentTime, syncToRange, isPlaying };
})();
