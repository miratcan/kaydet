Output "demo.gif"

Require kaydet

Set Shell "bash"
Set FontFamily "Monaco"
Set FontSize 14
Set Width 854
Set Height 480
Set Theme "Dracula"
Set LetterSpacing 0
Set Framerate 10
Set Padding 20
Set Margin 15
Set MarginFill "#6B50FF"
Set BorderRadius 8
Set TypingSpeed 15ms
Set WindowBar Colorful
Set WindowBarSize 30

Sleep 1s

# ---- HOOK ----
Hide
Type "vi" Enter
Type ":set wrap" Enter
Type ":set linebreak" Enter
Show
Type "i"

Type "You live in the terminal." Sleep 500ms Enter
Type "Why take notes in Notion or Obsidian?" Sleep 500ms Enter
Type "What a needless context switch." Sleep 500ms Enter 2
Type "What if you could just..." Sleep 500ms Enter
Type "...type and search?" Sleep 800ms

Escape
Type ":q!" Sleep 1 Enter
Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 1: Capture ----
Sleep 1s
Type "# Capture a note." Enter
Type "# Add tags. Done." Enter 2
Type `kaydet "Fixed auth race condition #dev commit:a3f89d status:done"` Sleep 300ms Enter
Sleep 3s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 2: Todo ----
Sleep 1s
Type "# Track todos without" Enter
Type "# leaving the terminal." Enter 2
Type `kaydet --todo "Review PR by end of day #work priority:high"` Sleep 300ms Enter
Sleep 3s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 3: List ----
Sleep 1s
Type "# List everything." Enter 2
Type "kaydet --list" Sleep 300ms Enter
Sleep 2.5s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 4: Filter ----
Sleep 1s
Type "# Or filter by tag." Enter 2
Type `kaydet --filter "#dev"` Sleep 300ms Enter
Sleep 2.5s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 5: Metadata ----
Sleep 1s
Type "# Structured metadata." Enter
Type "# Naturally." Enter 2
Type `kaydet "Lunch with client #expense cost:850"` Sleep 300ms Enter
Sleep 2s

Type `kaydet "Flight tickets booked #expense cost:3250"` Sleep 300ms Enter
Sleep 2.5s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 6: Metadata queries ----
Sleep 1s
Type "# Query like a database." Enter 2
Type `kaydet --filter "cost:>1000"` Sleep 300ms Enter
Sleep 2.5s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 7: Sum ----
Sleep 1s
Type "# Sum numeric values" Enter
Type "# across matching entries." Enter 2
Type `kaydet --filter "#expense" --sum` Sleep 300ms Enter
Sleep 3s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- 8: Today ----
Sleep 1s
Type "# Open today's log" Enter
Type "# in your editor." Enter 2
Type "kaydet --today" Sleep 300ms Enter
Sleep 3s

Hide
Type "clear" Enter
Show
Sleep 500ms

# ---- OUTRO ----
Hide
Type "vi" Enter
Type ":set wrap" Enter
Type ":set linebreak" Enter
Show
Type "i"

Type "No folders." Sleep 300ms Enter
Type "No app switching." Sleep 300ms Enter
Type "No excuses." Sleep 500ms Enter 2
Type "github.com/miratcan/kaydet" Enter 2 Sleep 1
Type "Take notes." Sleep 400ms
Type " Stay in the terminal." Sleep 600ms

Escape
Type ":q!" Sleep 1 Enter
Hide
Type "clear" Enter
Show
Sleep 2s
