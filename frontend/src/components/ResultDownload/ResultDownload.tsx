import React, { useState } from "react";
import styles from "./ResultDownload.module.css";

interface ResultDownloadProps {
  onDownload: () => Promise<void>;
  onReset: () => void;
  transactionCount?: number;
  filename?: string;
}

export const ResultDownload: React.FC<ResultDownloadProps> = ({
  onDownload,
  onReset,
  transactionCount,
  filename,
}) => {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleDownload = async () => {
    setIsDownloading(true);
    setDownloadError(null);

    try {
      await onDownload();
    } catch {
      setDownloadError("Download failed. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.successBanner}>
        <div className={styles.bannerIcon}>🎉</div>
        <div className={styles.bannerContent}>
          <h3 className={styles.bannerTitle}>Statement Processed!</h3>
          {transactionCount !== undefined && (
            <p className={styles.bannerSubtitle}>
              {transactionCount.toLocaleString()} transactions extracted
            </p>
          )}
        </div>
      </div>

      {downloadError && (
        <p className={styles.errorText} role="alert">
          {downloadError}
        </p>
      )}

      <div className={styles.actions}>
        <button
          onClick={handleDownload}
          disabled={isDownloading}
          className={styles.downloadButton}
        >
          {isDownloading ? (
            <>
              <span className={styles.buttonSpinner} aria-hidden="true" />
              Downloading...
            </>
          ) : (
            <>
              <span aria-hidden="true">📥</span>
              Download Excel
            </>
          )}
        </button>

        <button
          onClick={onReset}
          className={styles.resetButton}
          disabled={isDownloading}
        >
          Process Another Statement
        </button>
      </div>
    </div>
  );
};