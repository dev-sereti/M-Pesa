import React, { useCallback, useRef, useState } from "react";
import styles from "./FileUpload.module.css";

interface FileUploadProps {
  onFileSelect: (file: File) => void;
  disabled?: boolean;
  selectedFile?: File | null;
}

const MAX_SIZE_MB = 10;
const ALLOWED_TYPES = ["application/pdf"];

export const FileUpload: React.FC<FileUploadProps> = ({
  onFileSelect,
  disabled = false,
  selectedFile,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return "Only PDF files are accepted";
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File size must not exceed ${MAX_SIZE_MB}MB`;
    }
    return null;
  };

  const handleFile = useCallback(
    (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      setError(null);
      onFileSelect(file);
    },
    [onFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);

      if (disabled) return;

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        handleFile(files[0]);
      }
    },
    [disabled, handleFile]
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={styles.container}>
      <div
        className={`${styles.dropzone} ${isDragging ? styles.dragging : ""} ${
          disabled ? styles.disabled : ""
        } ${selectedFile ? styles.hasFile : ""}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !disabled && fileInputRef.current?.click()}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Upload PDF statement"
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            fileInputRef.current?.click();
          }
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleInputChange}
          className={styles.hiddenInput}
          disabled={disabled}
          aria-hidden="true"
        />

        {selectedFile ? (
          <div className={styles.fileInfo}>
            <span className={styles.fileIcon}>📄</span>
            <div className={styles.fileDetails}>
              <span className={styles.fileName}>{selectedFile.name}</span>
              <span className={styles.fileSize}>
                {formatFileSize(selectedFile.size)}
              </span>
            </div>
            <span className={styles.checkmark}>✓</span>
          </div>
        ) : (
          <div className={styles.placeholder}>
            <span className={styles.uploadIcon}>📤</span>
            <p className={styles.mainText}>
              {isDragging
                ? "Drop your PDF here"
                : "Drag & drop your MPesa statement"}
            </p>
            <p className={styles.subText}>
              or <span className={styles.browseLink}>browse files</span>
            </p>
            <p className={styles.hint}>PDF files only • Max {MAX_SIZE_MB}MB</p>
          </div>
        )}
      </div>

      {error && (
        <p className={styles.errorMessage} role="alert">
          ⚠️ {error}
        </p>
      )}
    </div>
  );
};