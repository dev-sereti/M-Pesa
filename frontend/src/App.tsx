import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { FileUpload } from "./components/FileUpload/FileUpload";
import { PinInput } from "./components/PinInput/PinInput";
import { ProcessingStatus } from "./components/ProcessingStatus/ProcessingStatus";
import { ResultDownload } from "./components/ResultDownload/ResultDownload";
import { useStatementProcessor } from "./hooks/useStatementProcessor";
import { apiClient, ApiError, User } from "./services/api";
import "./App.css";

// ─── Auth Context ─────────────────────────────────────────────────────────────

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  signup: (data: SignupData) => Promise<void>;
}

interface SignupData {
  email: string;
  username: string;
  password: string;
  confirm_password: string;
  full_name?: string;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

// ─── Auth Provider ────────────────────────────────────────────────────────────

const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Try to restore session on mount
    if (apiClient.isAuthenticated()) {
      apiClient
        .getCurrentUser()
        .then(setUser)
        .catch(() => {})
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }

    // Listen for auth:logout events (triggered by API client)
    const handleLogout = () => setUser(null);
    window.addEventListener("auth:logout", handleLogout);
    return () => window.removeEventListener("auth:logout", handleLogout);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await apiClient.login(email, password);
    const currentUser = await apiClient.getCurrentUser();
    setUser(currentUser);
  }, []);

  const logout = useCallback(async () => {
    await apiClient.logout();
    setUser(null);
  }, []);

  const signup = useCallback(async (data: SignupData) => {
    await apiClient.signup(data);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, signup }}>
      {children}
    </AuthContext.Provider>
  );
};

// ─── Auth Forms ───────────────────────────────────────────────────────────────

type AuthView = "login" | "signup";

