#!/bin/bash
cd /home/kavia/workspace/code-generation/enterprise-analytics-platform-43808-43824/dashboard_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

