# Usage: .\build.ps1   (configures if needed, then builds build\release\MLWS_Listener.dll)
$root = $PSScriptRoot
$steps = @()
if (-not (Test-Path "$root\build\release\build.ninja")) { $steps += "cmake --preset release" }
$steps += "cmake --build --preset release"
$cmd = 'call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && ' +
	'set "VCPKG_ROOT=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\vcpkg" && ' +
	"cd /d `"$root`" && " + ($steps -join ' && ')
cmd /c $cmd
exit $LASTEXITCODE
