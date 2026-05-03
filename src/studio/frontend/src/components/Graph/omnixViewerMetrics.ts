/** Last FPS sample from the Pixi main ticker (updated ~2 Hz). 0 = not sampled yet. */
let omnixFpsSample = 0;

export function setOmnixFpsSample(n: number) {
  omnixFpsSample = n;
}

export function getOmnixFpsSample() {
  return omnixFpsSample;
}
