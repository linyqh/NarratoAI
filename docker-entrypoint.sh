#!/bin/bash
set -e

if [ "$1" = "webui" ]; then
    exec streamlit run webui.py --browser.serverAddress=127.0.0.1 --server.enableCORS=True --browser.gatherUsageStats=False
else
    exec "$@"
fi 