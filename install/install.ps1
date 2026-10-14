<#
Install blender-agent-skills for your AI agent(s) on Windows.
  .\install\install.ps1 [-Agent claude,agents,codex,opencode,gemini,copilot,cursor,all]
                        [-Scope user|project] [-Project DIR] [-Link] [-Uninstall] [-Skills a,b]
Defaults: -Agent claude,agents  -Scope user  (copies; -Link makes junctions, no admin needed)
"agents" = ~/.agents/skills, read by Codex, OpenCode, Gemini CLI, GitHub Copilot and Cursor.
#>
param(
    [string[]]$Agent = @("claude", "agents"),
    [ValidateSet("user", "project")][string]$Scope = "user",
    [string]$Project = (Get-Location).Path,
    [switch]$Link,
    [switch]$Uninstall,
    [string[]]$Skills = @()
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if ($PSBoundParameters.ContainsKey("Project")) { $Scope = "project" }
if ($Agent -contains "all") { $Agent = @("claude", "agents", "opencode", "gemini", "copilot", "cursor") }

function Get-Target([string]$a) {
    $u = $HOME; $p = $Project
    $map = @{
        "claude:user" = "$u\.claude\skills";            "claude:project" = "$p\.claude\skills"
        "agents:user" = "$u\.agents\skills";            "agents:project" = "$p\.agents\skills"
        "codex:user" = "$u\.agents\skills";             "codex:project" = "$p\.agents\skills"
        "opencode:user" = "$u\.config\opencode\skills"; "opencode:project" = "$p\.opencode\skills"
        "gemini:user" = "$u\.gemini\skills";            "gemini:project" = "$p\.gemini\skills"
        "copilot:user" = "$u\.copilot\skills";          "copilot:project" = "$p\.github\skills"
        "cursor:user" = "$u\.cursor\skills";            "cursor:project" = "$p\.cursor\skills"
    }
    $k = "${a}:$Scope"
    if (-not $map.ContainsKey($k)) { throw "unknown agent $a" }
    return $map[$k]
}

foreach ($a in $Agent) {
    $dst = Get-Target $a
    New-Item -ItemType Directory -Force $dst | Out-Null
    $n = 0
    foreach ($s in Get-ChildItem -Directory (Join-Path $Root "skills")) {
        if ($Skills.Count -and -not ($Skills -contains $s.Name)) { continue }
        $target = Join-Path $dst $s.Name
        if (Test-Path $target) {
            $item = Get-Item $target -Force
            if ($item.LinkType) { $item.Delete() } else { Remove-Item -Recurse -Force $target }
        }
        if (-not $Uninstall) {
            if ($Link) { New-Item -ItemType Junction -Path $target -Target $s.FullName | Out-Null }
            else { Copy-Item -Recurse $s.FullName $target -Exclude "__pycache__" }
        }
        $n++
    }
    $verb = if ($Uninstall) { "removed" } else { "installed" }
    Write-Output "$verb $n skills -> $dst ($a)"
}
