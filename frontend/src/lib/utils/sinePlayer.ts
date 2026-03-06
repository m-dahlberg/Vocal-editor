let _audioContext: AudioContext | null = null;
let _oscillator: OscillatorNode | null = null;
let _gainNode: GainNode | null = null;
let _isPlaying = false;
let _currentFreq = 440;

function init() {
  if (!_audioContext) {
    _audioContext = new AudioContext();
  }
}

export function play(frequency: number) {
  init();
  if (!_audioContext) return;

  if (_isPlaying) {
    if (_oscillator && frequency !== _currentFreq) {
      _oscillator.frequency.setValueAtTime(frequency, _audioContext.currentTime);
      _currentFreq = frequency;
    }
    return;
  }

  _oscillator = _audioContext.createOscillator();
  _gainNode = _audioContext.createGain();

  _oscillator.type = 'sine';
  _oscillator.frequency.setValueAtTime(frequency, _audioContext.currentTime);
  _currentFreq = frequency;

  _gainNode.gain.setValueAtTime(0.3, _audioContext.currentTime);

  _oscillator.connect(_gainNode);
  _gainNode.connect(_audioContext.destination);

  _oscillator.start();
  _isPlaying = true;
}

export function updateFrequency(frequency: number) {
  if (_oscillator && _isPlaying && _audioContext) {
    _oscillator.frequency.setTargetAtTime(frequency, _audioContext.currentTime, 0.01);
    _currentFreq = frequency;
  }
}

export function stop() {
  if (_oscillator && _isPlaying && _audioContext && _gainNode) {
    _gainNode.gain.setTargetAtTime(0, _audioContext.currentTime, 0.01);
    const osc = _oscillator;
    const gain = _gainNode;
    setTimeout(() => {
      osc.stop();
      osc.disconnect();
      gain.disconnect();
    }, 100);
    _oscillator = null;
    _gainNode = null;
    _isPlaying = false;
  }
}

export function isPlaying(): boolean {
  return _isPlaying;
}
