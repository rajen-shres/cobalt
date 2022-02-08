#!/bin/bash

# Check if we are on WSL
uname -r | grep Microsoft > /dev/null

if [ $? -eq 0 ]
then
  cd /tmp
  explorer.exe test-output.html
else
  open /tmp/test-output.html
fi