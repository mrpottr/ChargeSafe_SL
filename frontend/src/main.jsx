import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// The root error boundary keeps a rendering crash visible during development
// instead of leaving the screen blank with no clue about what failed.
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ChargeSafe render error:", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ minHeight: "100vh", background: "#060c1a", color: "#e8f0fe", padding: "24px", fontFamily: "monospace" }}>
          <h1 style={{ fontSize: "20px", marginBottom: "16px" }}>Frontend Error</h1>
          <pre style={{ whiteSpace: "pre-wrap" }}>{String(this.state.error?.stack || this.state.error)}</pre>
        </div>
      );
    }

    return this.props.children;
  }
}

// The app is mounted once here so the shared boundary wraps every screen and
// React strict mode can surface unsafe patterns during development.
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
