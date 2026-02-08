pipeline {
  agent any
  options {
    timestamps()
  }
  environment {
    PATH = "/Users/yash.malik/.rd/bin:/usr/local/bin:/opt/homebrew/bin:${env.PATH}"
    NERDCTL_NAMESPACE = "k8s.io"
    NERDCTL_PULL = "never"
    APP_IMAGE = "order-service:ci"
    UV_IMAGE = "ghcr.io/astral-sh/uv:python3.14-bookworm-slim"
  }
  stages {
    stage("Build") {
      steps {
        sh "nerdctl --namespace ${NERDCTL_NAMESPACE} build --pull=${NERDCTL_PULL} -t ${APP_IMAGE} -f backend/Dockerfile ."
      }
    }
    stage("Test") {
      steps {
        sh """
          set -euo pipefail
          nerdctl --namespace ${NERDCTL_NAMESPACE} run --rm --pull=${NERDCTL_PULL} \\
            -v "\\\$PWD:/workspace" -w /workspace \\
            ${UV_IMAGE} \\
            sh -lc "uv sync --frozen --group dev --package app && uv run --package app python -m unittest discover -s backend/tests -p 'test_*.py'"
        """
      }
    }
  }
}
