#!/bin/bash

# Make sure Rust is in the PATH for the pip install process
export PATH="$HOME/.cargo/bin:$PATH"
source $HOME/.cargo/env

echo "Rust is available at: $(which rustc)"
echo "Rust version: $(rustc --version)"

# Create a flag file to indicate Rust is ready
touch /tmp/rust_ready 