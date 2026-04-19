import { useState } from "react";
import type { CompressionType, SourceFile } from "../types";
import "./SaveDialog.css";

interface Props {
  sourceFiles: SourceFile[];
  onSave: (outputDir: string, packer: CompressionType) => void;
  onCancel: () => void;
  onPickDir: () => Promise<string | null>;
}

export default function SaveDialog({ sourceFiles, onSave, onCancel, onPickDir }: Props) {
  const [outputDir, setOutputDir] = useState("");
  const [packer, setPacker] = useState<CompressionType>("none");

  const changedFiles = sourceFiles.filter((f) => f.is_changed);

  async function handlePickDir() {
    const dir = await onPickDir();
    if (dir) setOutputDir(dir);
  }

  function handleSave() {
    if (!outputDir.trim()) return;
    onSave(outputDir.trim(), packer);
  }

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <span>Save Bundle</span>
          <button className="close-btn" onClick={onCancel}>×</button>
        </div>

        <div className="dialog-body">
          {changedFiles.length > 0 && (
            <div className="changed-files">
              <div className="label">Modified files:</div>
              {changedFiles.map((f) => (
                <div key={f.path} className="changed-file-name" title={f.path}>
                  {f.name}
                </div>
              ))}
            </div>
          )}

          <div className="field">
            <label>Output Directory</label>
            <div className="dir-row">
              <input
                type="text"
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                placeholder="Select output folder…"
              />
              <button onClick={handlePickDir}>Browse</button>
            </div>
          </div>

          <div className="field">
            <label>Compression</label>
            <select value={packer} onChange={(e) => setPacker(e.target.value as CompressionType)}>
              <option value="none">None (fastest)</option>
              <option value="lz4">LZ4</option>
              <option value="lzma">LZMA (smallest)</option>
              <option value="original">Original</option>
            </select>
          </div>
        </div>

        <div className="dialog-footer">
          <button onClick={onCancel}>Cancel</button>
          <button className="primary" onClick={handleSave} disabled={!outputDir.trim()}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
