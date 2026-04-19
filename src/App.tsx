import { useState, useEffect, useCallback, useRef } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { getCurrentWindow } from "@tauri-apps/api/window";
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
        setStatus({ text: "Backend unavailable. Start the Python server.", level: "error" });
      }
    }, 500);
    return () => clearInterval(interval);
  }, []);

  // Tauri drag-drop integration
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    getCurrentWindow()
      .onDragDropEvent((event) => {
        if (event.payload.type === "over") {
          setIsDragging(true);
        } else if (event.payload.type === "drop") {
          setIsDragging(false);
          const paths = event.payload.paths ?? [];
          if (paths.length > 0) loadFiles(paths);
        } else {
          setIsDragging(false);
        }
      })
      .then((fn) => {
        unlisten = fn;
      });
    return () => unlisten?.();
  }, []);

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
    const paths = await open({
      multiple: true,
      title: "Open Unity Bundle Files",
    });
    if (!paths) return;
    const list = Array.isArray(paths) ? paths : [paths];
    if (list.length > 0) await loadFiles(list);
  }

  const updatePreview = useCallback(async (asset: Asset) => {
    previewAbortRef.current?.abort();
    const ctrl = new AbortController();
    previewAbortRef.current = ctrl;

    setPreviewLoading(true);
    setPreviewAssetName(asset.name);
    try {
      const data = await api.getPreview(asset.path_id);
      if (!ctrl.signal.aborted) {
        setPreview(data);
      }
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

    const dir = await open({ directory: true, title: "Select Export Folder" });
    if (!dir || typeof dir !== "string") return;

    setIsLoading(true);
    setStatus({ text: "Exporting…", level: "info" });
    try {
      const result = await api.exportAssets(exportable, dir);
      const msg =
        result.success_count === result.total
          ? `Exported ${result.success_count} asset(s) to ${dir}`
          : `Exported ${result.success_count}/${result.total} assets (check log for errors)`;
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

    const filters =
      asset.obj_type === "Texture2D"
        ? [{ name: "Image Files", extensions: ["png", "jpg", "jpeg", "bmp", "tga", "dds"] }]
        : [{ name: "All Files", extensions: ["*"] }];

    const path = await open({ multiple: false, filters, title: "Select Replacement File" });
    if (!path || typeof path !== "string") return;

    setIsLoading(true);
    setStatus({ text: `Replacing ${asset.name}…`, level: "info" });
    try {
      const result = await api.replaceAsset(asset.path_id, path);
      if (result.is_success) {
        // Refresh asset list and preview
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
      // Refresh asset list to update change flags
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
    const dir = await open({ directory: true, title: "Select Save Folder" });
    return typeof dir === "string" ? dir : null;
  }

  const selectedList = assets.filter((a) => selectedIds.has(a.path_id));
  const canExport = selectedList.some((a) => a.is_exportable);
  const canReplace = selectedList.length === 1 && selectedList[0].is_editable;
  const hasAssets = assets.length > 0;
  const hasChanges = assets.some((a) => a.is_changed);

  return (
    <div className={`app ${isDragging ? "drag-over" : ""}`}>
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
        {!backendReady && <span className="backend-warn">⚠ Backend not connected</span>}
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
