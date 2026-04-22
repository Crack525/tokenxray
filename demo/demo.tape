# tokenxray terminal demo
# Do NOT run this file directly — use demo/record.sh instead.
# record.sh substitutes __DEMO_DIR__ with the real path before calling vhs.

Output demo/demo.gif
Set FontSize 16
Set Width 900
Set Height 600
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms
Set Shell "bash"

# __DEMO_DIR__ is replaced by demo/record.sh at record time.
Env "PATH" "__DEMO_DIR__/bin:/opt/homebrew/bin:/usr/bin:/bin"
Env "PS1" "$ "
Env "HOME" "__DEMO_DIR__/home"
Env "BASH_SILENCE_DEPRECATION_WARNING" "1"

# 1. Overview — see where your money goes across all sessions
Type "tokenxray"
Enter
Sleep 4s

# 2. Session drill-down — the $104 session from the blog post
Type "tokenxray --session a4f2c831-9d7e-4b8a-b2e1-f3c9d0e5a6b8"
Enter
Sleep 5s

# 3. Diagnose — specific recommendations and potential savings
Type "tokenxray --diagnose"
Enter
Sleep 4s

# 4. Install hooks — set it and forget it
Type "tokenxray --install-hook --confirm"
Enter
Sleep 4s

Sleep 2s
