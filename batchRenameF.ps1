# --- 1. SETTINGS ---
$parentDir = "C:\Your\Parent\Folder"
$csvPath   = "C:\path\to\your_data.csv"
$logPath   = "C:\path\to\rename_log.txt"

# --- 2. BEST PRACTICE: AUTOMATED BACKUP ---
# Creates a timestamped copy of the parent folder before any changes are made
$backupDir = Join-Path $parentDir "Backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Write-Host "Creating backup at: $backupDir" -ForegroundColor Yellow
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item -Path "$parentDir\*" -Destination $backupDir -Recurse -Exclude "Backup_*"

# --- 3. EXECUTION LOOP WITH ERROR HANDLING & LOGGING ---
Import-Csv $csvPath | ForEach-Object {
    $currentLookup  = $_.lookup
    $currentReplace = $_.replacewith

    try {
        # BEST PRACTICE: FIND THE TARGET FOLDER
        $targetFolder = Get-ChildItem -Path $parentDir -Directory -Filter "*$currentLookup*" | Select-Object -First 1

        if ($targetFolder) {
            # BEST PRACTICE: LOGGING SUCCESS
            $logMsg = "$(Get-Date): SUCCESS - Processing folder '$($targetFolder.FullName)' with lookup '$currentLookup'"
            Write-Host $logMsg -ForegroundColor Cyan
            $logMsg | Out-File -FilePath $logPath -Append

            # EXECUTION: Call your script
            # TIP: Add -WhatIf to your rename.ps1 call below to SIMULATE first!
            .\rename.ps1 -folder "$($targetFolder.FullName)" -lookup $currentLookup -replacewith $currentReplace
        } 
        else {
            throw "No folder found containing: $currentLookup"
        }
    }
    catch {
        # BEST PRACTICE: ERROR HANDLING & LOGGING
        $errorEntry = "$(Get-Date): ERROR - Row with lookup '$currentLookup' failed. Reason: $($_.Exception.Message)"
        $errorEntry | Out-File -FilePath $logPath -Append
        Write-Error $errorEntry
    }
}
