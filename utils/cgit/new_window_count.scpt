tell application "Terminal" to activate

tell application "Terminal"
    set c to 0
    repeat with i from 1 to (count of windows)
        set c to c + (count of tabs in window i)
    end repeat
    c
end tell