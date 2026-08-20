param(
  [Parameter(Position=0, Mandatory=$true)][string]$Command,
  [Parameter(Position=1)][string]$Tool,
  [Parameter(Position=2)][string]$Arguments = "{}",
  [string]$Root = (Get-Location).Path,
  [switch]$ReadOnly
)

$python = if ($env:STEADY_PYTHON) { $env:STEADY_PYTHON } else { "python" }
$prefix = @("-m", "steady_memory", "--root", $Root)
if ($ReadOnly) { $prefix += "--read-only" }

if ($Command -eq "call") {
  & $python @prefix call $Tool --arguments $Arguments
} else {
  & $python @prefix $Command
}
exit $LASTEXITCODE
