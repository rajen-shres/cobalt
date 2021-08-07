#!/usr/bin/env bash

window_count="$(osascript utils/cgit/new_window_count.scpt)"

echo $window_count

osascript utils/cgit/new_window_open.scpt