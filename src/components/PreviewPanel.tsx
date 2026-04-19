import { useState, useRef } from "react";
import type { PreviewData } from "../types";
import "./PreviewPanel.css";

interface Props {
  preview: PreviewData | null;
  isLoading: boolean;
  assetName: string;
}

export default function PreviewPanel({ preview, isLoading, assetName }: Props) {
  const [zoom, setZoom] = useState(1);
  const [showParsed, setShowParsed] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  function handleWheel(e: React.WheelEvent) {
    if (preview?.type !== "Texture2D") return;
    e.preventDefault();
    setZoom((z) => Math.min(8, Math.max(0.1, z - e.deltaY * 0.001)));
  }

  function resetZoom() {
    setZoom(1);
  }

  if (isLoading) {
    return (
      <div className="preview-panel loading">
        <div className="spinner" />
        <span>Loading preview…</span>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="preview-panel empty">
        <span className="preview-hint">Select an asset to preview</span>
      </div>
    );
  }

  const hasParsed = !!preview.parsed_data?.trim();

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <span className="preview-title" title={assetName}>
          {assetName || "(unnamed)"}
        </span>
        <span className="preview-type">{preview.type}</span>
        {hasParsed && (
          <button
            className={`parsed-toggle ${showParsed ? "active" : ""}`}
            onClick={() => setShowParsed((s) => !s)}
          >
            {showParsed ? "Preview" : "Raw Data"}
          </button>
        )}
        {preview.type === "Texture2D" && !showParsed && (
          <div className="zoom-controls">
            <button onClick={() => setZoom((z) => Math.max(0.1, z - 0.25))}>−</button>
            <span className="zoom-label" onClick={resetZoom}>
              {Math.round(zoom * 100)}%
            </span>
            <button onClick={() => setZoom((z) => Math.min(8, z + 0.25))}>+</button>
          </div>
        )}
      </div>

      <div className="preview-content" onWheel={handleWheel}>
        {showParsed && hasParsed ? (
          <pre className="parsed-data">{preview.parsed_data}</pre>
        ) : preview.type === "Texture2D" && preview.image ? (
          <div className="image-container" style={{ transform: `scale(${zoom})` }}>
            <img ref={imgRef} src={preview.image} alt={assetName} draggable={false} />
          </div>
        ) : preview.type === "TextAsset" && preview.text !== undefined ? (
          <pre className="text-preview">{preview.text}</pre>
        ) : (
          <div className="preview-unsupported">
            <span>{preview.message || "Preview not available for this asset type"}</span>
            {hasParsed && (
              <button onClick={() => setShowParsed(true)}>View Raw Data</button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
