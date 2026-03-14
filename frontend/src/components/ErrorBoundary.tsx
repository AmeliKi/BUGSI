import { Component, type ReactNode } from 'react'
import i18n from '../i18n'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen items-center justify-center">
          <div className="text-center p-8">
            <h2 className="text-lg font-bold text-red-600 mb-2">{i18n.t('error.title')}</h2>
            <p className="text-sm text-gray-500 mb-4">{this.state.error?.message}</p>
            <button
              onClick={() => window.location.reload()}
              className="bg-gray-800 text-white px-4 py-2 rounded-md text-sm hover:bg-gray-900"
            >
              {i18n.t('error.reload')}
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
