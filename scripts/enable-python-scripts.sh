#!/usr/bin/env bash
# Patches coolwsd.xml inside the running Collabora container to permit
# Python macro execution. Run once after first `docker compose up`.
#
# Usage: ./scripts/enable-python-scripts.sh [container-name]
#        Default container name: collabora

set -euo pipefail

CONTAINER="${1:-collabora}"
COOLWSD="/etc/coolwsd/coolwsd.xml"

echo "→ Patching $COOLWSD in container '$CONTAINER' …"

docker exec -u root "$CONTAINER" bash -c "
  # Enable macro execution
  xmlstarlet ed -L \
    -u '//security/macro_security_level' -v 1 \
    -u '//security/enable_macros_execution' -v 'true' \
    '$COOLWSD' 2>/dev/null || \
  sed -i \
    -e 's|<macro_security_level>.*</macro_security_level>|<macro_security_level>1</macro_security_level>|' \
    '$COOLWSD'
  echo 'Done.'
"

echo "→ Restarting coolwsd …"
docker exec -u root "$CONTAINER" bash -c "pkill -HUP coolwsd || true"
echo "→ Python scripting enabled. Test at: http://localhost:9980/browser/dist/framed.doc.html"
