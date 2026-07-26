Output "kaydet-demo.webm"

Require kaydet

Set Shell "bash"
Set FontFamily "Monaco"
Set FontSize 16
Set Width 430
Set Height 574
Set Theme "Unholy"
Set LetterSpacing 0
Set Framerate 6
Set Padding 10
Set Margin 20
Set MarginFill "#6B50FF"
Set BorderRadius 10
Set TypingSpeed 25ms
Set WindowBar Colorful
Set WindowBarSize 40

Sleep 1s

Env PS1 '\[\e[32m\]\$\[\e[0m\] '

# Init Vim
Hide Type "vi" Enter Type ":set wrap" Enter Type ":set linebreak" Enter Show Type "i"

Type "Gununu terminal karsisinda geciren insanlarin not almak icin Notion ya da Obsidian kullanmasi cok sacma degil mi?" Sleep 1 Enter 2

Type "Su sekilde not almak mumkun olsa mesela?" Enter 1

# Exit Vim
Escape Type ":q!" Sleep 1 Enter Hide Type "clear" Enter Show Sleep 1s

# Core demo
Type `kaydet "AWS faturasi odendi. #harcama tutar:3000tl"` Sleep 1s Enter
Type `kaydet --todo "mesafe:3km kosulacak"` Sleep 1s Enter 2

Type "# Simdi sorgulayabilirim:" Sleep 1s Enter 2

Type `kaydet --filter "#etiketli"` Sleep 1s Enter 2

Sleep 2s

# Closing Vim
Hide Type "vi" Enter Type ":set wrap" Enter Type ":set linebreak" Enter Show Type "i"

Type "Terminalden ayrilmadan," Enter
Type "beklemeden ve bolumme" Backspace@200ms 3 Type "nmeden." Enter 2
Type "github.com/miratcan/kaydet/" Enter 2 Sleep 4

Escape Type ":q!" Sleep 1 Enter Hide Type "clear" Enter Show Sleep 1s
