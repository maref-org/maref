import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary]", error, info.componentStack);
    this.props.onError?.(error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex h-screen w-screen flex-col items-center justify-center bg-maref-bg text-maref-text">
          <div className="max-w-md rounded-lg border border-maref-border bg-maref-surface p-8 text-center shadow-lg">
            <div className="mb-4 text-4xl">⚠️</div>
            <h2 className="mb-2 text-xl font-semibold">Application Error</h2>
            <p className="mb-4 text-sm text-maref-text/70">
              Something went wrong. Please try refreshing the application.
            </p>
            <details className="mb-4 text-left">
              <summary className="cursor-pointer text-xs text-maref-text/50">
                Error Details
              </summary>
              <pre className="mt-2 max-h-32 overflow-auto rounded bg-black/10 p-2 text-xs">
                {this.state.error?.message}
              </pre>
            </details>
            <button
              onClick={this.handleReset}
              className="rounded bg-maref-primary px-4 py-2 text-sm text-white transition hover:opacity-90"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
