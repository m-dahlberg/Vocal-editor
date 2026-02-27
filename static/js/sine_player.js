/* sine_player.js - Web Audio API sine wave generator for preview */

const SinePlayer = (() => {
  let _audioContext = null;
  let _oscillator = null;
  let _gainNode = null;
  let _isPlaying = false;
  let _currentFreq = 440;

  function init() {
    // Create audio context lazily (on first use)
    if (!_audioContext) {
      _audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
  }

  function play(frequency) {
    init();

    if (_isPlaying) {
      // Just update frequency if already playing
      if (_oscillator && frequency !== _currentFreq) {
        _oscillator.frequency.setValueAtTime(frequency, _audioContext.currentTime);
        _currentFreq = frequency;
      }
      return;
    }

    // Create oscillator and gain
    _oscillator = _audioContext.createOscillator();
    _gainNode = _audioContext.createGain();

    _oscillator.type = 'sine';
    _oscillator.frequency.setValueAtTime(frequency, _audioContext.currentTime);
    _currentFreq = frequency;

    // Set volume to reasonable level
    _gainNode.gain.setValueAtTime(0.3, _audioContext.currentTime);

    // Connect: oscillator -> gain -> output
    _oscillator.connect(_gainNode);
    _gainNode.connect(_audioContext.destination);

    _oscillator.start();
    _isPlaying = true;
  }

  function updateFrequency(frequency) {
    if (_oscillator && _isPlaying) {
      // Smooth frequency change over 50ms to avoid clicks
      _oscillator.frequency.setTargetAtTime(frequency, _audioContext.currentTime, 0.01);
      _currentFreq = frequency;
    }
  }

  function stop() {
    if (_oscillator && _isPlaying) {
      // Fade out over 50ms to avoid clicks
      _gainNode.gain.setTargetAtTime(0, _audioContext.currentTime, 0.01);
      setTimeout(() => {
        if (_oscillator) {
          _oscillator.stop();
          _oscillator.disconnect();
          _gainNode.disconnect();
          _oscillator = null;
          _gainNode = null;
        }
      }, 100);
      _isPlaying = false;
    }
  }

  function isPlaying() {
    return _isPlaying;
  }

  return { play, updateFrequency, stop, isPlaying };
})();
