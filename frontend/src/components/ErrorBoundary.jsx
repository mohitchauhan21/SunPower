import { Component } from 'react';

/* If a page crashes, show a calm message with a way out instead of a blank screen. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error('Page crashed:', error, info?.componentStack);
  }

  componentDidUpdate(prev) {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="wrap login" role="alert">
        <h1 className="headline">Something went wrong.</h1>
        <p className="lead">This page hit a problem. Your data is safe. Try again, or go back to the home page.</p>
        <div className="actions">
          <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>Try again</button>
          <a className="link" href="/">Home</a>
        </div>
      </section>
    );
  }
}
