@echo off
title ADB Remote SSH Tunnel

:: Automatically get the currently logged-in Windows username
set USER_ID=%USERNAME%

:: Set the predefined Remote machine's IP address (No prompt needed)
set REMOTE_IP=10.184.129.24

echo Establishing ADB Remote connection...
echo Target: %USER_ID%@%REMOTE_IP%
echo Please enter the password for '%USER_ID%' if prompted.
echo.

echo "after login"
echo "adb kill-server
echo "adb devices"

:: Create a reverse tunnel for the ADB port (5037)
ssh -R 5037:127.0.0.1:5037 %USER_ID%@%REMOTE_IP% -p 22



echo.
echo Connection closed.
pause
 