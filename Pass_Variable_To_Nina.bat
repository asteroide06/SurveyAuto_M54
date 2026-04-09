REM echo off
echo.
echo Running Pass_Sys_Var_To_NINA.bat
echo.

set file=%1
set /p value=< "C:\NightImages\Confirm\%file%"
set /a out=value * 1

echo %out%

exit /B %out%

