import type { StatusMessage } from "../types";
import "./StatusBar.css";

interface Props {
  status: StatusMessage;
  isLoading: boolean;
  progress?: { current: number; total: number; label: string } | null;
}

export default function StatusBar({ status, isLoading, progress }: Props) {
  return (
    <div className={`status-bar level-${status.level}`}>
      {isLoading && progress ? (
        <>
          <div className="progress-bar-wrap">
            <div
              className="progress-bar-fill"
              style={{ width: `${(progress.current / Math.max(progress.total, 1)) * 100}%` }}
            />
          </div>
          <span className="status-text">
            {progress.label} ({progress.current}/{progress.total})
          </span>
        </>
      ) : (
        <>
          {isLoading && <div className="mini-spinner" />}
          <span className="status-text">{status.text}</span>
        </>
      )}
    </div>
  );
}
