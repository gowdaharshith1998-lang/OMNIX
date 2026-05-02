/** Last FPS sample from the Pixi main ticker (updated ~2 Hz). */
let omnixFpsSample = 60;

export function setOmnixFpsSample(n: number) {
  omnixFpsSample = n;
}

export function getOmnixFpsSample() {
  return omnixFpsSample;
}
