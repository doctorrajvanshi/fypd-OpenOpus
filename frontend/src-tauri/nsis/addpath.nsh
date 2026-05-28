Section "AddToPath"
    EnVar::SetHKCU
    EnVar::AddValue "PATH" "$INSTDIR"
SectionEnd

Section "un.RemoveFromPath"
    EnVar::SetHKCU
    EnVar::DeleteValue "PATH" "$INSTDIR"
SectionEnd
