import React from "react";

// A resilience-themed app should not white-screen on a render error. This
// boundary catches any throw in the tree below it and shows a recoverable
// fallback instead. It's a class component because React only exposes error
// boundaries via the class lifecycle (getDerivedStateFromError / componentDidCatch).
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // In a real deployment this would ship to an error tracker (Sentry, etc.).
    // eslint-disable-next-line no-console
    console.error("Uncaught render error:", error, info?.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary" role="alert">
          <div className="error-boundary-card">
            <h2>Something went wrong</h2>
            <p className="muted">
              The console hit an unexpected error and stopped this view to avoid
              showing anything inconsistent.
            </p>
            <pre className="error-boundary-detail">
              {String(this.state.error?.message || this.state.error)}
            </pre>
            <div className="error-boundary-actions">
              <button className="run-btn" onClick={this.reset}>
                Try again
              </button>
              <button
                className="ghost-btn"
                onClick={() => window.location.reload()}
              >
                Reload
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
