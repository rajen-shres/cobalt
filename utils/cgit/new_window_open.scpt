tell application "System Events"
	tell process "Terminal"
		tell menu item "Test Layout" of menu "Open Window Group" of menu item "Open Window Group" of menu "Window" of menu bar item "Window" of menu bar 1
			click
		end tell
	end tell
end tell
    tell application "Terminal"
      activate
      do script with command "echo Hello" in window 1
      do script with command "stripe listen --forward-to 127.0.0.1:8088/payments/stripe-webhook" in window 2
      do script with command "echo Hello 33" in window 3
    end tell