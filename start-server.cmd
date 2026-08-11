@echo off
REM 영수증 리더 백엔드 실행 - 더블클릭하면 됩니다.
REM
REM [주의] 이 파일은 CP949(ANSI) 인코딩 + CRLF 줄바꿈이어야 합니다.
REM   UTF-8 로 저장하면 cmd.exe 가 BOM 과 한글을 깨뜨리고,
REM   줄바꿈이 LF 뿐이면 REM 줄 중간이 명령으로 실행됩니다.
REM   편집기(VS Code 등)에서 고칠 때 인코딩이 바뀌지 않는지 확인하세요.
REM
REM Tailscale Funnel 이 이 포트(8000)를 고정 공개 주소로 연결합니다.
REM 주소 확인:  tailscale funnel status
REM Funnel 은 Tailscale 서비스가 부팅 시 알아서 복원하므로 따로 켤 필요가 없습니다.
REM
REM 'python' 이 아니라 'py' 인 이유: 이 PC 의 python 명령은 Microsoft Store
REM 스텁으로 연결돼 있어 실행되지 않습니다.

cd /d "%~dp0"

REM 이미 떠 있는데 또 실행하면 uvicorn 이 포트 충돌 오류만 뱉고 죽습니다.
REM 그 메시지는 무슨 뜻인지 알기 어려우므로 미리 확인합니다.
netstat -ano | findstr /C:"127.0.0.1:8000" | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
    echo.
    echo   이미 서버가 실행 중입니다. 창을 하나만 띄우면 됩니다.
    echo   앱이 안 되면 이 창이 아니라 먼저 띄운 창을 확인하세요.
    echo.
    echo   새로 켜고 싶으면 실행 중인 창을 먼저 닫으세요.
    echo.
    pause
    exit /b 1
)

echo.
echo   영수증 리더 서버를 시작합니다. 이 창을 닫으면 서버가 꺼집니다.
echo.
py -m uvicorn server:app --host 127.0.0.1 --port 8000
echo.
echo   서버가 종료됐습니다.
pause
