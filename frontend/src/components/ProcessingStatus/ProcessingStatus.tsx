import React from "react";
import styles from "./ProcessingStatus.module.css";
import { ProcessingState } from "../../hooks/useStatementProcessor";

interface ProcessingStatusProps {
  state: ProcessingState;
  progress: number;
  transactionCount?: number;
  errorMessage?: string;
}

const STATUS_CONFIG = {
  idle: { label: "", icon: "", color: "" },
  uploading: {
    label: "Uploading your statement...",
    icon: "⬆️",
    color: "#1976D2",
  },
  polling: {
    label: "Processing your statement...",
    icon: "⚙️",
    color: "#F57C00",
  },
  completed: {
    label: "Processing complete!",
    icon: "✅",
    color: "#388E3C",
  },
  error: { label: "Processing failed", icon: "❌", color: "#D32F2F" },
};

export const ProcessingStatus: React.FC<ProcessingStatusProps> = ({
  state,
  progress,
  transactionCount,
  errorMessage,
}) => {
  if (state === "idle") return null;

  const config = STATUS_CONFIG[state];

  return (
    <div className={styles.container} role="status" aria-live="polite">
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden="true">
          {config.icon}
        </span>
        <span className={styles.label} style={{ color: config.color }}>
          {config.label}
        </span>
      </div>

      {/* Progress Bar */}
      {(state === "uploading" || state === "polling") && (
        <div className={styles.progressContainer}>
          <div
            className={styles.progressBar}
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className={styles.progressFill}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className={styles.progressText}>{progress}%</span>
        </div>
      )}

      {/* Success Details */}
      {state === "completed" && transactionCount !== undefined && (
        <div className={styles.successDetails}>
          <p className={styles.successText}>
            🎉 Found{" "}
            <strong>{transactionCount.toLocaleString()}</strong> transactions
          </p>
          <p className={styles.successSubtext}>
            Your Excel report is ready for download
          </p>
        </div>
      )}

      {/* Error Message */}
      {state === "error" && errorMessage && (
        <div className={styles.errorDetails} role="alert">
          <p className={styles.errorText}>{errorMessage}</p>
        </div>
      )}

      {/* Animated Spinner */}
      {(state === "uploading" || state === "polling") && (
        <div className={styles.spinner} aria-hidden="true" />
      )}
    </div>
  );
};