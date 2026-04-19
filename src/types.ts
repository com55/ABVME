export interface Asset {
  path_id: string;
  name: string;
  container: string;
  obj_type: string;
  source_path: string;
  is_changed: boolean;
  is_editable: boolean;
  is_exportable: boolean;
}

export interface PreviewData {
  type: string;
  status: string;
  image?: string;
  text?: string;
  parsed_data?: string;
  message?: string;
}

export interface SourceFile {
  path: string;
  name: string;
  is_changed: boolean;
}

export type CompressionType = "none" | "lz4" | "lzma" | "original";

export interface StatusMessage {
  text: string;
  level: "info" | "warning" | "error";
}
