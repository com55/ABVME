import { useState, useEffect, useCallback, useRef } from "react";
import { isTauri, pickFiles, onFileDrop, onDragOver } from "./tauri-compat";
import type { Asset, PreviewData, StatusMessage, SourceFile, CompressionType } from "./types";
import * as api from "./api";
import AssetTable from "./components/AssetTable";
import PreviewPanel from "./components/PreviewPanel";
import StatusBar from "./components/StatusBar";
import SaveDialog from "./components/SaveDialog";
import "./App.css";

export default function App() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewAssetName, setPreviewAssetName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<StatusMessage>({ text: "Ready", level: "info" });
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [sourceFiles, setSourceFiles] = useState<SourceFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  const previewAbortRef = useRef<AbortController | null>(null);

  // Wait for backend to be ready on startup
  useEffect(() => {
    let tries = 0;
    const maxTries = 30;
    const interval = setInterval(async () => {
      const ok = await api.checkHealth();
      if (ok) {
        clearInterval(interval);
        setBackendReady(true);
        setStatus({ text: "Ready", level: "info" });
      } else if (++tries >= maxTries) {
        clearInterval(interval);
        setStatus({ text: "Backend not connected — run: python backend.py", level: "error" });
      }
    }, 500);
    return () => clearInterval(interval);
  }, []);

  // Tauri drag-drop integration (no-op in browser)
  useEffect(() => {
    let unlistenDrop: (() => void) | undefined;
    let unlistenOver: (() => void) | undefined;

    onFileDrop((paths) => loadFiles(paths)).then((fn) => {
      unlistenDrop = fn;
    });
    onDragOver(
      () => setIsDragging(true),
      () => setIsDragging(false)
    ).then((fn) => {
      unlistenOver = fn;
    });

    return () => {
      unlistenDrop?.();
      unlistenOver?.();
    };
  }, []);

  // Browser drag-drop fallback (using file paths shown in status — files can't yield
  // real paths in browser security model, so we show a hint instead)
  function handleBrowserDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (isTauri()) return; // handled by Tauri event above
    setStatus({
      text: "Drag-and-drop paths require Tauri. Use the Load Files button instead.",
      level: "warning",
    });
  }

  async function loadFiles(paths: string[]) {
    if (!backendReady) return;
    setIsLoading(true);
    setStatus({ text: `Loading ${paths.length} file(s)…`, level: "info" });
    try {
      const result = await api.loadFiles(paths);
      setAssets(result.assets);
      setSelectedIds(new Set());
      setPreview(null);
      setStatus({
        text: `Loaded ${result.assets.length} assets from ${result.file_count} file(s)`,
        level: "info",
      });
    } catch (err) {
      setStatus({ text: `Load failed: ${err}`, level: "error" });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleOpenFiles() {
    if (!isTauri()) {
      // In browser: show a prompt asking the user to type the path,
      // since browser security blocks real file paths
      const path = window.prompt(
        "Enter the full path(s) to the bundle file(s), separated by commas:"
      );
      if (!path?.trim()) return;
      const paths = path.split(",").map((p) => p.trim()).filter(Boolean);
      if (paths.length > 0) await loadFiles(paths);
      return;
    }

    const paths = await pickFiles({ multiple: true, title: "Open Unity Bundle Files" });
    if (paths && paths.length > 0) await loadFiles(paths);
  }

  const updatePreview = useCallback(async (asset: Asset) => {
    previewAbortRef.current?.abort();
    const ctrl = new AbortController();
    previewAbortRef.current = ctrl;

    setPreviewLoading(true);
    setPreviewAssetName(asset.name);
    try {
      const data = await api.getPreview(asset.path_id);
      if (!ctrl.signal.aborted) setPreview(data);
    } catch {
      if (!ctrl.signal.aborted) setPreview(null);
    } finally {
      if (!ctrl.signal.aborted) setPreviewLoading(false);
    }
  }, []);

  function handleSelectionChange(ids: Set<string>) {
    setSelectedIds(ids);
    if (ids.size === 1) {
      const asset = assets.find((a) => a.path_id === [...ids][0]);
      if (asset) updatePreview(asset);
    } else {
      setPreview(null);
      setPreviewAssetName("");
    }
  }

  async function handleExport() {
    const exportable = [...selectedIds].filter(
      (id) => assets.find((a) => a.path_id === id)?.is_exportable
    );
    if (exportable.length === 0) return;

    let dir: string | null = null;
    if (isTauri()) {
      const result = await pickFiles({ directory: true, title: "Select Export Folder" });
      dir = result?.[0] ?? null;
    } else {
      dir = window.prompt("Enter the full path to the export folder:");
    }
    if (!dir) return;

    setIsLoading(true);
    setStatus({ text: "Exporting…", level: "info" });
    try {
      const result = await api.exportAssets(exportable, dir);
      const msg =
        result.success_count === result.total
          ? `Exported ${result.success_count} asset(s) to ${dir}`
          : `Exported ${result.success_count}/${result.total} assets (some failed)`;
      setStatus({ text: msg, level: result.success_count === result.total ? "info" : "warning" });
    } catch (err) {
      setStatus({ text: `Export failed: ${err}`, level: "error" });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleReplace() {
    if (selectedIds.size !== 1) return;
    const asset = assets.find((a) => a.path_id === [...selectedIds][0]);
    if (!asset?.is_editable) return;

    let path: string | null = null;
    if (isTauri()) {
      const filters =
        asset.obj_type === "Texture2D"
          ? [{ name: "Image Files", extensions: ["png", "jpg", "jpeg", "bmp", "tga", "dds"] }]
          : [{ name: "All Files", extensions: ["*"] }];
      const result = await pickFiles({ multiple: false, filters, title: "Select Replacement File" });
      path = result?.[0] ?? null;
    } else {
      path = window.prompt("Enter the full path to the replacement file:");
    }
    if (!path) return;

    setIsLoading(true);
    setStatus({ text: `Replacing ${asset.name}…`, level: "info" });
    try {
      const result = await api.replaceAsset(asset.path_id, path);
      if (result.is_success) {
        const refreshed = await api.getAssets();
        setAssets(refreshed.assets);
        await updatePreview(asset);
        setStatus({ text: result.message || "Asset replaced successfully", level: "info" });
      } else {
        setStatus({ text: result.message || "Replace failed", level: "error" });
      }
    } catch (err) {
      setStatus({ text: `Replace failed: ${err}`, level: "error" });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleOpenSaveDialog() {
    try {
      const { files } = await api.getSourceFiles();
      setSourceFiles(files);
      setShowSaveDialog(true);
    } catch (err) {
      setStatus({ text: `Failed to get source files: ${err}`, level: "error" });
    }
  }

  async function handleSave(outputDir: string, packer: CompressionType) {
    setShowSaveDialog(false);
    setIsLoading(true);
    setStatus({ text: "Saving bundle…", level: "info" });
    try {
      await api.saveBundle(outputDir, packer);
      const refreshed = await api.getAssets();
      setAssets(refreshed.assets);
      setStatus({ text: `Bundle saved to ${outputDir}`, level: "info" });
    } catch (err) {
      setStatus({ text: `Save failed: ${err}`, level: "error" });
    } finally {
      setIsLoading(false);
    }
  }

  async function handlePickSaveDir(): Promise<string | null> {
    if (isTauri()) {
      const result = await pickFiles({ directory: true, title: "Select Save Folder" });
      return result?.[0] ?? null;
    }
    return window.prompt("Enter the full path to the save folder:");
  }

  const selectedList = assets.filter((a) => selectedIds.has(a.path_id));
  const canExport = selectedList.some((a) => a.is_exportable);
  const canReplace = selectedList.length === 1 && selectedList[0].is_editable;
  const hasAssets = assets.length > 0;
  const hasChanges = assets.some((a) => a.is_changed);

  return (
    <div
      className={`app ${isDragging ? "drag-over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); if (!isTauri()) setIsDragging(true); }}
      onDragLeave={() => { if (!isTauri()) setIsDragging(false); }}
      onDrop={handleBrowserDrop}
    >
      {/* Toolbar */}
      <div className="toolbar">
        <span className="app-title">ABVME</span>
        <div className="toolbar-actions">
          <button onClick={handleOpenFiles} disabled={isLoading || !backendReady}>
            Load Files
          </button>
          <div className="separator" />
          <button onClick={handleExport} disabled={!canExport || isLoading}>
            Export
          </button>
          <button onClick={handleReplace} disabled={!canReplace || isLoading}>
            Replace
          </button>
          <div className="separator" />
          <button
            className={hasChanges ? "primary" : ""}
            onClick={handleOpenSaveDialog}
            disabled={!hasAssets || isLoading}
          >
            Save Bundle
          </button>
        </div>
        {!backendReady && (
          <span className="backend-warn">⚠ Run: python backend.py</span>
        )}
      </div>

      {/* Main Content */}
      <div className="main-content">
        <div className="left-panel">
          <AssetTable
            assets={assets}
            selectedIds={selectedIds}
            onSelectionChange={handleSelectionChange}
          />
        </div>
        <div className="divider" />
        <div className="right-panel">
          <PreviewPanel
            preview={preview}
            isLoading={previewLoading}
            assetName={previewAssetName}
          />
        </div>
      </div>

      {/* Status bar */}
      <StatusBar status={status} isLoading={isLoading} />

      {/* Drag overlay */}
      {isDragging && (
        <div className="drag-overlay">
          <div className="drag-message">Drop bundle files to load</div>
        </div>
      )}

      {/* Save dialog */}
      {showSaveDialog && (
        <SaveDialog
          sourceFiles={sourceFiles}
          onSave={handleSave}
          onCancel={() => setShowSaveDialog(false)}
          onPickDir={handlePickSaveDir}
        />
      )}
    </div>
  );
}
