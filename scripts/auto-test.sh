#!/bin/bash
# MACS Auto-Test Hook
# Runs after Write/Edit on code files. If tests fail, wakes Claude to fix.

FILE=$(jq -r '.tool_response.filePath // .tool_input.file_path' 2>/dev/null)

# Skip non-code files
case "$FILE" in
  *.ts|*.tsx|*.js|*.jsx|*.py|*.go|*.rs|*.java|*.rb|*.php) ;;
  *) exit 0 ;;
esac

# Skip test files themselves (prevent infinite loop)
case "$FILE" in
  *.test.*|*.spec.*|*_test.*|*_spec.*|*/test_*|*/tests/*) exit 0 ;;
esac

# Find project root (walk up to find package.json, pyproject.toml, go.mod, etc.)
DIR=$(dirname "$FILE")
ROOT=""
while [ "$DIR" != "/" ]; do
  if [ -f "$DIR/package.json" ] || [ -f "$DIR/pyproject.toml" ] || [ -f "$DIR/go.mod" ] || [ -f "$DIR/Cargo.toml" ] || [ -f "$DIR/Makefile" ]; then
    ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done

[ -z "$ROOT" ] && exit 0

cd "$ROOT" || exit 0

# Auto-detect and run test command
RESULT=""
EXIT_CODE=0

if [ -f "package.json" ]; then
  # Check if test script exists
  HAS_TEST=$(jq -r '.scripts.test // empty' package.json 2>/dev/null)
  if [ -n "$HAS_TEST" ] && [ "$HAS_TEST" != "echo \"Error: no test specified\" && exit 1" ]; then
    export PATH="$HOME/macs-tools/node-v22.15.0-darwin-arm64/bin:$PATH"
    RESULT=$(npm test 2>&1 | tail -30)
    EXIT_CODE=${PIPESTATUS[0]}
  fi
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -d "tests" ] && command -v pytest &>/dev/null; then
  RESULT=$(pytest --tb=short -q 2>&1 | tail -30)
  EXIT_CODE=$?
elif [ -f "go.mod" ]; then
  RESULT=$(go test ./... 2>&1 | tail -30)
  EXIT_CODE=$?
elif [ -f "Cargo.toml" ]; then
  RESULT=$(cargo test 2>&1 | tail -30)
  EXIT_CODE=$?
elif [ -f "Makefile" ] && grep -q "^test:" Makefile; then
  RESULT=$(make test 2>&1 | tail -30)
  EXIT_CODE=$?
fi

# No test runner found
[ -z "$RESULT" ] && exit 0

if [ $EXIT_CODE -ne 0 ]; then
  # Tests failed — wake Claude to fix
  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"AUTO-TEST FAILED after editing $FILE.\n\nTest output:\n$RESULT\n\nFix the failing tests. The code you just wrote has errors."}}
EOF
  exit 2
fi

# Tests passed — silent success
exit 0
