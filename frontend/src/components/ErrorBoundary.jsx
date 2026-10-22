import React from 'react'

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (typeof this.props.fallback === 'function') {
        return this.props.fallback(this.state.error, () => this.setState({ hasError: false, error: null }))
      }
      return (
        <div style={{
          padding: '24px',
          background: '#FFF1F2',
          border: '1px solid #FECDD3',
          borderRadius: '16px',
          margin: '20px 0',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>⚠️</div>
          <h3 style={{ margin: '0 0 8px', color: '#9F1239', fontSize: '16px' }}>
            {this.props.title || 'Component Rendering Error'}
          </h3>
          <p style={{ margin: '0 0 16px', color: '#BE123C', fontSize: '13.5px', maxWidth: '600px', marginInline: 'auto' }}>
            {this.state.error?.message || 'A component error prevented this section from rendering correctly.'}
          </p>
          <button
            type="button"
            className="l1-btn-secondary"
            onClick={() => {
              this.setState({ hasError: false, error: null })
              if (this.props.onReset) this.props.onReset()
            }}
            style={{ padding: '8px 18px', fontSize: '13px' }}
          >
            ↻ Retry Component
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
