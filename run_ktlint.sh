#!/usr/bin/env bash
set -e
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
mkdir -p reports
if ./gradlew -q tasks --all | grep -q ktlintCheck; then
  ./gradlew ktlintCheck
  if [ -d build/reports/ktlint ]; then
    find build/reports/ktlint -type f -name "*.json" -exec cat {} \; > reports/ktlint.json || true
  else
    touch reports/ktlint.json
  fi
else
  KVER="1.3.1"
  curl -L -o ktlint.jar https://github.com/pinterest/ktlint/releases/download/${KVER}/ktlint-${KVER}-all.jar
  java -jar ktlint.jar --reporter=json > reports/ktlint.json || true
fi
python3 parse_ktlint.py reports/ktlint.json reports/ktlint_findings.json
