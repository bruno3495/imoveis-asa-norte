@echo off
REM Atualiza o painel de imoveis: coleta -> dedup -> build -> commit -> push.
REM Usado pelo Agendador de Tarefas (semanal) e tambem serve p/ rodar com duplo clique.
cd /d "%~dp0"
echo ================================================== >> update.log
echo Execucao: %date% %time% >> update.log
"C:\Users\bruno\AppData\Local\Programs\Python\Python312\python.exe" update.py >> update.log 2>&1
echo Fim: %date% %time% >> update.log
