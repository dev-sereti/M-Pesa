/**
 * Custom hook for managing the statement processing workflow.
 * Handles upload, polling, and download states.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, ApiError, ProcessingJob, ProcessingStatus } from "../services/api";

export type ProcessingState =
  | "idle"
  | "uploading"
  | "polling"
  | "completed"
  | "error";

interface UseStatementProcessorReturn {
  state: ProcessingState;
  progress: number;
  job: ProcessingJob | null;
  status: ProcessingStatus | null;
  error: string | null;
  uploadAndProcess: (file: File, pin: string) => Promise<void>;
  downloadResult: () => Promise<void>;
  reset: () => void;
}

export function useStatementProcessor(): UseStatementProcessorReturn {
  const [state, setState] = useState<ProcessingState>("idle");
  const [progress, setProgress] = useState(0);
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const maxPollAttempts = 60; // 5 minutes at 5s intervals
  const pollAttemptsRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    pollAttemptsRef.current = 0;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const pollJobStatus = useCallback(
    (jobId: string) => {
      setState("polling");

      pollIntervalRef.current = setInterval(async () => {
        pollAttemptsRef.current += 1;

        if (pollAttemptsRef.current > maxPollAttempts) {
          stopPolling();
          setState("error");
          setError("Processing timed out. Please try again.");
          return;
        }

        try {
          const currentStatus = await apiClient.getJobStatus(jobId);
          setStatus(currentStatus);

          // Update progress based on status
          if (currentStatus.status === "pending") {
            setProgress(10);
          } else if (currentStatus.status === "processing") {
            setProgress(
              Math.min(50 + pollAttemptsRef.current * 2, 90)
            );
          } else if (currentStatus.status === "completed") {
            setProgress(100);
            stopPolling();
            setState("completed");
          } else if (currentStatus.status === "failed") {
            stopPolling();
            setState("error");
            setError(
              currentStatus.message ||
                "Processing failed. Please check your PIN and try again."
            );
          }
        } catch (err) {
          if (pollAttemptsRef.current > 3) {
            stopPolling();
            setState("error");
            setError("Lost connection to server. Please refresh and try again.");
          }
        }
      }, 3000); // Poll every 3 seconds
    },
    [stopPolling]
  );

  const uploadAndProcess = useCallback(
    async (file: File, pin: string) => {
      setState("uploading");
      setProgress(5);
      setError(null);
      setJob(null);
      setStatus(null);

      try {
        const uploadedJob = await apiClient.uploadStatement(file, pin);
        setJob(uploadedJob);
        setProgress(20);

        // Start polling for status
        pollJobStatus(uploadedJob.job_id);
      } catch (err) {
        setState("error");
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Upload failed. Please try again.");
        }
      }
    },
    [pollJobStatus]
  );

  const downloadResult = useCallback(async () => {
    if (!job?.job_id) return;

    try {
      const blob = await apiClient.downloadExcel(job.job_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `mpesa_${job.original_filename.replace(".pdf", "")}_processed.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      // Clean up object URL
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (err) {
      setError("Download failed. Please try again.");
    }
  }, [job]);

  const reset = useCallback(() => {
    stopPolling();
    setState("idle");
    setProgress(0);
    setJob(null);
    setStatus(null);
    setError(null);
  }, [stopPolling]);

  return {
    state,
    progress,
    job,
    status,
    error,
    uploadAndProcess,
    downloadResult,
    reset,
  };
}