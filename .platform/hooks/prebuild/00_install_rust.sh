#!/bin/bash

echo "Installing Rust..." >> /var/log/cobalt.log

# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env
export PATH="$HOME/.cargo/bin:$PATH"

# Make Rust available to subsequent scripts
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> /root/.bashrc
echo 'source $HOME/.cargo/env' >> /root/.bashrc

# Also make it available to the webapp user
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> /home/webapp/.bashrc
echo 'source $HOME/.cargo/env' >> /home/webapp/.bashrc

echo "Rust installation complete" >> /var/log/cobalt.log