FROM collabora/code:latest

# Install Python scripting support for LibreOffice
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        collaboraofficebasis-python-script-provider \
        collaboraofficebasis-pyuno \
    && rm -rf /var/lib/apt/lists/*

# Enable Python macro execution in coolwsd.xml.
# The default config ships with macro_security_level = 4 (disabled).
# Level 1 allows execution without user prompts, which is required for
# CallPythonScript to work. We also set python_path so the Kit process
# can find our scripts.
RUN COOLWSD=/etc/coolwsd/coolwsd.xml && \
    # Master switch: enable macro/script execution (Basic + Python)
    sed -i 's|<enable_macros_execution[^>]*>[^<]*</enable_macros_execution>|<enable_macros_execution desc="" type="bool" default="false">true</enable_macros_execution>|' "$COOLWSD" && \
    # macro_security_level: 0=lowest (no prompt, required for headless Kit process)
    # Level 1 triggers a confirmation dialog that hangs the headless Kit forever.
    sed -i 's|<macro_security_level[^>]*>[^<]*</macro_security_level>|<macro_security_level desc="" type="int" default="4">0</macro_security_level>|' "$COOLWSD"

# Copy Zotero Python scripts into the global script directory
COPY scripts/zotero_fields.py  /opt/collaboraoffice/share/Scripts/python/zotero_fields.py
COPY scripts/zotero_export.py  /opt/collaboraoffice/share/Scripts/python/zotero_export.py

USER cool