const AuthForms: React.FC = () => {
  const { login, signup } = useAuth();
  const [view, setView] = useState<AuthView>("login");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Login form state
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Signup form state
  const [signupData, setSignupData] = useState({
    email: "",
    username: "",
    password: "",
    confirm_password: "",
    full_name: "",
  });

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      await login(loginEmail, loginPassword);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Login failed. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      await signup(signupData);
      setSuccessMessage("Account created! Please log in.");
      setView("login");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Signup failed. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-logo">
          <span className="logo-icon">💚</span>
          <h1 className="auth-title">MPesa Processor</h1>
          <p className="auth-subtitle">Secure Statement Analysis</p>
        </div>

        {/* Tab Switcher */}
        <div className="auth-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={view === "login"}
            className={`auth-tab ${view === "login" ? "active" : ""}`}
            onClick={() => { setView("login"); setError(null); }}
          >
            Sign In
          </button>
          <button
            role="tab"
            aria-selected={view === "signup"}
            className={`auth-tab ${view === "signup" ? "active" : ""}`}
            onClick={() => { setView("signup"); setError(null); }}
          >
            Create Account
          </button>
        </div>

        {error && (
          <div className="alert alert-error" role="alert">
            ⚠️ {error}
          </div>
        )}
        {successMessage && (
          <div className="alert alert-success" role="status">
            ✅ {successMessage}
          </div>
        )}

        {view === "login" ? (
          <form onSubmit={handleLogin} className="auth-form" noValidate>
            <div className="form-group">
              <label htmlFor="login-email">Email Address</label>
              <input
                id="login-email"
                type="email"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoComplete="email"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="Your password"
                required
                autoComplete="current-password"
                className="form-input"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="btn btn-primary btn-full"
            >
              {isLoading ? "Signing in..." : "Sign In"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSignup} className="auth-form" noValidate>
            <div className="form-group">
              <label htmlFor="signup-name">Full Name</label>
              <input
                id="signup-name"
                type="text"
                value={signupData.full_name}
                onChange={(e) =>
                  setSignupData({ ...signupData, full_name: e.target.value })
                }
                placeholder="John Doe"
                autoComplete="name"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label htmlFor="signup-username">Username</label>
              <input
                id="signup-username"
                type="text"
                value={signupData.username}
                onChange={(e) =>
                  setSignupData({ ...signupData, username: e.target.value })
                }
                placeholder="johndoe"
                required
                autoComplete="username"
                pattern="[a-zA-Z0-9_-]+"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label htmlFor="signup-email">Email Address</label>
              <input
                id="signup-email"
                type="email"
                value={signupData.email}
                onChange={(e) =>
                  setSignupData({ ...signupData, email: e.target.value })
                }
                placeholder="you@example.com"
                required
                autoComplete="email"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label htmlFor="signup-password">
                Password
                <span className="password-hint">
                  (12+ chars, uppercase, lowercase, number, symbol)
                </span>
              </label>
              <input
                id="signup-password"
                type="password"
                value={signupData.password}
                onChange={(e) =>
                  setSignupData({ ...signupData, password: e.target.value })
                }
                placeholder="Strong password"
                required
                autoComplete="new-password"
                minLength={12}
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label htmlFor="signup-confirm">Confirm Password</label>
              <input
                id="signup-confirm"
                type="password"
                value={signupData.confirm_password}
                onChange={(e) =>
                  setSignupData({
                    ...signupData,
                    confirm_password: e.target.value,
                  })
                }
                placeholder="Repeat password"
                required
                autoComplete="new-password"
                className="form-input"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="btn btn-primary btn-full"
            >
              {isLoading ? "Creating account..." : "Create Account"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

// ─── Main Processor UI ────────────────────────────────────────────────────────

const StatementProcessor: React.FC = () => {
  const { user, logout } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pin, setPin] = useState("");

  const {
    state,
    progress,
    job,
    status,
    error,
    uploadAndProcess,
    downloadResult,
    reset,
  } = useStatementProcessor();

  const handleProcess = async () => {
    if (!selectedFile || !pin) return;
    await uploadAndProcess(selectedFile, pin);
  };

  const handleReset = () => {
    setSelectedFile(null);
    setPin("");
    reset();
  };

  const isProcessing = state === "uploading" || state === "polling";
  const canProcess =
    selectedFile !== null &&
    pin.length >= 4 &&
    state === "idle";

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-brand">
          <span className="brand-icon">💚</span>
          <h1 className="brand-name">MPesa Processor</h1>
        </div>
        <div className="header-user">
          <span className="user-greeting">Hello, {user?.full_name || user?.username}</span>
          <button onClick={logout} className="btn btn-outline btn-sm">
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        <div className="processor-card">
          <h2 className="card-title">
            Process MPesa Statement
          </h2>
          <p className="card-subtitle">
            Upload your PIN-protected PDF statement to extract and analyze
            your transactions
          </p>

          {state === "completed" ? (
            <ResultDownload
              onDownload={downloadResult}
              onReset={handleReset}
              transactionCount={status?.transaction_count}
              filename={job?.original_filename}
            />
          ) : (
            <>
              {/* Step 1: File Upload */}
              <section className="step-section">
                <div className="step-header">
                  <span className="step-number">1</span>
                  <h3 className="step-title">Select Your Statement</h3>
                </div>
                <FileUpload
                  onFileSelect={setSelectedFile}
                  disabled={isProcessing}
                  selectedFile={selectedFile}
                />
              </section>

              {/* Step 2: PIN Input */}
              <section className="step-section">
                <div className="step-header">
                  <span className="step-number">2</span>
                  <h3 className="step-title">Enter Statement PIN</h3>
                </div>
                <PinInput
                  onPinChange={setPin}
                  disabled={isProcessing}
                  hint="Usually your registered MPesa phone number (e.g., 0712345678)"
                />
              </section>

              {/* Processing Status */}
              <ProcessingStatus
                state={state}
                progress={progress}
                transactionCount={status?.transaction_count}
                errorMessage={error || undefined}
              />

              {/* Action Buttons */}
              <div className="action-buttons">
                <button
                  onClick={handleProcess}
                  disabled={!canProcess}
                  className="btn btn-primary btn-large"
                >
                  {isProcessing ? (
                    <>
                      <span className="btn-spinner" aria-hidden="true" />
                      Processing...
                    </>
                  ) : (
                    "Process Statement"
                  )}
                </button>

                {(state === "error" || (state === "idle" && selectedFile)) && (
                  <button onClick={handleReset} className="btn btn-outline">
                    Start Over
                  </button>
                )}
              </div>

              {/* Security Notice */}
              <div className="security-notice">
                <span>🔒</span>
                <p>
                  Your PIN is never stored. Files are automatically deleted
                  after processing. All data is encrypted in transit.
                </p>
              </div>
            </>
          )}
        </div>

        {/* Job History */}
        <JobHistory />
      </main>
    </div>
  );
};

// ─── Job History Component ────────────────────────────────────────────────────

const JobHistory: React.FC = () => {
  const [jobs, setJobs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    apiClient
      .listJobs()
      .then(setJobs)
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading || jobs.length === 0) return null;

  return (
    <div className="history-card">
      <h3 className="history-title">Recent Processing History</h3>
      <div className="history-list">
        {jobs.map((job) => (
          <div key={job.job_id} className="history-item">
            <div className="history-info">
              <span className="history-filename">{job.original_filename}</span>
              <span className="history-date">
                {new Date(job.created_at).toLocaleDateString()}
              </span>
            </div>
            <div className="history-status">
              <span
                className={`status-badge status-${job.status}`}
              >
                {job.status}
              </span>
              {job.transaction_count && (
                <span className="history-count">
                  {job.transaction_count} transactions
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Root App ─────────────────────────────────────────────────────────────────

const AppContent: React.FC = () => {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  return user ? <StatementProcessor /> : <AuthForms />;
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;















// import { useState } from 'react'
// import reactLogo from './assets/react.svg'
// import viteLogo from '/vite.svg'
// import './App.css'

// function App() {
//   const [count, setCount] = useState(0)

//   return (
//     <>
//       <div>
//         <a href="https://vite.dev" target="_blank">
//           <img src={viteLogo} className="logo" alt="Vite logo" />
//         </a>
//         <a href="https://react.dev" target="_blank">
//           <img src={reactLogo} className="logo react" alt="React logo" />
//         </a>
//       </div>
//       <h1>Vite + React</h1>
//       <div className="card">
//         <button onClick={() => setCount((count) => count + 1)}>
//           count is {count}
//         </button>
//         <p>
//           Edit <code>src/App.tsx</code> and save to test HMR
//         </p>
//       </div>
//       <p className="read-the-docs">
//         Click on the Vite and React logos to learn more
//       </p>
//     </>
//   )
// }

// export default App
