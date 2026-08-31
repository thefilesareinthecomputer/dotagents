. .\helpers.ps1
Import-Module ./mod.psm1

function Invoke-Deploy {
    param([string]$Target)
    $config = Get-Config
    Publish-Artifact -Path $config.Path -Target $Target
}

Invoke-Deploy -Target "staging"
