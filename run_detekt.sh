#!/usr/bin/env bash
set -e
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
./gradlew detektBaseline || true
./gradlew detekt
mkdir -p reports
if [ -f build/reports/detekt/detekt.xml ]; then cp build/reports/detekt/detekt.xml reports/detekt.xml; fi
if [ -f config/detekt/baseline.xml ]; then cp config/detekt/baseline.xml reports/detekt-baseline.xml; elif [ -f detekt-baseline.xml ]; then cp detekt-baseline.xml reports/detekt-baseline.xml; else touch reports/detekt-baseline.xml; fi
python3 parse_detekt.py reports/detekt.xml reports/detekt-baseline.xml reports/detekt_findings.json
