/**
 * Hidden DOM contracts still used by the transplanted graph engine.
 * The PIXI view mounts in a separate sibling container.
 */
export function OmnixDomStubs() {
  return (
    <div
      className="pointer-events-none fixed left-0 top-0 z-0 m-0 h-px w-px overflow-hidden opacity-0"
      aria-hidden
    >
      <div id="loading-error" aria-live="polite">
        <div>
          <div className="msg" id="loading-error-msg" />
        </div>
      </div>

      <div id="entrance" className="skip-hint" title="Click to skip">
        <div className="ent-title" id="ent-title">
          OMNIX
        </div>
        <div className="ent-sub" id="ent-sub" />
      </div>

      <div id="ui-fade">
        <div id="fps-counter" />
        <div id="breadcrumb" />
        <div id="tooltip">
          <div className="tooltip-name" />
          <div className="tooltip-type" />
          <div className="tooltip-file" />
          <div className="tooltip-lines" />
        </div>
        <input type="text" id="search-input" readOnly tabIndex={-1} />
        <span id="search-count" />
        <div id="search-hint" style={{ display: "none" }} />
        <div className="stat-row">
          <span id="stat-files">0</span>
        </div>
        <span className="stat-val" id="stat-functions" />
        <span id="stat-classes" />
        <span id="stat-edges" />
        <span id="stat-dark" style={{ color: "#8b5cf6" }}>
          0
        </span>
        <span id="stat-entangled" style={{ color: "#f59e0b" }}>
          0
        </span>
        <div id="timeline-panel" style={{ display: "none" }}>
          <span id="timeline-date" />
          <span id="timeline-info" />
          <span id="timeline-stats" />
          <input type="range" id="timeline-slider" min="0" max="99" defaultValue="0" readOnly tabIndex={-1} />
          <span id="timeline-date-end" />
        </div>
        <button type="button" id="btn-fullscreen" title="fs" tabIndex={-1} />
        <button type="button" id="btn-dark-matter" title="dm" tabIndex={-1} />
        <button type="button" id="btn-timeline" style={{ display: "none" }} title="tl" tabIndex={-1} />
        <button type="button" id="btn-export" title="ex" tabIndex={-1} />
        <div id="xray-panel" style={{ display: "none" }}>
          <div id="xray-content" />
        </div>
        <input type="text" id="ai-question-input" readOnly tabIndex={-1} />
        <div id="ai-response" />
        <button type="button" id="xray-close" title="x" tabIndex={-1} />
        <button type="button" id="omnix-symbol-popup-close" title="c" tabIndex={-1} />
      </div>
    </div>
  );
}
