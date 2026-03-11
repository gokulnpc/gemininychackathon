class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.current = null;
    this.offset = 0;

    this.port.onmessage = (event) => {
      const data = event.data || {};
      if (data.type === "push" && data.samples) {
        this.queue.push(data.samples);
      } else if (data.type === "clear") {
        this.queue = [];
        this.current = null;
        this.offset = 0;
      }
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    const channel = output[0];
    channel.fill(0);

    let writeIndex = 0;
    while (writeIndex < channel.length) {
      if (!this.current) {
        this.current = this.queue.shift() || null;
        this.offset = 0;
        if (!this.current) {
          break;
        }
      }

      const remaining = this.current.length - this.offset;
      const toCopy = Math.min(remaining, channel.length - writeIndex);
      channel.set(this.current.subarray(this.offset, this.offset + toCopy), writeIndex);
      this.offset += toCopy;
      writeIndex += toCopy;

      if (this.offset >= this.current.length) {
        this.current = null;
        this.offset = 0;
      }
    }

    return true;
  }
}

registerProcessor("pcm-player-processor", PCMPlayerProcessor);
