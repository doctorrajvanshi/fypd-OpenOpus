!include "EnvVarUpdate.nsh"

Section "AddToPath"
    ${EnvVarUpdate} $0 "PATH" "A" "HKCU" "$INSTDIR"
SectionEnd

Section "un.RemoveFromPath"
    ${EnvVarUpdate} $0 "PATH" "R" "HKCU" "$INSTDIR"
SectionEnd
