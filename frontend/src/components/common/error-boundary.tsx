import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorState } from '@/components/common/error-state'

interface Props {
  children: ReactNode
}
interface State {
  error: Error | null
}

/** Last-resort guard so a render error shows a message instead of a blank page. */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
  }

  override render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-xl p-6">
          <ErrorState
            title="The application hit an unexpected error"
            message={this.state.error.message}
            onRetry={() => this.setState({ error: null })}
          />
        </div>
      )
    }
    return this.props.children
  }
}
