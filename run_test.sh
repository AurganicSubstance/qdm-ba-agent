#!/bin/bash
# Test Run — full pipeline without emails
set -e
cd "$(dirname "$0")"
bash run_morning.sh --test
