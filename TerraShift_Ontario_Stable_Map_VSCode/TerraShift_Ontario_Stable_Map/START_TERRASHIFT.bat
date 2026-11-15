@echo off
cd /d "%~dp0"
echo TerraShift Ontario map starting...
where py >nul 2>&1
if %errorlevel%==0 (
 start "" "http://localhost:5500"
 py -m http.server 5500
 goto :end
)
where python >nul 2>&1
if %errorlevel%==0 (
 start "" "http://localhost:5500"
 python -m http.server 5500
 goto :end
)
where npx >nul 2>&1
if %errorlevel%==0 (
 start "" "http://localhost:5500"
 npx --yes http-server -p 5500 -c-1 .
 goto :end
)
echo Could not find Python or Node.js. Opening limited file preview.
start "" "%~dp0index.html"
pause
:end
