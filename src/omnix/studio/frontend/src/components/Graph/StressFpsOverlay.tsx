import { useEffect, useState } from "react";
import type { GalaxyStressTier } from "./galaxyStressHarness";
import { getActiveGalaxyStressTier } from "./galaxyStressHarness";
import { getOmnixFpsSample } from "./omnixViewerMetrics";

/**
 * Bottom-right FPS readout when ?stress= is active (samples Pixi main ticker rate).
 */
export function StressFpsOverlay() {
  const [tier, setTier] = useState<GalaxyStressTier | null>(() =>
    getActiveGalaxyStressTier()
  );
  const [fps, setFps] = useState(() => getOmnixFpsSample());

  useEffect(() => {
    const id = window.setInterval(() => {
      setTier(getActiveGalaxyStressTier());
      setFps(getOmnixFpsSample());
    }, 500);
    return () => window.clearInterval(id);
  }, []);

  if (!tier) return null;

  const color =
    fps >= 55 ? "#4ad9c8" : fps >= 30 ? "#e67e22" : "#e74c3c";

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[9999] rounded px-3 py-1.5 font-mono text-sm font-bold"
      style={{
        background: "rgba(0, 0, 0, 0.7)",
        color,
      }}
      data-slice="18a-lite.1-stress-fps"
    >
      FPS: {fps} · stress={tier}
    </div>
  );
}
