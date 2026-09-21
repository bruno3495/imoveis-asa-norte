@echo off
REM Monitor dos imoveis da UnB. Leve (1 requisicao), roda todo dia.
REM Os imoveis saem as quartas 08h e somem em dias — por isso a checagem diaria.
cd /d "%~dp0"
echo ================================================== >> unb.log
echo Execucao: %date% %time% >> unb.log
"C:\Users\bruno\AppData\Local\Programs\Python\Python312\python.exe" unb.py >> unb.log 2>&1
REM publica a pagina se houver mudanca
git add unb.html unb_estado.json >nul 2>&1
git diff --cached --quiet || (
  git -c commit.gpgsign=false commit -q -m "Atualiza monitor UnB" >> unb.log 2>&1
  git push -q >> unb.log 2>&1
)
echo Fim: %date% %time% >> unb.log
