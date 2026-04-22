# tokenxray session demo — live status line hints in Claude Code
# Do NOT run this file directly — use demo/record.sh instead.
# record.sh substitutes __DEMO_DIR__ with the real path before calling vhs.

Output demo/demo-session.gif
Set FontSize 16
Set Width 900
Set Height 620
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms
Set Shell "bash"

# __DEMO_DIR__ is replaced by demo/record.sh at record time.
Env "PATH" "__DEMO_DIR__/bin:/opt/homebrew/bin:/usr/bin:/bin"
Env "PS1" ""
Env "HOME" "__DEMO_DIR__/home"
Env "BASH_SILENCE_DEPRECATION_WARNING" "1"

# Run the simulated session — timing is internal to the script
# Hide the invocation so the GIF starts cleanly with session output
Hide
Type "session-demo"
Enter
Show

# Total script runtime ≈ 9 turns × ~2.2s + final 3s ≈ 23s; add buffer
Sleep 30s
