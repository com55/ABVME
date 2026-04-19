import type { Asset, PreviewData, SourceFile, CompressionType } from "./types";

const BASE = "http://127.0.0.1:8765";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text);
  }
  return res.json() as Promise<T>;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export async function checkHealth(): Promise<boolean> {
  try {
    await request("/health");
    return true;
  } catch {
    return false;
  }
}

export async function loadFiles(paths: string[]): Promise<{ assets: Asset[]; file_count: number }> {
  return request("/api/load", json({ paths }));
}

export async function getAssets(): Promise<{ assets: Asset[] }> {
  return request("/api/assets");
}

export async function getPreview(pathId: string): Promise<PreviewData> {
  return request(`/api/asset/${pathId}/preview`);
}

export async function exportAssets(
  pathIds: string[],
  outputDir: string
): Promise<{ success_count: number; total: number }> {
  return request("/api/assets/export", json({ path_ids: pathIds, output_dir: outputDir }));
}

export async function replaceAsset(
  pathId: string,
  sourcePath: string
): Promise<{ status: string; message: string; is_success: boolean }> {
  return request(`/api/asset/${pathId}/replace`, json({ source_path: sourcePath }));
}

export async function getSourceFiles(): Promise<{ files: SourceFile[] }> {
  return request("/api/source-files");
}

export async function saveBundle(
  outputDir: string,
  packer: CompressionType
): Promise<{ status: string }> {
  return request("/api/save", json({ output_dir: outputDir, packer }));
}

export async function resetState(): Promise<void> {
  await request("/api/reset", { method: "POST" });
}
