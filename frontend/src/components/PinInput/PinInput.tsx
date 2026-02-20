import React, { useState, useRef, useEffect } from "react";
import styles from "./PinInput.module.css";

interface PinInputProps {
  onPinChange: (pin: string) => void;
  disabled?: boolean;
  label?: string;
  placeholder?: string;
  hint?: string;
}

export const PinInput: React.FC<PinInputProps> = ({
  onPinChange,
  disabled = false,
  label = "Statement PIN",
  placeholder = "Enter your PDF PIN",
  hint = "This is usually your phone number registered with MPesa",
}) => {
  const [pin, setPin] = useState("");
  const [showPin, setShowPin] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Allow digits, letters (for some PINs), and limit length
    if (value.length <= 20) {
      setPin(value);
      onPinChange(value);
    }
  };

  const handleToggleVisibility = () => {
    setShowPin((prev) => !prev);
  };

  // Clear PIN on unmount for security
  useEffect(() => {
    return () => {
      setPin("");
    };
  }, []);

  return (
    <div className={styles.container}>
      {label && (
        <label className={styles.label} htmlFor="pin-input">
          {label}
        </label>
      )}

      <div className={styles.inputWrapper}>
        <span className={styles.lockIcon} aria-hidden="true">
          🔐
        </span>
        <input
          id="pin-input"
          ref={inputRef}
          type={showPin ? "text" : "password"}
          value={pin}
          onChange={handleChange}
          placeholder={placeholder}
          disabled={disabled}
          className={styles.input}
          autoComplete="off"
          spellCheck={false}
          inputMode="numeric"
          aria-describedby="pin-hint"
        />
        <button
          type="button"
          onClick={handleToggleVisibility}
          className={styles.visibilityToggle}
          aria-label={showPin ? "Hide PIN" : "Show PIN"}
          disabled={disabled}
        >
          {showPin ? "🙈" : "👁️"}
        </button>
      </div>

      {hint && (
        <p id="pin-hint" className={styles.hint}>
          ℹ️ {hint}
        </p>
      )}
    </div>
  );
};