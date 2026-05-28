Section "AddToPath"
    ExecWait 'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "[Environment]::SetEnvironmentVariable(\"PATH\", [Environment]::GetEnvironmentVariable(\"PATH\", \"User\") + \";$INSTDIR\", \"User\")"'
SectionEnd

Section "un.RemoveFromPath"
    ExecWait 'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$p = [Environment]::GetEnvironmentVariable(\"PATH\", \"User\"); $p = $p -replace [regex]::Escape(\";$INSTDIR\"), \"\"; $p = $p -replace [regex]::Escape(\"$INSTDIR;\"), \"\"; [Environment]::SetEnvironmentVariable(\"PATH\", $p, \"User\")"'
SectionEnd
