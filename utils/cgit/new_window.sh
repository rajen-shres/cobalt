#!/usr/bin/env bash

window_count="$(osascript utils/cgit/new_window_count.scpt)"

echo $window_count

osascript << EOF
tell application "System Events"
	tell process "Terminal"
		tell menu item "Test Layout" of menu "Open Window Group" of menu item "Open Window Group" of menu "Window" of menu bar item "Window" of menu bar 1
			click
		end tell
	end tell
end tell
    tell application "Terminal"
      activate
      do script with command "echo Window A=$((window_count))" in window $((window_count))
      do script with command "echo Window B=$((window_count+1))" in window $((window_count+1))
      do script with command "echo Window C=$((window_count+2))" in window $((window_count+2))
      -- do script with command "stripe listen --forward-to 127.0.0.1:8088/payments/stripe-webhook" in window $((window_count+2))
      set custom title of window $((window_count)) to "Window A $((window_count)) --- Cobalt Window"
    end tell
EOF