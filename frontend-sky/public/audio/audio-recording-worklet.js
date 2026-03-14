// Audio recording worklet — ports Float32 mic input to Int16 PCM chunks.
// Sends 2048-sample chunks (~128ms at 16kHz) to the main thread via postMessage.
// Ported from Project Livewire (Google).

class RecordingProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(2048);
    this.bufferIndex = 0;
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;

    for (let i = 0; i < input.length; i++) {
      this.buffer[this.bufferIndex++] = Math.max(
        -32768,
        Math.min(32767, input[i] * 32768)
      );
      if (this.bufferIndex >= 2048) {
        this.port.postMessage(
          { event: "chunk", data: { int16arrayBuffer: this.buffer.buffer } },
          [this.buffer.buffer]
        );
        this.buffer = new Int16Array(2048);
        this.bufferIndex = 0;
      }
    }
    return true;
  }
}

registerProcessor("recording-processor", RecordingProcessor);
