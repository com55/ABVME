/**
 * Utilities to safely use Tauri APIs when running inside a Tauri window.
 * Falls back to browser-native alternatives when running in a plain browser.
 */

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Open a file picker. Returns selected path(s) or null. */
export async function pickFiles(opts: {
  multiple?: boolean;
  directory?: boolean;
  filters?: { name: string; extensions: string[] }[];
  title?: string;
}): Promise<string[] | null> {
  if (isTauri()) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const result = await open({
      multiple: opts.multiple ?? false,
      directory: opts.directory ?? false,
      filters: opts.filters,
      title: opts.title,
    });
    if (!result) return null;
    return Array.isArray(result) ? result : [result];
  }

  // Browser fallback: hidden file input
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    if (opts.multiple) input.multiple = true;
    if (opts.filters) {
      input.accept = opts.filters
        .flatMap((f) => f.extensions.map((e) => (e === "*" ? "*" : `.${e}`)))
        .join(",");
    }
    input.onchange = () => {
      const files = Array.from(input.files ?? []);
      resolve(files.length > 0 ? files.map((f) => f.name) : null);
    };
    input.oncancel = () => resolve(null);
    input.click();
  });
}

/** Subscribe to Tauri window drag-drop events. No-op in browser. */
export async function onFileDrop(
  callback: (paths: string[]) => void
): Promise<() => void> {
  if (!isTauri()) return () => {};

  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const unlisten = await getCurrentWindow().onDragDropEvent((event) => {
      if (event.payload.type === "drop") {
        const paths = (event.payload as { paths?: string[] }).paths ?? [];
        if (paths.length > 0) callback(paths);
      }
    });
    return unlisten;
  } catch {
    return () => {};
  }
}

/** Returns "over" / "leave" drag state updates. No-op in browser. */
export async function onDragOver(
  onOver: () => void,
  onLeave: () => void
): Promise<() => void> {
  if (!isTauri()) return () => {};

  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const unlisten = await getCurrentWindow().onDragDropEvent((event) => {
      if (event.payload.type === "over") onOver();
      else onLeave();
    });
    return unlisten;
  } catch {
    return () => {};
  }
}
