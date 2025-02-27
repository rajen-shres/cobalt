#!/bin/bash

echo "Starting Rust installation..."

# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# Make Rust available to subsequent scripts
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> /root/.bashrc
echo 'source $HOME/.cargo/env' >> /root/.bashrc

# Make it available system-wide
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> /etc/profile
echo 'source $HOME/.cargo/env' >> /etc/profile

# Create a script that will be sourced during the pip install phase
cat << EOF > /tmp/rust_env.sh
#!/bin/bash
export PATH="$HOME/.cargo/bin:$PATH"
source $HOME/.cargo/env
EOF
chmod +x /tmp/rust_env.sh

# Create a modified pip command that sources the Rust environment
cat << EOF > /usr/local/bin/pip-with-rust
#!/bin/bash
source /tmp/rust_env.sh
/var/app/venv/staging-LQM1lest/bin/pip "\$@"
EOF
chmod +x /usr/local/bin/pip-with-rust

echo "Rust installation complete"