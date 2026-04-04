import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

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

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
